"""Free sources added on 23 November 2026 so the scenario agent has non-US macro, rates, housing and trade data.

Eurostat allows commercial reuse with credit, but only of data for EU, EFTA and candidate countries, so every other
country is dropped. OECD data may be reused for any purpose with credit. BIS statistics are free with citation,
provided they add no extra charge for users. New York Fed reference rates may be republished with the Bank's notice.
FHFA, USGS and Census data are US government works. Each series title names the country and the measure in plain words,
so the agent's find_series can match a question such as "German inflation" or "Turkish lira".
"""
import csv
import datetime as dt
import io
import os
import re
import time
import xml.etree.ElementTree as ET

from core import Run, fetch, upsert_series

FREQ = {"M": "Monthly", "Q": "Quarterly", "A": "Annual", "D": "Daily", "W": "Weekly"}


def _date(period):
    """SDMX periods to the database's dates: 2026-03 and 2026-Q1 become the first day, 2026 the last day of the year."""
    p = str(period)
    if len(p) == 7 and p[5] == "Q":
        return f"{p[:4]}-{(int(p[6]) - 1) * 3 + 1:02d}-01"
    if len(p) == 7:
        return f"{p}-01"
    if len(p) == 4:
        return f"{p}-12-31"
    return p[:10]


def _current(rows):
    """Whether a series is still published. One that stopped over 18 months ago would read as a current figure."""
    return max(d for d, _ in rows) >= (dt.date.today() - dt.timedelta(days=548)).isoformat()


def _require(con, run_, missing):
    """Fails the run when a source answered but part of it came back empty, or it returned under half the readings of
    its last good run, so the daily check-in alerts the team. Readings stored earlier are kept."""
    if missing:
        raise RuntimeError("no data for " + ", ".join(missing))
    last = con.execute("SELECT rows_written FROM cat_run WHERE step=? AND status='ok' ORDER BY run_id DESC LIMIT 1", (run_.step,)).fetchone()
    if last and last[0] and run_.rows < last[0] / 2:
        raise RuntimeError(f"only {run_.rows} readings came back, against {last[0]} last time")


# Eurostat. Only EU members, the euro area and EU aggregates, EFTA and candidate countries may be reused commercially.
EU_GEO = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "EL": "Greece", "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SK": "Slovakia", "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
    "IS": "Iceland", "LI": "Liechtenstein", "NO": "Norway", "CH": "Switzerland",
    "AL": "Albania", "BA": "Bosnia and Herzegovina", "GE": "Georgia", "MD": "Moldova", "ME": "Montenegro", "MK": "North Macedonia",
    "RS": "Serbia", "TR": "Turkey", "UA": "Ukraine",
}
EURO_AREA = ("EA", "EA21", "EA20", "EA19")   # the changing composition first, then the latest fixed one
# (dataset, filters, id suffix, measure, units, topic). The economic sentiment indicator and the 10 year yields
# (ei_bssi_m_r2, irt_lt_mcby_m) are left out until it is clear that Eurostat's reuse notice covers them, since it
# excludes data identified as belonging to other sources.
ESTAT = [
    ("prc_hicp_minr", {"unit": "RCH_A", "coicop18": "TOTAL"}, "hicp", "inflation, consumer prices (HICP), annual rate", "Percent, year on year", "Inflation"),
    ("prc_hicp_minr", {"unit": "RCH_A", "coicop18": "TOT_X_NRG_FOOD"}, "hicp_core", "core inflation, HICP excluding energy, food, alcohol and tobacco, annual rate", "Percent, year on year", "Inflation"),
    ("prc_hicp_minr", {"unit": "RCH_A", "coicop18": "NRG"}, "hicp_energy", "energy price inflation, HICP energy, annual rate", "Percent, year on year", "Inflation"),
    ("prc_hicp_minr", {"unit": "RCH_A", "coicop18": "SERV"}, "hicp_services", "services inflation, HICP services, annual rate", "Percent, year on year", "Inflation"),
    ("une_rt_m", {"s_adj": "SA", "age": "TOTAL", "sex": "T", "unit": "PC_ACT"}, "unemployment", "unemployment rate, seasonally adjusted", "Percent of labour force", "Labour"),
    ("namq_10_gdp", {"na_item": "B1GQ", "unit": "CLV_PCH_PRE", "s_adj": "SCA"}, "gdp_qoq", "real GDP growth, quarter on quarter", "Percent", "Growth"),
    ("namq_10_gdp", {"na_item": "B1GQ", "unit": "CLV_PCH_SM", "s_adj": "SCA"}, "gdp_yoy", "real GDP growth, year on year", "Percent", "Growth"),
    ("sts_inpr_m", {"indic_bt": "PRD", "nace_r2": "B-D", "s_adj": "SCA", "unit": "I21"}, "industrial_production", "industrial production, seasonally adjusted", "Index, 2021 = 100", "Growth"),
    ("gov_10q_ggdebt", {"unit": "PC_GDP", "sector": "S13", "na_item": "GD"}, "gov_debt", "government debt", "Percent of GDP", "Fiscal"),
]


def _jsonstat(body):
    """A Eurostat JSON-stat answer as {(geo, time): value}, for a query that fixes every other dimension."""
    ids, sizes, dims = body["id"], body["size"], body["dimension"]
    keys = []
    for d in ids:
        idx = dims[d]["category"]["index"]
        keys.append(sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx))
    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    gi, ti = ids.index("geo"), ids.index("time")
    out = {}
    values = body.get("value") or {}
    for flat, v in (values.items() if isinstance(values, dict) else enumerate(values)):
        if v is None:
            continue
        n = int(flat)
        pos = [(n // strides[i]) % sizes[i] for i in range(len(ids))]
        out[(keys[gi][pos[gi]], keys[ti][pos[ti]])] = v
    return out


def _estat(dataset, filters, since):
    r = fetch(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}",
              params={"format": "JSON", "lang": "EN", "sinceTimePeriod": since, **filters}, timeout=300)
    return _jsonstat(r.json())


def eurostat(con):
    """Inflation, unemployment, GDP, industry and government debt for EU, euro area and nearby countries."""
    with Run(con, "eurostat") as run_:
        series, missing = 0, []
        for dataset, filters, suffix, measure, units, topic in ESTAT:
            monthly = dataset not in ("namq_10_gdp", "gov_10q_ggdebt")
            got = _estat(dataset, filters, "2000-01" if monthly else "2000-Q1")
            before = series
            euro = next((g for g in EURO_AREA if any(k[0] == g for k in got)), None)
            places = {g: ("Euro area", "Eurozone", "EA") for g in [euro] if g}
            places["EU27_2020"] = ("European Union", "European Union", "EU27")
            places.update({g: (name, name, g) for g, name in EU_GEO.items()})
            for geo, (label, country, code) in places.items():
                rows = [(_date(t), v) for (g, t), v in got.items() if g == geo]
                if rows and _current(rows):
                    n = upsert_series(con, f"estat:{code}:{suffix}", "macro_eurostat", f"{label}: {measure}", units,
                                      "Monthly" if monthly else "Quarterly", rows, country, topic)
                    run_.rows += n
                    series += 1
            if series == before:
                missing.append(suffix)
            con.commit()
        run_.note(f"{series} series")
        _require(con, run_, missing)


# OECD. Composite leading indicators and confidence for the G20, and for countries outside the EU (which Eurostat
# covers): unemployment, consumer price inflation and interest rates.
OECD_NAMES = {"CHN": "China", "KOR": "South Korea", "TUR": "Turkey", "SVK": "Slovakia", "EA20": "Euro area", "EU": "European Union",
              "USA": "United States", "GBR": "United Kingdom", "G4E": "Major four European countries", "A5M": "Major five Asian economies"}
OECD_FLOWS = [
    ("OECD.SDD.STES,DSD_STES@DF_CLI,", ".M.LI+BCICP+CCICP...AA...H", False, {
        "LI": ("cli", "composite leading indicator (OECD CLI), amplitude adjusted, business cycle", "Index, long run average = 100", "Growth"),
        "BCICP": ("business_confidence", "business confidence, amplitude adjusted", "Index, long run average = 100", "Growth"),
        "CCICP": ("consumer_confidence", "consumer confidence, amplitude adjusted", "Index, long run average = 100", "Growth")}),
    ("OECD.SDD.STES,DSD_STES@DF_FINMARK,", ".M.IRLT+IR3TIB.PA.....", True, {
        "IRLT": ("bond_10y", "long-term interest rate, 10 year government bond yield", "Percent", "Rates"),
        "IR3TIB": ("rate_3m", "short-term interest rate, 3 month interbank", "Percent", "Rates")}),
    ("OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,", ".UNE_LF_M.._Z.Y._T.Y_GE15..M", True, {
        "UNE_LF_M": ("unemployment", "unemployment rate, seasonally adjusted", "Percent of labour force", "Labour")}),
    ("OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,", ".M.N.CPI.PA._T.N.GY", True, {
        "CPI": ("cpi", "inflation, consumer prices (CPI), annual rate", "Percent, year on year", "Inflation")}),
]
# OECD codes of countries whose figures come from Eurostat instead.
OECD_IN_EU = {"AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX",
              "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE", "ISL", "NOR", "CHE", "TUR", "EA20", "EA19", "EU", "EU27_2020", "EA"}


def oecd(con):
    """OECD composite leading indicators and confidence, and unemployment, inflation and interest rates outside the EU."""
    with Run(con, "oecd") as run_:
        series, missing = 0, []
        for flow, key, outside_eu, measures in OECD_FLOWS:
            r = fetch(f"https://sdmx.oecd.org/public/rest/data/{flow}/{key}", params={"startPeriod": "2000-01", "format": "csvfilewithlabels"},
                      headers={"Accept": "application/vnd.sdmx.data+csv; charset=utf-8; labels=both"}, timeout=300)
            got = {}
            for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))):
                area, measure = row["REF_AREA"], row["MEASURE"]
                if measure not in measures or (outside_eu and area in OECD_IN_EU) or not row["OBS_VALUE"]:
                    continue
                name = OECD_NAMES.get(area) or row.get("Reference area") or area
                got.setdefault((area, measure), (name, []))[1].append((_date(row["TIME_PERIOD"]), row["OBS_VALUE"]))
            missing += [suffix for m, (suffix, *_) in measures.items() if not any(k[1] == m for k in got)]
            for (area, measure), (name, rows) in got.items():
                if not _current(rows):
                    continue
                suffix, label, units, topic = measures[measure]
                run_.rows += upsert_series(con, f"oecd:{area}:{suffix}", "macro_oecd", f"{name}: {label}", units, "Monthly", rows, name, topic)
                series += 1
            con.commit()
        run_.note(f"{series} series")
        _require(con, run_, missing)


# BIS. Codes for places come from its own code list.
def _bis_areas():
    root = ET.fromstring(fetch("https://stats.bis.org/api/v1/codelist/BIS/CL_BIS_IF_REF_AREA", timeout=120).content)
    out = {}
    for el in root.iter():
        if el.tag.endswith("}Code"):
            name = next((n.text for n in el if n.tag.endswith("}Name")), None)
            if name:
                out[el.attrib["id"]] = name
    return out


BIS_FIX = {"XM": "Euro area", "KR": "South Korea", "TR": "Turkey", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "RU": "Russia", "VN": "Vietnam"}
BIS_PARTS = ("policy_rate", "house_prices", "credit_p", "credit_h", "credit_n", "credit_g", "credit_gap", "eer_n", "eer_r", "usd")


# Central bank names, so a question that names the bank finds its rate.
CENTRAL_BANKS = {
    "US": "Federal Reserve", "XM": "European Central Bank (ECB)", "GB": "Bank of England", "JP": "Bank of Japan", "CN": "People's Bank of China",
    "CA": "Bank of Canada", "AU": "Reserve Bank of Australia", "NZ": "Reserve Bank of New Zealand", "CH": "Swiss National Bank",
    "SE": "Sveriges Riksbank", "NO": "Norges Bank", "DK": "Danmarks Nationalbank", "IN": "Reserve Bank of India", "KR": "Bank of Korea",
    "BR": "Banco Central do Brasil", "MX": "Banco de Mexico (Banxico)", "TR": "Central Bank of the Republic of Turkey", "RU": "Bank of Russia",
    "ZA": "South African Reserve Bank", "ID": "Bank Indonesia", "TH": "Bank of Thailand", "MY": "Bank Negara Malaysia", "PH": "Bangko Sentral ng Pilipinas",
    "SA": "Saudi Central Bank", "IL": "Bank of Israel", "PL": "National Bank of Poland", "CZ": "Czech National Bank", "HU": "Magyar Nemzeti Bank",
    "CL": "Central Bank of Chile", "CO": "Banco de la Republica (Colombia)", "PE": "Central Reserve Bank of Peru", "AR": "Central Bank of Argentina",
    "HK": "Hong Kong Monetary Authority", "IS": "Central Bank of Iceland", "RO": "National Bank of Romania", "RS": "National Bank of Serbia",
    "MK": "National Bank of North Macedonia", "HR": "Croatian National Bank",
}


def _bis(flow, key, start, **extra):
    params = {"format": "csv", "startPeriod": start, "detail": "dataonly", **extra}
    r = fetch(f"https://stats.bis.org/api/v1/data/{flow}/{key}/all", params=params, timeout=300)
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


def _bis_currencies():
    """{area: (currency code, currency name)} from the titles of the dollar exchange rate series."""
    out = {}
    for r in _bis("WS_XRU", "M...A", "2020-01", detail="full", lastNObservations=1):
        parts = [p.strip() for p in (r.get("TITLE") or "").split(" - ")]
        if r["CURRENCY"] != "USD" and len(parts) > 1:
            out.setdefault(r["REF_AREA"], (r["CURRENCY"], parts[1]))
    return out


def bis(con):
    """Central bank policy rates, house prices, credit by sector, credit gaps, effective exchange rates and dollar exchange rates."""
    with Run(con, "bis") as run_:
        areas = _bis_areas()
        place = lambda c: BIS_FIX.get(c) or areas.get(c, c)  # noqa: E731
        series, done = 0, set()

        def put(sid, title, units, freq, rows, country, topic):
            nonlocal series
            if not _current(rows):
                return
            done.add(sid.split(":")[1])
            run_.rows += upsert_series(con, f"bis:{sid}", "macro_bis", title, units, freq, rows, country, topic)
            series += 1

        def group(rows, *cols):
            out = {}
            for r in rows:
                if r.get("OBS_VALUE") not in (None, "", "NaN"):
                    out.setdefault(tuple(r[c] for c in cols), []).append((_date(r["TIME_PERIOD"]), r["OBS_VALUE"]))
            return out

        money = _bis_currencies()
        money["XM"] = ("EUR", "euro")
        for (area,), rows in group(_bis("WS_CBPOL", "M.", "1990-01"), "REF_AREA").items():
            bank = f"{CENTRAL_BANKS[area]} " if area in CENTRAL_BANKS else "central bank "
            put(f"{area}:policy_rate", f"{place(area)}: {bank}policy rate, central bank interest rate, end of month", "Percent", "Monthly", rows, place(area), "Rates")
        for (area, kind), rows in group(_bis("WS_SPP", "Q..N+R.628", "1990-01"), "REF_AREA", "VALUE").items():
            word = "real, after inflation" if kind == "R" else "nominal"
            put(f"{area}:house_prices_{kind.lower()}", f"{place(area)}: residential property prices, house prices, {word}", "Index, 2010 = 100", "Quarterly", rows, place(area), "Housing")
        sector = {"P": "private non-financial sector", "H": "households", "N": "non-financial companies", "G": "general government"}
        credit = group(_bis("WS_TC", "Q..P+H+N+G.A..770.A", "1990-01"), "BORROWERS_CTY", "TC_BORROWERS", "VALUATION")
        for (area, who, valuation), rows in credit.items():
            if valuation == "N" and (area, who, "M") in credit:
                continue   # market value is preferred where both exist
            put(f"{area}:credit_{who.lower()}", f"{place(area)}: credit to {sector[who]}, debt", "Percent of GDP", "Quarterly", rows, place(area), "Credit")
        for (area,), rows in group(_bis("WS_CREDIT_GAP", "Q..P.A.C", "1990-01"), "BORROWERS_CTY").items():
            put(f"{area}:credit_gap", f"{place(area)}: credit-to-GDP gap, private credit above its long run trend", "Percentage points of GDP", "Quarterly", rows, place(area), "Credit")
        for (kind, area), rows in group(_bis("WS_EER", "M.N+R.B.", "2000-01"), "EER_TYPE", "REF_AREA").items():
            word = "real" if kind == "R" else "nominal"
            cur = f"{money[area][1]} ({money[area][0]}) " if area in money else ""
            put(f"{area}:eer_{kind.lower()}", f"{place(area)}: {cur}{word} effective exchange rate, broad basket, trade weighted currency", "Index, 2020 = 100", "Monthly", rows, place(area), "FX")
        names = {code: name for code, name in money.values()}
        seen = set()
        # One series per currency. Where several places share it, the euro area or the longest running one is kept.
        fx = group(_bis("WS_XRU", "M...A", "2000-01"), "REF_AREA", "CURRENCY")
        for (area, cur), rows in sorted(fx.items(), key=lambda kv: (kv[0][0] == "XM", max(kv[1])[0], len(kv[1])), reverse=True):
            if cur in seen or cur == "USD":
                continue
            seen.add(cur)
            label = f"{names[cur]} ({cur})" if cur in names else cur
            put(f"{cur}:usd", f"{place(area)}: {label} per US dollar, exchange rate, monthly average", f"{cur} per USD", "Monthly", rows, place(area), "FX")
        con.commit()
        run_.note(f"{series} series")
        _require(con, run_, [p for p in BIS_PARTS if not any(d.startswith(p) for d in done)])


# New York Fed reference rates.
NYFED = [
    ("secured/sofr", "SOFR", "Secured Overnight Financing Rate (SOFR)"),
    ("secured/bgcr", "BGCR", "Broad General Collateral Rate (BGCR), repo rate"),
    ("secured/tgcr", "TGCR", "Tri-Party General Collateral Rate (TGCR), repo rate"),
    ("unsecured/effr", "EFFR", "Effective Federal Funds Rate (EFFR), New York Fed"),
    ("unsecured/obfr", "OBFR", "Overnight Bank Funding Rate (OBFR)"),
]


def nyfed_rates(con):
    """SOFR, the repo rates, EFFR and OBFR with their daily volumes, and the SOFR averages and index."""
    with Run(con, "nyfed_sofr") as run_:
        end, missing = dt.date.today().isoformat(), []
        for path, code, title in NYFED:
            got = fetch(f"https://markets.newyorkfed.org/api/rates/{path}/search.json", params={"startDate": "2000-01-01", "endDate": end}).json()["refRates"]
            low = code.lower()
            if not got or not _current([(r["effectiveDate"], 0) for r in got]):
                missing.append(code)
            run_.rows += upsert_series(con, f"nyfr:{low}", "rates_nyfed", title, "Percent", "Daily",
                                       [(r["effectiveDate"], r.get("percentRate")) for r in got], "United States", "Rates")
            run_.rows += upsert_series(con, f"nyfr:{low}_volume", "rates_nyfed", f"{title.split(' (')[0]} daily volume", "Billions USD", "Daily",
                                       [(r["effectiveDate"], r.get("volumeInBillions")) for r in got], "United States", "Rates")
        got = fetch("https://markets.newyorkfed.org/api/rates/secured/sofrai/search.json", params={"startDate": "2018-04-02", "endDate": end}).json()["refRates"]
        for key, sid, title, units in (("average30day", "sofr_avg30", "SOFR 30 day average", "Percent"), ("average90day", "sofr_avg90", "SOFR 90 day average", "Percent"),
                                       ("average180day", "sofr_avg180", "SOFR 180 day average", "Percent"), ("index", "sofr_index", "SOFR Index", "Index, 2 April 2018 = 1")):
            run_.rows += upsert_series(con, f"nyfr:{sid}", "rates_nyfed", title, units, "Daily", [(r["effectiveDate"], r.get(key)) for r in got], "United States", "Rates")
        con.commit()
        _require(con, run_, missing + ([] if got else ["SOFR averages"]))


# FHFA house prices: the purchase-only index for the US and its nine census divisions (monthly), every state and the
# 100 largest metro areas (quarterly), seasonally adjusted.
def fhfa_hpi(con):
    """US house prices by census division, state and large metro area."""
    with Run(con, "fhfa_hpi") as run_:
        text = fetch("https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv", timeout=300).content.decode("utf-8-sig")
        got = {}
        for r in csv.DictReader(io.StringIO(text)):
            if r["hpi_type"] != "traditional" or r["hpi_flavor"] != "purchase-only":
                continue
            level, freq = r["level"], r["frequency"]
            if not ((freq == "monthly" and level == "USA or Census Division") or (freq == "quarterly" and level in ("State", "MSA"))):
                continue
            value = r["index_sa"] or None
            if value is None:
                continue
            month = int(r["period"]) if freq == "monthly" else (int(r["period"]) - 1) * 3 + 1
            got.setdefault((freq, level, r["place_id"], r["place_name"]), []).append((f"{r['yr']}-{month:02d}-01", value))
        series = 0
        for (freq, level, pid, name), rows in got.items():
            place = "United States" if name == "United States" else (f"{name}, US" if level == "USA or Census Division" else name)
            base = "January 1991 = 100" if freq == "monthly" else "1991 Q1 = 100"
            title = f"{place}: house prices, purchase-only index, seasonally adjusted" + (" (metro area)" if level == "MSA" else "")
            run_.rows += upsert_series(con, f"fhfa:{'m' if freq == 'monthly' else 'q'}:{pid}", "housing_fhfa", title, f"Index, {base}",
                                       freq.capitalize(), rows, "United States", "Housing")
            series += 1
        con.commit()
        run_.note(f"{series} series")
        _require(con, run_, [f"{f} {lv}" for f, lv in (("monthly", "USA or Census Division"), ("quarterly", "State"), ("quarterly", "MSA")) if not any(k[:2] == (f, lv) for k in got)])


# US Census international trade: US goods imports and exports with every partner, and by HS chapter with the largest
# partners and the EU, for tariff questions. Census needs a free API key (CENSUS_API_KEY).
TRADE_TOP = 25                # partners by total trade over the last 12 months that get a breakdown by chapter
MIN_MONTHLY_USD = 50e6        # a chapter is kept for a partner only if it averaged at least this much a month over the last year
TRADE_NAMES = {"Korea, South": "South Korea"}
TRADE_FLOWS = (("imports", "I_COMMODITY", "GEN_VAL_MO", "imports from"), ("exports", "E_COMMODITY", "ALL_VAL_MO", "exports to"))


def _census(flow, key, start, **params):
    """Rows from the trade API. Two years a request, since a longer one runs past the server's time limit (524)."""
    out, this_year = [], dt.date.today().year
    for year in range(start, this_year + 1, 2):
        period = f"from {year}-01 to {min(year + 1, this_year)}-12"
        for attempt in range(4):
            try:
                r = fetch(f"https://api.census.gov/data/timeseries/intltrade/{flow}/hs", params={**params, "time": period, "key": key}, timeout=300)
                break
            except RuntimeError as e:
                if str(e).startswith("204 from"):
                    r = None
                    break
                if not str(e).startswith("524 from") or attempt == 3:
                    raise RuntimeError(str(e).replace(key, "[hidden]")) from None   # a connection error quotes the address, key included
                time.sleep(20 * (attempt + 1))
        if r is None:
            continue
        if "json" not in r.headers.get("content-type", ""):
            title = re.search(r"<title>(.*?)</title>", r.text)
            raise RuntimeError(f"Census answered with a page, not data: {title[1] if title else 'no title'}. If it says Invalid Key, check CENSUS_API_KEY")
        body = r.json()
        out += [dict(zip(body[0], row)) for row in body[1:]]
    return out


def census_trade(con):
    """US goods imports and exports by partner, in total and by HS chapter, monthly from 2015."""
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise RuntimeError("CENSUS_API_KEY is not set")
    with Run(con, "census_trade") as run_:
        series, size = 0, {}
        # The whole history once, then the last three years, which hold the revisions.
        done = con.execute("SELECT 1 FROM cat_run WHERE step='census_trade' AND status='ok' LIMIT 1").fetchone()
        start = dt.date.today().year - 2 if done else 2015
        for flow, comm, val, words in TRADE_FLOWS:
            # Country codes are four digits; codes starting with 0 or holding an X are groups, of which only the EU is kept.
            got = {}
            rows = [r for r in _census(flow, key, start, get=f"CTY_CODE,CTY_NAME,{val}", **{comm: "-"})
                    if r["CTY_CODE"] and r["CTY_CODE"].isdigit() and (r["CTY_CODE"][0] != "0" or r["CTY_CODE"] == "0003")]
            # Some months leave the name out, so a partner keeps the latest name Census gave its code.
            names = {r["CTY_CODE"]: r["CTY_NAME"].title() for r in sorted(rows, key=lambda r: r["time"]) if r["CTY_NAME"]}
            for r in rows:
                name = names.get(r["CTY_CODE"])
                if name:
                    got.setdefault((r["CTY_CODE"], TRADE_NAMES.get(name, name)), []).append((f"{r['time']}-01", r[val]))
            for (code, name), obs in got.items():
                obs.sort()
                size[(code, name)] = size.get((code, name), 0) + sum(float(v or 0) for _, v in obs[-12:])
                run_.rows += upsert_series(con, f"ustrade:{flow}:{code}", "trade_census", f"US goods {words} {name}, total", "USD", "Monthly", obs, name, "Trade")
                series += 1
            con.commit()
        top = sorted((k for k in size if k[0] != "0003"), key=size.get, reverse=True)[:TRADE_TOP] + [k for k in size if k[0] == "0003"]
        for flow, comm, val, words in TRADE_FLOWS:
            for code, name in top:
                chapters, text = {}, {}
                for r in _census(flow, key, start, get=f"{comm},{comm}_SDESC,{val}", COMM_LVL="HS2", CTY_CODE=code):
                    if r[f"{comm}_SDESC"]:
                        text[r[comm]] = r[f"{comm}_SDESC"]
                    chapters.setdefault(r[comm], []).append((f"{r['time']}-01", r[val]))
                for hs, obs in chapters.items():
                    desc = text.get(hs, "other goods")
                    obs.sort()
                    recent = [float(v or 0) for _, v in obs[-12:]]
                    if sum(recent) / max(1, len(recent)) < MIN_MONTHLY_USD:
                        continue
                    run_.rows += upsert_series(con, f"ustrade:{flow}:{code}:hs{hs}", "trade_census", f"US goods {words} {name}: {desc.capitalize()} (HS {hs})",
                                               "USD", "Monthly", obs, name, "Trade")
                    series += 1
                con.commit()
        run_.note(f"{series} series")
        # The size guard in _require does not fit here: a later run is meant to return far fewer readings than the first.
        if series < 400:
            raise RuntimeError(f"only {series} trade series came back")
