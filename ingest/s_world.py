"""Free sources added on 11 November 2026 so the scenario agent can reason about countries, currencies, rates and hazards.

Federal Reserve Board releases are public domain. USGS and NOAA data are US government works.
World Bank indicators are CC BY 4.0 unless an indicator's metadata says otherwise.
"""
import csv
import datetime as dt
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile

from core import Run, fetch, upsert_series

# H.10 country codes the Board uses in its series names.
H10_NAMES = {
    "AUD": "Australian dollar", "EUR": "euro", "NZD": "New Zealand dollar", "GBP": "pound sterling", "ZAR": "South African rand",
    "BRL": "Brazilian real", "CAD": "Canadian dollar", "CNY": "Chinese yuan", "DKK": "Danish krone", "HKD": "Hong Kong dollar",
    "INR": "Indian rupee", "JPY": "Japanese yen", "MYR": "Malaysian ringgit", "MXN": "Mexican peso", "NOK": "Norwegian krone",
    "SGD": "Singapore dollar", "KRW": "South Korean won", "LKR": "Sri Lankan rupee", "SEK": "Swedish krona", "CHF": "Swiss franc",
    "TWD": "Taiwan dollar", "THB": "Thai baht", "VEB": "Venezuelan bolivar",
}
# H.15 business day series kept beyond the Treasury curve: constant maturities back to 1962, the prime rate and commercial paper.
H15_TENORS = {"M01": "1 month", "M03": "3 month", "M06": "6 month", "Y01": "1 year", "Y02": "2 year", "Y03": "3 year", "Y05": "5 year",
              "Y07": "7 year", "Y10": "10 year", "Y20": "20 year", "Y30": "30 year"}
H15_OTHER = {
    "RIFSPBLP_N.B": ("prime", "US bank prime loan rate", "Rates"),
    "RIFSPPFAAD30_N.B": ("cp_fin_30d", "US 30 day AA financial commercial paper rate", "Credit"),
    "RIFSPPNAAD30_N.B": ("cp_nonfin_30d", "US 30 day AA nonfinancial commercial paper rate", "Credit"),
    "RIFSPPNA2P2D30_N.B": ("cp_a2p2_30d", "US 30 day A2/P2 nonfinancial commercial paper rate", "Credit"),
}


def _sdmx_series(blob, keep):
    """Every series in a Federal Reserve SDMX zip that keep(attrib) accepts, as {name: (attrib, [(date, value)])}."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in z.namelist() if n.lower().endswith("_data.xml"))
    out, cur = {}, None
    with z.open(name) as f:
        for ev, el in ET.iterparse(f, events=("start", "end")):
            tag = el.tag.rsplit("}", 1)[-1]
            if ev == "start" and tag == "Series":
                a = dict(el.attrib)
                cur = [] if keep(a) else None
                if cur is not None:
                    out[a["SERIES_NAME"]] = (a, cur)
            elif ev == "end" and tag == "Obs":
                if cur is not None and el.attrib.get("OBS_STATUS", "A") == "A":
                    cur.append((el.attrib["TIME_PERIOD"], el.attrib.get("OBS_VALUE")))
                el.clear()
            elif ev == "end" and tag == "Series":
                cur = None
                el.clear()
    return out


def _board(rel):
    return fetch("https://www.federalreserve.gov/datadownload/Output.aspx", params={"rel": rel, "filetype": "zip"}, timeout=300).content


def fed_fx(con):
    """Daily noon buying rates in New York for 23 currencies, from 1971."""
    with Run(con, "fed_fx") as run_:
        got = _sdmx_series(_board("H10"), lambda a: re.fullmatch(r"RXI(\$US)?_N\.B\.[A-Z]+", a.get("SERIES_NAME", "")) is not None)
        for code, (a, rows) in got.items():
            cur = a.get("FX") if a.get("FX") in H10_NAMES else a.get("CURRENCY")
            label = H10_NAMES.get(cur, cur)
            if code.startswith("RXI$US"):
                sid, title, units = f"frbfx:{cur}USD", f"US dollars per {label}", f"USD per {cur}"
            else:
                sid, title, units = f"frbfx:USD{cur}", f"{label[0].upper() + label[1:]} per US dollar", f"{cur} per USD"
            run_.rows += upsert_series(con, sid, "fx_fed", title, units, "Daily", rows, None, "FX")
        con.commit()
        run_.note(f"{len(got)} currency series")


def fed_rates(con):
    """Treasury constant maturities from 1962, the prime rate and commercial paper, from the H.15 release."""
    with Run(con, "fed_h15") as run_:
        def keep(a):
            n = a.get("SERIES_NAME", "")
            return n in H15_OTHER or re.fullmatch(r"RIFLGFC(M|Y)\d\d_N\.B", n) is not None
        got = _sdmx_series(_board("H15"), keep)
        for code, (a, rows) in got.items():
            if code in H15_OTHER:
                sid, title, topic = H15_OTHER[code]
            else:
                tenor = H15_TENORS.get(code[7:10])
                if not tenor:
                    continue
                sid, title, topic = f"cmt_{code[7:10].lower()}", f"US Treasury {tenor} constant maturity yield", "Rates"
            run_.rows += upsert_series(con, f"h15:{sid}", "rates_h15", title, "Percent", "Daily", rows, "United States", topic)
        con.commit()
        run_.note(f"{len(got)} series")


def earthquakes(con, min_mag=5.5, first_year=1970):
    """Every earthquake of magnitude 5.5 or more worldwide, with place, depth and tsunami flag."""
    with Run(con, "usgs_quakes") as run_:
        con.execute("""CREATE TABLE IF NOT EXISTS geo_quake(
            event_id TEXT PRIMARY KEY, time TEXT, mag REAL, place TEXT, lat REAL, lon REAL, depth_km REAL, tsunami INTEGER, alert TEXT, url TEXT)""")
        con.execute("CREATE INDEX IF NOT EXISTS ix_geo_quake_time ON geo_quake(time)")
        for start in range(first_year, dt.date.today().year + 1, 5):
            r = fetch("https://earthquake.usgs.gov/fdsnws/event/1/query",
                      params={"format": "geojson", "starttime": f"{start}-01-01", "endtime": f"{start + 5}-01-01", "minmagnitude": min_mag, "orderby": "time-asc", "limit": 20000},
                      timeout=180)
            rows = []
            for ft in r.json().get("features", []):
                p, g = ft["properties"], ft["geometry"]["coordinates"]
                when = dt.datetime.fromtimestamp(p["time"] / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                rows.append((ft["id"], when, p.get("mag"), p.get("place"), g[1], g[0], g[2], p.get("tsunami"), p.get("alert"), p.get("url")))
            con.executemany("INSERT OR REPLACE INTO geo_quake VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)


SEASON_MID = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6, "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}


def enso(con):
    """The Oceanic Nino Index: three month sea surface temperature anomalies. El Nino above 0.5, La Nina below -0.5."""
    with Run(con, "noaa_enso") as run_:
        text = fetch("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt").text
        rows = []
        for line in text.splitlines()[1:]:
            p = line.split()
            if len(p) == 4 and p[0] in SEASON_MID:
                rows.append((f"{p[1]}-{SEASON_MID[p[0]]:02d}-01", p[3]))
        run_.rows += upsert_series(con, "noaa:oni", "climate_enso", "Oceanic Nino Index (ENSO)", "Degrees C anomaly", "Monthly", rows, None, "Climate")
        con.commit()


# World Bank indicators for every country. Chosen for scenario work: what a country exports and imports, how exposed its
# finances are, and how stable it is.
WB_MORE = [
    ("NY.GDP.MKTP.CD", "GDP", "Current USD", "Growth"),
    ("NY.GDP.MKTP.KD.ZG", "GDP growth", "Percent", "Growth"),
    ("NY.GDP.PCAP.CD", "GDP per person", "Current USD", "Growth"),
    ("FP.CPI.TOTL.ZG", "Inflation, consumer prices", "Percent", "Inflation"),
    ("SL.UEM.TOTL.ZS", "Unemployment", "Percent", "Labour"),
    ("GC.DOD.TOTL.GD.ZS", "Central government debt", "Percent of GDP", "Fiscal"),
    ("GC.REV.XGRT.GD.ZS", "Government revenue", "Percent of GDP", "Fiscal"),
    ("BN.CAB.XOKA.GD.ZS", "Current account balance", "Percent of GDP", "External"),
    ("NE.TRD.GNFS.ZS", "Trade", "Percent of GDP", "External"),
    ("NE.EXP.GNFS.ZS", "Exports of goods and services", "Percent of GDP", "External"),
    ("NE.IMP.GNFS.ZS", "Imports of goods and services", "Percent of GDP", "External"),
    ("TX.VAL.FUEL.ZS.UN", "Fuel exports", "Percent of merchandise exports", "Energy"),
    ("TM.VAL.FUEL.ZS.UN", "Fuel imports", "Percent of merchandise imports", "Energy"),
    ("TX.VAL.FOOD.ZS.UN", "Food exports", "Percent of merchandise exports", "Commodities"),
    ("TM.VAL.FOOD.ZS.UN", "Food imports", "Percent of merchandise imports", "Commodities"),
    ("TX.VAL.MMTL.ZS.UN", "Ores and metals exports", "Percent of merchandise exports", "Commodities"),
    ("TX.VAL.TECH.MF.ZS", "High technology exports", "Percent of manufactured exports", "External"),
    ("EG.IMP.CONS.ZS", "Net energy imports", "Percent of energy use", "Energy"),
    ("NY.GDP.PETR.RT.ZS", "Oil rents", "Percent of GDP", "Energy"),
    ("NY.GDP.NGAS.RT.ZS", "Natural gas rents", "Percent of GDP", "Energy"),
    ("NY.GDP.MINR.RT.ZS", "Mineral rents", "Percent of GDP", "Commodities"),
    ("NV.AGR.TOTL.ZS", "Agriculture", "Percent of GDP", "Growth"),
    ("NV.IND.MANF.ZS", "Manufacturing", "Percent of GDP", "Growth"),
    ("BX.KLT.DINV.WD.GD.ZS", "Foreign direct investment, net inflows", "Percent of GDP", "External"),
    ("DT.DOD.DECT.CD", "External debt stocks", "Current USD", "External"),
    ("DT.DOD.DSTC.IR.ZS", "Short term debt", "Percent of reserves", "External"),
    ("FI.RES.TOTL.CD", "Total reserves", "Current USD", "External"),
    ("FI.RES.TOTL.MO", "Reserves in months of imports", "Months", "External"),
    ("PA.NUS.FCRF", "Official exchange rate", "Local currency per USD, period average", "FX"),
    ("FR.INR.RINR", "Real interest rate", "Percent", "Rates"),
    ("FS.AST.PRVT.GD.ZS", "Domestic credit to the private sector", "Percent of GDP", "Credit"),
    ("FB.AST.NPER.ZS", "Bank non-performing loans", "Percent of gross loans", "Credit"),
    ("BX.TRF.PWKR.DT.GD.ZS", "Personal remittances received", "Percent of GDP", "External"),
    ("ST.INT.RCPT.CD", "International tourism receipts", "Current USD", "External"),
    ("MS.MIL.XPND.GD.ZS", "Military spending", "Percent of GDP", "Geopolitics"),
    ("MS.MIL.XPND.CD", "Military spending", "Current USD", "Geopolitics"),
    ("SP.POP.TOTL", "Population", "People", "Demographics"),
]
WGI = [
    ("GOV_WGI_PV.EST", "Political stability and absence of violence"),
    ("GOV_WGI_GE.EST", "Government effectiveness"),
    ("GOV_WGI_RQ.EST", "Regulatory quality"),
    ("GOV_WGI_RL.EST", "Rule of law"),
    ("GOV_WGI_CC.EST", "Control of corruption"),
    ("GOV_WGI_VA.EST", "Voice and accountability"),
]


def _wb_countries():
    r = fetch("https://api.worldbank.org/v2/country", params={"format": "json", "per_page": 400})
    return {c["id"]: c["name"] for c in r.json()[1] if c["region"]["id"] != "NA"}


def _wb_indicator(code, source=None):
    page, pages, out = 1, 1, []
    while page <= pages:
        params = {"format": "json", "per_page": 20000, "page": page}
        if source:
            params["source"] = source
        body = fetch(f"https://api.worldbank.org/v2/country/all/indicator/{code}", params=params, timeout=180).json()
        pages = body[0].get("pages", 1)
        out += body[1] or [] if len(body) > 1 else []
        page += 1
    return out


def world_bank(con):
    with Run(con, "worldbank_all") as run_:
        names = _wb_countries()
        for code, label, units, topic in WB_MORE:
            by = {}
            for x in _wb_indicator(code):
                iso = x["countryiso3code"]
                if iso in names:
                    by.setdefault(iso, []).append((f"{x['date']}-12-31", x["value"]))
            for iso, obs in by.items():
                # Military spending comes from SIPRI, which charges for commercial use, so it is kept in its own dataset.
                ds = "macro_military" if code.startswith("MS.MIL") else "macro_world"
                run_.rows += upsert_series(con, f"wdi:{iso}:{code}", ds, f"{names[iso]}: {label}", units, "Annual", obs, names[iso], topic)
            con.commit()
        run_.note(f"{len(names)} economies")


def governance(con):
    with Run(con, "worldbank_wgi") as run_:
        names = _wb_countries()
        for code, label in WGI:
            by = {}
            for x in _wb_indicator(code, source=3):
                iso = x["countryiso3code"]
                if iso in names:
                    by.setdefault(iso, []).append((f"{x['date']}-12-31", x["value"]))
            for iso, obs in by.items():
                run_.rows += upsert_series(con, f"wgi:{iso}:{code[8:10]}", "gov_wgi", f"{names[iso]}: {label}", "Estimate, about -2.5 to 2.5", "Annual", obs, names[iso], "Geopolitics")
            con.commit()


def sec_tickers(con):
    """Every SEC registrant with a ticker and exchange. Replaces the Nasdaq list, whose terms are non-commercial."""
    with Run(con, "sec_tickers") as run_:
        con.execute("""CREATE TABLE IF NOT EXISTS ref_sec_ticker(
            ticker TEXT PRIMARY KEY, cik INTEGER, name TEXT, exchange TEXT, refreshed TEXT)""")
        body = fetch("https://www.sec.gov/files/company_tickers_exchange.json", timeout=120).json()
        today = dt.date.today().isoformat()
        rows = [(r[2], r[0], r[1], r[3], today) for r in body["data"] if r[2]]
        con.execute("DELETE FROM ref_sec_ticker")
        con.executemany("INSERT OR REPLACE INTO ref_sec_ticker VALUES(?,?,?,?,?)", rows)
        con.commit()
        run_.rows += len(rows)


MONTH_NO = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def tic(con):
    """Monthly holdings of US Treasury securities by the largest foreign holders, from the Treasury's TIC system."""
    with Run(con, "treasury_tic") as run_:
        text = fetch("https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/mfhhis01.txt", timeout=120).text
        months, dates, by = None, None, {}
        for line in text.splitlines():
            cells = [c.strip().strip('"') for c in line.split("\t")]
            words = [c for c in cells if c]
            if words and all(w in MONTH_NO for w in words):
                months = words
                continue
            if words and words[0] == "Country" and months and len(words) - 1 == len(months):
                dates = [f"{y}-{MONTH_NO[m]:02d}-01" for m, y in zip(months, words[1:])]
                continue
            if not dates or not cells or not cells[0] or cells[0].startswith(("-", "Grand", "Of which", "Country")) or len(words) < 2:
                continue
            name = re.sub(r"\s*\d+/$", "", cells[0]).strip()
            vals = [c for c in cells[1:] if c != ""]
            if len(vals) != len(dates):
                continue
            by.setdefault(name, []).extend(zip(dates, vals))
        for name, rows in by.items():
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            title = f"Foreign holdings of US Treasuries: {name}" if not name.lower().startswith("all other") and "total" not in name.lower() else f"Foreign holdings of US Treasuries, {name.lower()}"
            run_.rows += upsert_series(con, f"tic:{slug}", "tic_holders", title, "Billions USD", "Monthly", rows, name, "External")
        con.commit()
        run_.note(f"{len(by)} holders")


EIA_INTL = {
    "Crude oil including lease condensate production": ("thousand barrels per day", "Energy"),
    "Petroleum and other liquids production": ("thousand barrels per day", "Energy"),
    "Petroleum and other liquids consumption": ("thousand barrels per day", "Energy"),
    "Refined petroleum products consumption": ("thousand barrels per day", "Energy"),
    "Dry natural gas production": ("billion cubic feet", "Energy"),
    "Dry natural gas consumption": ("billion cubic feet", "Energy"),
    "Dry natural gas exports": ("billion cubic feet", "Energy"),
    "Dry natural gas imports": ("billion cubic feet", "Energy"),
    "Coal production": ("thousand short tons", "Energy"),
    "Coal consumption": ("thousand short tons", "Energy"),
}


def eia_world(con):
    """Oil, gas and coal production and use by country, and who buys crude from whom, from the EIA international bulk file."""
    with Run(con, "eia_world") as run_:
        z = zipfile.ZipFile(io.BytesIO(fetch("https://api.eia.gov/bulk/INTL.zip", timeout=600).content))
        n = 0
        with z.open(z.namelist()[0]) as f:
            for line in f:
                d = json.loads(line)
                sid, name, units, freq = d.get("series_id"), d.get("name", ""), (d.get("units") or "").lower(), d.get("f")
                if not sid or freq not in ("M", "A") or (d.get("copyright") or "None") != "None":
                    continue
                key = name.split(",")[0]
                want = EIA_INTL.get(key)
                if want:
                    if units != want[0]:
                        continue
                    topic = want[1]
                elif "gross imports" in key and units == "thousand barrels per day":
                    topic = "Trade"
                else:
                    continue
                rows = [((f"{p[:4]}-{p[4:6]}-01" if freq == "M" else f"{p[:4]}-12-31"), v) for p, v in d.get("data", [])]
                title = re.sub(r",\s*(Monthly|Annual)$", "", name)
                run_.rows += upsert_series(con, "eiaw:" + sid[5:], "energy_world", title, units, "Monthly" if freq == "M" else "Annual", rows, None, topic)
                n += 1
                if n % 500 == 0:
                    con.commit()
        con.commit()
        run_.note(f"{n} series")


PSD_COMMODITIES = {"Coffee, Green", "Wheat", "Corn", "Oilseed, Soybean", "Rice, Milled", "Sugar, Centrifugal", "Cotton", "Oil, Palm", "Barley", "Meal, Soybean", "Cocoa beans"}
PSD_ATTRS = {"Production", "Exports", "Imports", "Ending Stocks", "Domestic Consumption"}


def crops(con):
    """Production, trade and stocks of the main crops by country and marketing year, from USDA's PSD database."""
    with Run(con, "usda_psd") as run_:
        z = zipfile.ZipFile(io.BytesIO(fetch("https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip", timeout=600).content))
        by, meta = {}, {}
        with z.open(z.namelist()[0]) as f:
            for x in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace")):
                com, attr = x["Commodity_Description"], x["Attribute_Description"]
                if com not in PSD_COMMODITIES or attr not in PSD_ATTRS:
                    continue
                key = (x["Commodity_Code"], x["Country_Code"], attr)
                meta[key] = (com, x["Country_Name"].strip(), x["Unit_Description"].strip("() "))
                by.setdefault(key, []).append((f"{x['Market_Year']}-12-31", x["Value"]))
        for (code, ctry, attr), rows in by.items():
            com, country, unit = meta[(code, ctry, attr)]
            slug = re.sub(r"[^a-z]+", "_", attr.lower()).strip("_")
            run_.rows += upsert_series(con, f"psd:{code}:{ctry}:{slug}", "crops_usda", f"{country}: {com.lower()} {attr.lower()}, marketing year", unit, "Annual", rows, country, "Commodities")
        con.commit()
        run_.note(f"{len(by)} series")


def supply_chain(con):
    """The New York Fed's Global Supply Chain Pressure Index, monthly from 1998."""
    import xlrd
    with Run(con, "nyfed_gscpi") as run_:
        blob = fetch("https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx", timeout=120).content
        book = xlrd.open_workbook(file_contents=blob)
        rows = []
        for sh in book.sheets():
            for i in range(sh.nrows):
                a, b = sh.cell(i, 0), sh.cell(i, 1) if sh.ncols > 1 else None
                if b is None or b.ctype != xlrd.XL_CELL_NUMBER:
                    continue
                if a.ctype == xlrd.XL_CELL_DATE:
                    day = xlrd.xldate_as_datetime(a.value, book.datemode).date()
                else:
                    try:
                        day = dt.datetime.strptime(str(a.value).strip(), "%d-%b-%Y").date()
                    except ValueError:
                        continue
                rows.append((day.replace(day=1).isoformat(), b.value))
            if rows:
                break
        run_.rows += upsert_series(con, "nyfed:gscpi", "supply_gscpi", "Global Supply Chain Pressure Index", "Standard deviations from average", "Monthly", rows, None, "Trade")
        con.commit()

PW_METRICS = {"n_total": "all vessels", "n_tanker": "tankers", "n_container": "container ships", "n_dry_bulk": "dry bulk carriers",
              "capacity": "capacity, all vessels", "capacity_tanker": "capacity, tankers"}


def chokepoints(con):
    """Daily vessel transits and cargo capacity through 28 maritime chokepoints, such as Hormuz, Suez and Malacca, from 2019."""
    with Run(con, "imf_portwatch") as run_:
        url = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
        offset, by, names = 0, {}, {}
        while True:
            body = fetch(url, params={"where": "1=1", "outFields": "*", "f": "json", "orderByFields": "ObjectId", "resultOffset": offset, "resultRecordCount": 2000}, timeout=120).json()
            feats = body.get("features", [])
            for ft in feats:
                a = ft["attributes"]
                d = a.get("date")
                day = dt.datetime.fromtimestamp(d / 1000, dt.timezone.utc).date().isoformat() if isinstance(d, (int, float)) else str(d)[:10]
                names[a["portid"]] = a["portname"]
                for k in PW_METRICS:
                    if a.get(k) is not None:
                        by.setdefault((a["portid"], k), []).append((day, a[k]))
            offset += len(feats)
            if not feats or not body.get("exceededTransferLimit"):
                break
        for (pid, k), rows in by.items():
            units = "Metric tonnes" if k.startswith("capacity") else "Vessels per day"
            run_.rows += upsert_series(con, f"pw:{pid}:{k}", "trade_chokepoints", f"{names[pid]} transits, {PW_METRICS[k]}", units, "Daily", rows, None, "Trade")
        con.commit()
        run_.note(f"{len(names)} chokepoints, {offset:,} records")


def _sanction_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS geo_sanction_list(
        list TEXT, ref TEXT, name TEXT, kind TEXT, regime TEXT, listed TEXT, country TEXT, PRIMARY KEY(list, ref)) WITHOUT ROWID""")


def _put(con, lst, rows):
    con.execute("DELETE FROM geo_sanction_list WHERE list=?", (lst,))
    con.executemany("INSERT OR REPLACE INTO geo_sanction_list VALUES(?,?,?,?,?,?,?)", [(lst, *r) for r in rows])
    con.commit()
    return len(rows)


def sanctions_un(con):
    with Run(con, "sanctions_un") as run_:
        _sanction_table(con)
        root = ET.fromstring(fetch("https://scsanctions.un.org/resources/xml/en/consolidated.xml", timeout=120).content)
        rows = []
        for kind, tag in (("Individual", "INDIVIDUAL"), ("Entity", "ENTITY")):
            for el in root.iter(tag):
                g = lambda t: (el.findtext(t) or "").strip()
                name = " ".join(x for x in (g("FIRST_NAME"), g("SECOND_NAME"), g("THIRD_NAME"), g("FOURTH_NAME")) if x)
                nat = el.find("NATIONALITY/VALUE")
                rows.append((g("REFERENCE_NUMBER") or g("DATAID"), name, kind, g("UN_LIST_TYPE"), g("LISTED_ON")[:10], (nat.text or "").strip() if nat is not None else None))
        run_.rows += _put(con, "UN", rows)


def sanctions_uk(con):
    with Run(con, "sanctions_uk") as run_:
        _sanction_table(con)
        text = fetch("https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.csv", timeout=300).content.decode("utf-8-sig", "replace")
        lines = text.splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("Last Updated,"))
        rows = {}
        for x in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
            if (x.get("Name type") or "").lower().startswith("primary"):
                name = " ".join(v for v in (x.get(f"Name {i}", "").strip() for i in (1, 2, 3, 4, 5, 6)) if v)
                raw = (x.get("Date Designated") or "")[:10]
                when = f"{raw[6:10]}-{raw[3:5]}-{raw[0:2]}" if re.fullmatch(r"\d\d/\d\d/\d{4}", raw) else raw or None
                rows[x["Unique ID"]] = (name, x.get("Designation Type"), x.get("Regime Name"), when, x.get("Nationality(/ies)") or x.get("Address Country") or None)
        run_.rows += _put(con, "UK", [(k, *v) for k, v in rows.items()])


def sanctions_eu(con):
    with Run(con, "sanctions_eu") as run_:
        _sanction_table(con)
        r = fetch("https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content", params={"token": "dG9rZW4tMjAxNw"}, timeout=300)
        rows = {}
        for x in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", "replace")), delimiter=";"):
            ref, name = x["Entity_LogicalId"], x.get("NameAlias_WholeName", "").strip()
            cur = rows.get(ref)
            kind = {"P": "Individual", "E": "Entity"}.get(x.get("Entity_SubjectType"), x.get("Entity_SubjectType"))
            country = x.get("Citizenship_CountryDescription") or x.get("Address_CountryDescription") or None
            if not cur:
                rows[ref] = [name, kind, x.get("Entity_Regulation_Programme"), x.get("Entity_Regulation_PublicationDate"), country]
            else:
                cur[0] = cur[0] or name
                cur[4] = cur[4] or country
        run_.rows += _put(con, "EU", [(k, *v) for k, v in rows.items()])


def run(con):
    for step in (fed_fx, fed_rates, earthquakes, enso, world_bank, governance, tic):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
