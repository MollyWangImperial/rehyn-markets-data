"""Open replacements and additions: BLS series direct from the agency, and SEC 13F fund holdings."""
import csv
import datetime as dt
import io
import re
import zipfile

from bs4 import BeautifulSoup

from core import Run, fetch, upsert_series

BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS = {
    "CUSR0000SA0": ("US CPI, all items", "Index 1982-84=100", "Inflation"),
    "CUSR0000SA0L1E": ("US core CPI", "Index 1982-84=100", "Inflation"),
    "WPU00000000": ("US producer price index, all commodities", "Index 1982=100", "Inflation"),
    "LNS14000000": ("US unemployment rate", "Percent", "Labour"),
    "CES0000000001": ("US nonfarm payrolls", "Thousands", "Labour"),
    "LNS11300000": ("US labour force participation", "Percent", "Labour"),
    "CES0500000003": ("US average hourly earnings", "USD per hour", "Labour"),
    "JTS000000000000000JOL": ("US job openings (JOLTS)", "Thousands", "Labour"),
    "CUSR0000SA0E": ("US CPI, energy", "Index 1982-84=100", "Inflation"),
    "CUSR0000SAF11": ("US CPI, food at home", "Index 1982-84=100", "Inflation"),
    "CUSR0000SAH1": ("US CPI, shelter", "Index 1982-84=100", "Inflation"),
    "CUSR0000SETB01": ("US CPI, gasoline", "Index 1982-84=100", "Inflation"),
    "CUSR0000SAS": ("US CPI, services", "Index 1982-84=100", "Inflation"),
    "EIUIR": ("US import price index, all imports", "Index 2000=100", "Inflation"),
    "EIUIR10": ("US import price index, fuels and lubricants", "Index 2000=100", "Inflation"),
    "EIUIQ": ("US export price index, all exports", "Index 2000=100", "Inflation"),
    "LNS13327709": ("US U-6 underemployment rate", "Percent", "Labour"),
    "CES3000000001": ("US manufacturing employment", "Thousands", "Labour"),
}

# Managers whose 13F filings are widely followed. Names match the filing manager field.
MANAGERS = ["BERKSHIRE HATHAWAY", "BRIDGEWATER", "RENAISSANCE TECHNOLOGIES", "CITADEL ADVISORS", "SOROS FUND", "PERSHING SQUARE", "TIGER GLOBAL", "DUQUESNE FAMILY", "SCION ASSET",
           "BAUPOST", "APPALOOSA", "THIRD POINT", "GREENLIGHT", "COATUE", "VANGUARD GROUP", "BLACKROCK", "STATE STREET", "FMR LLC", "MILLENNIUM MANAGEMENT", "TWO SIGMA"]


def bls(con, first_year=1948):
    with Run(con, "bls") as run_:
        this_year = dt.date.today().year
        by = {}
        for start in range(first_year, this_year + 1, 10):
            end = min(start + 9, this_year)
            r = _post(BLS_URL, {"seriesid": list(BLS), "startyear": str(start), "endyear": str(end)})
            body = r.json()
            if body.get("status") != "REQUEST_SUCCEEDED":
                run_.note(f"{start}: {body.get('message')}")
                continue
            for s in body["Results"]["series"]:
                for x in s["data"]:
                    if re.fullmatch(r"M(0[1-9]|1[0-2])", x["period"]):
                        by.setdefault(s["seriesID"], []).append((f"{x['year']}-{x['period'][1:]}-01", x["value"]))
        for code, rows in by.items():
            title, units, topic = BLS[code]
            run_.rows += upsert_series(con, f"bls:{code}", "macro_bls", title, units, "Monthly", rows, "United States", topic)
        con.commit()


def _post(url, payload):
    import requests

    from core import BOT_UA
    r = requests.post(url, json=payload, headers={"User-Agent": BOT_UA}, timeout=60)
    r.raise_for_status()
    return r


def _iso(raw):
    try:
        return dt.datetime.strptime(raw, "%d-%b-%Y").date().isoformat()
    except (TypeError, ValueError):
        return raw


def _tsv(z, part):
    name = next(n for n in z.namelist() if n.upper().endswith(part))
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t")


def holdings(con, quarters=2):
    with Run(con, "sec_13f") as run_:
        con.execute("""CREATE TABLE IF NOT EXISTS co_fund_holding(
            manager TEXT, filed TEXT, period TEXT, issuer TEXT, title TEXT, shares REAL, value_usd REAL,
            PRIMARY KEY(manager, period, issuer, title)) WITHOUT ROWID""")
        page = fetch("https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets").text
        links = [a["href"] for a in BeautifulSoup(page, "lxml").find_all("a", href=True) if a["href"].endswith("_form13f.zip")]
        for href in links[:quarters]:
            url = href if href.startswith("http") else "https://www.sec.gov" + href
            r = fetch(url, timeout=300)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            wanted = {}
            for x in _tsv(z, "COVERPAGE.TSV"):
                name = (x.get("FILINGMANAGER_NAME") or "").upper()
                hit = next((m for m in MANAGERS if m in name), None)
                if hit:
                    wanted[x["ACCESSION_NUMBER"]] = [name, _iso(x.get("REPORTCALENDARORQUARTER"))]
            for x in _tsv(z, "SUBMISSION.TSV"):
                if x["ACCESSION_NUMBER"] in wanted:
                    wanted[x["ACCESSION_NUMBER"]].append(_iso(x.get("FILING_DATE")))
            totals = {}
            for x in _tsv(z, "INFOTABLE.TSV"):
                meta = wanted.get(x["ACCESSION_NUMBER"])
                if not meta or len(meta) < 3:
                    continue
                key = (meta[0], meta[2], meta[1], x.get("NAMEOFISSUER"), x.get("TITLEOFCLASS"))
                cur = totals.setdefault(key, [0.0, 0.0])
                cur[0] += float(x.get("SSHPRNAMT") or 0)
                cur[1] += float(x.get("VALUE") or 0)
            rows = [(*k, *v) for k, v in totals.items()]
            con.executemany("INSERT OR REPLACE INTO co_fund_holding VALUES(?,?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)
            run_.note(f"{url.rsplit('/', 1)[-1]}: {len(wanted)} filings, {len(rows)} holdings")


def run(con):
    for step in (bls, holdings):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
