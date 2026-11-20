"""Primary sources for series that were only held through FRED. Terms read on 6 November 2026.

US Treasury and Fiscal Data allow commercial use, and Federal Reserve Board data is public domain.
Freddie Mac allows use with attribution. Spreads and breakevens are computed here from Treasury yields.
"""
import csv
import datetime as dt
import io
import xml.etree.ElementTree as ET
import zipfile

from core import Run, fetch, upsert_series

US = "United States"
# Release, series code, id, title, units, frequency, topic
FED = [
    ("H15", "RIFSPFF_N.B", "effr", "Effective federal funds rate, business days", "Percent", "Daily", "Policy"),
    ("H6", "M1.M", "m1", "US M1 money stock", "Billions USD", "Monthly", "Policy"),
    ("H6", "M2.M", "m2", "US M2 money stock", "Billions USD", "Monthly", "Policy"),
    ("H41", "RESPPA_N.WW", "assets", "Federal Reserve total assets", "Millions USD", "Weekly", "Policy"),
    ("H41", "RESH4R_N.WW", "reserves", "Reserve balances at Federal Reserve Banks", "Millions USD", "Weekly", "Policy"),
    ("H41", "RESPPLLR_N.WW", "rrp", "Federal Reserve reverse repurchase agreements", "Millions USD", "Weekly", "Policy"),
    ("H10", "JRXWTFB_N.B", "usd_broad", "Nominal broad US dollar index", "Index", "Daily", "FX"),
    ("H10", "JRXWTFN_N.B", "usd_afe", "Nominal US dollar index, advanced economies", "Index", "Daily", "FX"),
    ("H10", "JRXWTFO_N.B", "usd_eme", "Nominal US dollar index, emerging economies", "Index", "Daily", "FX"),
    ("G17", "IP.B50001.S", "ip", "US industrial production", "Index 2017=100", "Monthly", "Growth"),
    ("G17", "IP.B00004.S", "ip_mfg", "US manufacturing production", "Index 2017=100", "Monthly", "Growth"),
    ("G17", "CAPUTL.B50001.S", "caputl", "US capacity utilisation", "Percent", "Monthly", "Growth"),
]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _sdmx(blob, wanted):
    """Reads only the wanted series from a Federal Reserve SDMX zip."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in z.namelist() if n.lower().endswith("_data.xml"))
    out, cur = {}, None
    with z.open(name) as f:
        for ev, el in ET.iterparse(f, events=("start", "end")):
            tag = el.tag.rsplit("}", 1)[-1]
            if ev == "start" and tag == "Series":
                code = el.attrib.get("SERIES_NAME")
                cur = [] if code in wanted and code not in out else None
                if cur is not None:
                    out[code] = cur
            elif ev == "end" and tag == "Obs":
                if cur is not None and el.attrib.get("OBS_STATUS", "A") == "A":
                    cur.append((el.attrib["TIME_PERIOD"], el.attrib.get("OBS_VALUE")))
                el.clear()
            elif ev == "end" and tag == "Series":
                cur = None
                el.clear()
    return out


def federal_reserve(con):
    with Run(con, "fed_board") as run_:
        for rel in sorted({x[0] for x in FED}):
            series = [x for x in FED if x[0] == rel]
            r = fetch("https://www.federalreserve.gov/datadownload/Output.aspx", params={"rel": rel, "filetype": "zip"}, timeout=300)
            got = _sdmx(r.content, {x[1] for x in series})
            for _, code, sid, title, units, freq, topic in series:
                rows = got.get(code) or []
                if not rows:
                    run_.note(f"{rel} {code}: no observations")
                    continue
                if freq == "Monthly":
                    rows = [(d[:8] + "01", v) for d, v in rows]
                run_.rows += upsert_series(con, f"frb:{sid}", "macro_fed", title, units, freq, rows, US, topic)
            con.commit()


def _treasury_csv(kind, first_year):
    for year in range(first_year, dt.date.today().year + 1):
        r = fetch(
            f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all",
            params={"type": kind, "field_tdr_date_value": year, "page": "", "_format": "csv"},
        )
        yield from csv.DictReader(io.StringIO(r.text))


def treasury_curves(con):
    with Run(con, "treasury_curves") as run_:
        real, bills = {}, {}
        for row in _treasury_csv("daily_treasury_real_yield_curve", 2003):
            d = dt.datetime.strptime(row.pop("Date"), "%m/%d/%Y").date().isoformat()
            for tenor, v in row.items():
                real.setdefault(tenor.lower().replace(" ", ""), []).append((d, v))
        for row in _treasury_csv("daily_treasury_bill_rates", 2002):
            d = dt.datetime.strptime(row.pop("Date"), "%m/%d/%Y").date().isoformat()
            for col, v in row.items():
                if "COUPON" in col.upper():
                    bills.setdefault(col.split()[0], []).append((d, v))
        for tenor, rows in real.items():
            run_.rows += upsert_series(con, f"ust:real_{tenor}", "rates_treasury", f"US Treasury {tenor} real yield", "Percent", "Daily", rows, US, "Rates")
        for weeks, rows in bills.items():
            run_.rows += upsert_series(con, f"ust:bill_{weeks}wk", "rates_treasury", f"US Treasury {weeks} week bill, coupon equivalent", "Percent", "Daily", rows, US, "Rates")
        con.commit()


def _difference(con, a, b):
    return con.execute("SELECT x.date, round(x.value-y.value, 4) FROM ts_obs x JOIN ts_obs y ON y.date=x.date AND y.series_id=? WHERE x.series_id=? ORDER BY 1", (b, a)).fetchall()


def treasury_spreads(con):
    with Run(con, "treasury_spreads") as run_:
        for sid, a, b, title, topic in [
            ("spread_10y2y", "ust:10yr", "ust:2yr", "US 10 year minus 2 year spread", "Rates"),
            ("spread_10y3m", "ust:10yr", "ust:3mo", "US 10 year minus 3 month spread", "Rates"),
            ("breakeven_5y", "ust:5yr", "ust:real_5yr", "US 5 year breakeven inflation", "Inflation"),
            ("breakeven_10y", "ust:10yr", "ust:real_10yr", "US 10 year breakeven inflation", "Inflation"),
        ]:
            rows = [(r[0], r[1]) for r in _difference(con, a, b)]
            if not rows:
                run_.note(f"{sid}: no overlap between {a} and {b}")
            run_.rows += upsert_series(con, f"ust:{sid}", "rates_treasury", title, "Percent", "Daily", rows, US, topic)
        con.commit()


def _fiscal(path, **params):
    page, out = 1, []
    while True:
        q = {"page[size]": 10000, "page[number]": page, **params}
        body = fetch(f"https://api.fiscaldata.treasury.gov/services/api/fiscal_service/{path}", params=q, timeout=120).json()
        out += body["data"]
        if page >= int(body["meta"]["total-pages"]):
            return out
        page += 1


def fiscal(con):
    with Run(con, "fiscal_data") as run_:
        debt = _fiscal("v2/accounting/od/debt_to_penny", fields="record_date,tot_pub_debt_out_amt,debt_held_public_amt")
        run_.rows += upsert_series(con, "fiscal:debt_total", "fiscal_us", "US total public debt outstanding", "USD", "Daily",
                                   [(x["record_date"], x["tot_pub_debt_out_amt"]) for x in debt], US, "Fiscal")
        run_.rows += upsert_series(con, "fiscal:debt_public", "fiscal_us", "US debt held by the public", "USD", "Daily",
                                   [(x["record_date"], x["debt_held_public_amt"]) for x in debt], US, "Fiscal")
        rows, year = {}, {}
        table = _fiscal("v1/accounting/mts/mts_table_1")
        for x in table:
            if x["classification_desc"] == f"FY {x['record_fiscal_year']}":
                year[x["record_date"]] = x["classification_id"]
        for x in table:
            d = x["record_date"]
            if x["record_type_cd"] == "MTH" and x["parent_id"] == year.get(d) and x["classification_desc"] == MONTHS[int(d[5:7]) - 1]:
                rows[d[:8] + "01"] = x["current_month_dfct_sur_amt"]
        # Treasury reports a deficit as a positive number and a surplus as a negative one.
        run_.rows += upsert_series(con, "fiscal:deficit_month", "fiscal_us", "US monthly federal deficit", "USD, positive is a deficit", "Monthly", sorted(rows.items()), US, "Fiscal")
        con.commit()


def mortgage(con):
    with Run(con, "freddie_pmms") as run_:
        r = fetch("https://www.freddiemac.com/pmms/docs/PMMS_history.csv", timeout=60)
        cols = {"pmms30": [], "pmms15": []}
        for row in csv.DictReader(io.StringIO(r.text)):
            d = dt.datetime.strptime(row["date"].strip(), "%m/%d/%Y").date().isoformat()
            for k, v in cols.items():
                v.append((d, (row.get(k) or "").strip()))
        run_.rows += upsert_series(con, "pmms:30y", "rates_pmms", "US 30 year fixed mortgage rate", "Percent", "Weekly", cols["pmms30"], US, "Housing")
        run_.rows += upsert_series(con, "pmms:15y", "rates_pmms", "US 15 year fixed mortgage rate", "Percent", "Weekly", cols["pmms15"], US, "Housing")
        con.commit()


def run(con):
    for step in (treasury_curves, treasury_spreads, federal_reserve, fiscal, mortgage):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
