"""Time series: macro, rates, FX reference rates, spot commodities, risk indices and research factors."""
import csv
import datetime as dt
import io
import re
import zipfile

import openpyxl
import xlrd

from core import Run, fetch, restricted, upsert_series

# FRED code, title, units, frequency, topic
FRED = [
    ("CPIAUCSL", "US CPI, all items", "Index 1982-84=100", "Monthly", "Inflation"),
    ("CPILFESL", "US core CPI", "Index 1982-84=100", "Monthly", "Inflation"),
    ("PCEPI", "US PCE price index", "Index 2017=100", "Monthly", "Inflation"),
    ("PCEPILFE", "US core PCE price index", "Index 2017=100", "Monthly", "Inflation"),
    ("PPIACO", "US producer price index, all commodities", "Index 1982=100", "Monthly", "Inflation"),
    ("T5YIE", "US 5 year breakeven inflation", "Percent", "Daily", "Inflation"),
    ("T10YIE", "US 10 year breakeven inflation", "Percent", "Daily", "Inflation"),
    ("UNRATE", "US unemployment rate", "Percent", "Monthly", "Labour"),
    ("PAYEMS", "US nonfarm payrolls", "Thousands", "Monthly", "Labour"),
    ("ICSA", "US initial jobless claims", "Claims", "Weekly", "Labour"),
    ("CIVPART", "US labour force participation", "Percent", "Monthly", "Labour"),
    ("JTSJOL", "US job openings (JOLTS)", "Thousands", "Monthly", "Labour"),
    ("CES0500000003", "US average hourly earnings", "USD per hour", "Monthly", "Labour"),
    ("GDPC1", "US real GDP", "Billions of chained 2017 USD", "Quarterly", "Growth"),
    ("INDPRO", "US industrial production", "Index 2017=100", "Monthly", "Growth"),
    ("RSAFS", "US retail sales", "Millions USD", "Monthly", "Growth"),
    ("HOUST", "US housing starts", "Thousands", "Monthly", "Housing"),
    ("CSUSHPINSA", "Case-Shiller US home price index", "Index Jan 2000=100", "Monthly", "Housing"),
    ("MORTGAGE30US", "US 30 year mortgage rate", "Percent", "Weekly", "Housing"),
    ("UMCSENT", "University of Michigan consumer sentiment", "Index 1966=100", "Monthly", "Sentiment"),
    ("USREC", "NBER US recession indicator", "1 = recession", "Monthly", "Growth"),
    ("FEDFUNDS", "Effective federal funds rate, monthly", "Percent", "Monthly", "Policy"),
    ("DFF", "Effective federal funds rate, daily", "Percent", "Daily", "Policy"),
    ("DFEDTARU", "Fed funds target, upper limit", "Percent", "Daily", "Policy"),
    ("DFEDTARL", "Fed funds target, lower limit", "Percent", "Daily", "Policy"),
    ("DFEDTAR", "Fed funds target, single rate to 2008", "Percent", "Daily", "Policy"),
    ("WALCL", "Federal Reserve total assets", "Millions USD", "Weekly", "Policy"),
    ("M2SL", "US M2 money stock", "Billions USD", "Monthly", "Policy"),
    ("RRPONTSYD", "Fed overnight reverse repo", "Billions USD", "Daily", "Policy"),
    ("T10Y2Y", "US 10 year minus 2 year spread", "Percent", "Daily", "Rates"),
    ("T10Y3M", "US 10 year minus 3 month spread", "Percent", "Daily", "Rates"),
    ("DFII10", "US 10 year real yield", "Percent", "Daily", "Rates"),
    ("BAMLH0A0HYM2", "US high yield credit spread", "Percent", "Daily", "Credit"),
    ("BAMLC0A0CM", "US investment grade credit spread", "Percent", "Daily", "Credit"),
    ("NFCI", "Chicago Fed financial conditions", "Index", "Weekly", "Credit"),
    ("STLFSI4", "St. Louis Fed financial stress", "Index", "Weekly", "Credit"),
    ("DTWEXBGS", "Trade weighted US dollar, broad", "Index Jan 2006=100", "Daily", "FX"),
    ("GFDEGDQ188S", "US federal debt to GDP", "Percent", "Quarterly", "Fiscal"),
    ("FYFSD", "US federal surplus or deficit", "Millions USD", "Annual", "Fiscal"),
    ("USEPUINDXD", "US economic policy uncertainty, daily", "Index", "Daily", "Risk"),
]

# EIA spot price file code, title, units
EIA = [
    ("RBRTEd", "Europe Brent spot price", "USD per barrel"),
    ("RWTCd", "Cushing WTI spot price", "USD per barrel"),
    ("RNGWHHDd", "Henry Hub natural gas spot price", "USD per MMBtu"),
    ("EER_EPMRU_PF4_RGC_DPGd", "US Gulf Coast gasoline spot price", "USD per gallon"),
    ("EER_EPD2F_PF4_Y35NY_DPGd", "New York Harbor heating oil spot price", "USD per gallon"),
    # Weekly supply and storage, for supply shock scenarios.
    ("WCESTUS1w", "US commercial crude oil stocks, excluding the SPR", "Thousand barrels"),
    ("WCSSTUS1w", "US Strategic Petroleum Reserve stocks", "Thousand barrels"),
    ("WGTSTUS1w", "US total motor gasoline stocks", "Thousand barrels"),
    ("WDISTUS1w", "US distillate fuel oil stocks", "Thousand barrels"),
    ("WCRFPUS2w", "US field production of crude oil", "Thousand barrels per day"),
    ("WCRIMUS2w", "US crude oil imports", "Thousand barrels per day"),
    ("WCREXUS2w", "US crude oil exports", "Thousand barrels per day"),
    ("WPULEUS3w", "US refinery utilisation", "Percent"),
    ("WRPUPUS2w", "US product supplied, total petroleum", "Thousand barrels per day"),
    ("NW2_EPG0_SWO_R48_BCFw", "US working gas in underground storage, Lower 48", "Billion cubic feet"),
]

WB_INDICATORS = [
    ("NY.GDP.MKTP.CD", "GDP", "Current USD", "Growth"),
    ("NY.GDP.MKTP.KD.ZG", "GDP growth", "Percent", "Growth"),
    ("FP.CPI.TOTL.ZG", "Inflation, consumer prices", "Percent", "Inflation"),
    ("SL.UEM.TOTL.ZS", "Unemployment", "Percent", "Labour"),
    ("GC.DOD.TOTL.GD.ZS", "Central government debt", "Percent of GDP", "Fiscal"),
    ("BN.CAB.XOKA.GD.ZS", "Current account balance", "Percent of GDP", "External"),
    ("NE.TRD.GNFS.ZS", "Trade", "Percent of GDP", "External"),
    ("FI.RES.TOTL.CD", "Total reserves", "Current USD", "External"),
    ("SP.POP.TOTL", "Population", "People", "Demographics"),
]
WB_COUNTRIES = {
    "USA": "United States", "CHN": "China", "JPN": "Japan", "DEU": "Germany", "GBR": "United Kingdom", "FRA": "France",
    "ITA": "Italy", "ESP": "Spain", "CAN": "Canada", "AUS": "Australia", "KOR": "South Korea", "IND": "India",
    "BRA": "Brazil", "COL": "Colombia", "MEX": "Mexico", "ARG": "Argentina", "RUS": "Russia", "UKR": "Ukraine",
    "TUR": "Turkey", "SAU": "Saudi Arabia", "ARE": "United Arab Emirates", "IRN": "Iran", "IRQ": "Iraq", "ISR": "Israel",
    "EGY": "Egypt", "ZAF": "South Africa", "NGA": "Nigeria", "IDN": "Indonesia", "VNM": "Vietnam", "POL": "Poland",
    "NOR": "Norway", "CHE": "Switzerland", "NLD": "Netherlands", "SWE": "Sweden", "VEN": "Venezuela", "PAK": "Pakistan",
}


@restricted("FRED's terms bar commercial use and website display without written consent")
def fred(con):
    with Run(con, "fred") as run_:
        failed = []
        for code, title, units, freq, topic in FRED:
            try:
                r = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": code}, timeout=45, retries=3)
            except Exception:
                failed.append(code)
                continue
            rows = list(csv.reader(io.StringIO(r.text)))[1:]
            run_.rows += upsert_series(con, f"fred:{code}", "macro_us", title, units, freq, rows, "United States", topic)
            con.commit()
        if failed:
            run_.note(f"not fetched: {', '.join(failed)}")


def treasury(con):
    with Run(con, "treasury") as run_:
        this_year = dt.date.today().year
        cols = {}
        for year in range(1990, this_year + 1):
            r = fetch(
                f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all",
                params={"type": "daily_treasury_yield_curve", "field_tdr_date_value": year, "page": "", "_format": "csv"},
            )
            for row in csv.DictReader(io.StringIO(r.text)):
                d = dt.datetime.strptime(row.pop("Date"), "%m/%d/%Y").date().isoformat()
                for tenor, v in row.items():
                    cols.setdefault(tenor, []).append((d, v))
        for tenor, rows in cols.items():
            slug = tenor.lower().replace(" ", "").replace(".", "_")
            run_.rows += upsert_series(con, f"ust:{slug}", "rates_treasury", f"US Treasury {tenor} par yield", "Percent",
                                       "Daily", rows, "United States", "Rates")
        con.commit()


def ecb_fx(con):
    with Run(con, "ecb_fx") as run_:
        r = fetch("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        text = z.read(z.namelist()[0]).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        cols = {}
        for row in reader:
            d = row.pop("Date")
            for cur, v in row.items():
                if cur and v not in ("N/A", "", None):
                    cols.setdefault(cur.strip(), []).append((d, v))
        for cur, rows in cols.items():
            run_.rows += upsert_series(con, f"ecb:{cur}", "fx_ecb", f"Euro reference rate, {cur} per euro", f"{cur} per EUR",
                                       "Daily", rows, "Eurozone", "FX")
        con.commit()


def eia(con):
    with Run(con, "eia") as run_:
        for code, title, units in EIA:
            folder = "ng" if code.startswith(("RNG", "NW2")) else "pet"
            try:
                r = fetch(f"https://www.eia.gov/dnav/{folder}/hist_xls/{code}.xls")
            except RuntimeError as e:
                run_.note(f"{code}: {e}")
                continue
            book = xlrd.open_workbook(file_contents=r.content)
            sheet = book.sheet_by_name("Data 1")
            rows = []
            for i in range(3, sheet.nrows):
                cell, val = sheet.cell(i, 0), sheet.cell(i, 1).value
                if cell.ctype == xlrd.XL_CELL_DATE and val != "":
                    rows.append((xlrd.xldate_as_datetime(cell.value, book.datemode).date().isoformat(), val))
            run_.rows += upsert_series(con, f"eia:{code}", "commodity_eia", title, units, "Weekly" if code.endswith("w") else "Daily", rows, "United States" if code.endswith("w") else None, "Energy")
        con.commit()


def worldbank_pink(con):
    with Run(con, "worldbank_pink") as run_:
        page = fetch("https://www.worldbank.org/en/research/commodity-markets").text
        m = re.search(r'https://thedocs\.worldbank\.org/[^"\']+CMO-Historical-Data-Monthly\.xlsx', page)
        url = m.group(0) if m else (
            "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx")
        r = fetch(url)
        wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True, data_only=True)
        rows = list(wb["Monthly Prices"].iter_rows(values_only=True))
        head = next(i for i, x in enumerate(rows) if x[0] is None and x[1] is not None)
        names, units = rows[head], rows[head + 1]
        data = [x for x in rows[head + 2:] if x[0] and re.match(r"\d{4}M\d{2}", str(x[0]))]
        for c in range(1, len(names)):
            if not names[c]:
                continue
            title = re.sub(r"\s+", " ", str(names[c])).strip()
            sid = "wb:" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
            obs = [(f"{str(x[0])[:4]}-{str(x[0])[5:7]}-01", x[c]) for x in data]
            run_.rows += upsert_series(con, sid, "commodity_worldbank", title, str(units[c] or "").strip("() "), "Monthly", obs, None, "Commodities")
        con.commit()


def worldbank_indicators(con):
    with Run(con, "worldbank_indicators") as run_:
        codes = ";".join(WB_COUNTRIES)
        for code, label, units, topic in WB_INDICATORS:
            page, pages, by = 1, 1, {}
            while page <= pages:
                r = fetch(f"https://api.worldbank.org/v2/country/{codes}/indicator/{code}",
                          params={"format": "json", "per_page": 5000, "page": page})
                meta, rows = r.json()[0], r.json()[1] if len(r.json()) > 1 else None
                pages = meta.get("pages", 1)
                for x in rows or []:
                    by.setdefault(x["countryiso3code"], []).append((f"{x['date']}-12-31", x["value"]))
                page += 1
            for iso, obs in by.items():
                country = WB_COUNTRIES.get(iso, iso)
                run_.rows += upsert_series(con, f"wdi:{iso}:{code}", "macro_world", f"{country}: {label}", units, "Annual", obs, country, topic)
            con.commit()


@restricted("Cboe requires a signed licence for any use of its data")
def cboe_vix(con):
    with Run(con, "cboe_vix") as run_:
        r = fetch("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv")
        rows = [(dt.datetime.strptime(x["DATE"], "%m/%d/%Y").date().isoformat(), x["CLOSE"]) for x in csv.DictReader(io.StringIO(r.text))]
        run_.rows += upsert_series(con, "cboe:VIX", "vol_cboe", "Cboe VIX close", "Index", "Daily", rows, "United States", "Volatility")
        con.commit()


def gpr(con):
    with Run(con, "gpr") as run_:
        r = fetch("https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls")
        book = xlrd.open_workbook(file_contents=r.content)
        s = book.sheet_by_index(0)
        head = [str(s.cell_value(0, c)).strip() for c in range(s.ncols)]
        want = {"GPRD": "Geopolitical Risk index, daily", "GPRD_ACT": "Geopolitical acts index, daily", "GPRD_THREAT": "Geopolitical threats index, daily"}
        date_col = head.index("date") if "date" in head else 0
        for col, title in want.items():
            if col not in head:
                continue
            c = head.index(col)
            rows = []
            for i in range(1, s.nrows):
                cell = s.cell(i, date_col)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    d = xlrd.xldate_as_datetime(cell.value, book.datemode).date().isoformat()
                else:
                    raw = str(int(cell.value)) if cell.ctype == xlrd.XL_CELL_NUMBER else str(cell.value)
                    d = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else None
                rows.append((d, s.cell_value(i, c)))
            run_.rows += upsert_series(con, f"gpr:{col}", "risk_gpr", title, "Index", "Daily", rows, None, "Geopolitics")
        r = fetch("https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls")
        book = xlrd.open_workbook(file_contents=r.content)
        s = book.sheet_by_index(0)
        head = [str(s.cell_value(0, c)).strip() for c in range(s.ncols)]
        for c, name in enumerate(head):
            if not name.startswith("GPRC_") and name not in ("GPR", "GPRT", "GPRA", "GPRH"):
                continue
            rows = []
            for i in range(1, s.nrows):
                cell = s.cell(i, 0)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    rows.append((xlrd.xldate_as_datetime(cell.value, book.datemode).date().isoformat(), s.cell_value(i, c)))
            code = name.replace("GPRC_", "")
            title = f"Geopolitical Risk index, {code}" if name.startswith("GPRC_") else f"Geopolitical Risk index, monthly {name}"
            run_.rows += upsert_series(con, f"gpr:{name}", "risk_gpr", title, "Index", "Monthly", rows, None, "Geopolitics")
        con.commit()


def epu(con):
    with Run(con, "epu") as run_:
        r = fetch("https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv")
        rows = []
        for x in csv.DictReader(io.StringIO(r.text)):
            try:
                rows.append((f"{int(x['year']):04d}-{int(x['month']):02d}-{int(x['day']):02d}", x["daily_policy_index"]))
            except (KeyError, ValueError):
                continue
        run_.rows += upsert_series(con, "epu:US_daily", "risk_epu", "US Economic Policy Uncertainty, daily news index", "Index", "Daily", rows, "United States", "Policy risk")
        con.commit()


def french(con):
    with Run(con, "french") as run_:
        base = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
        files = {
            "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip": ("ff5", ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]),
            "F-F_Momentum_Factor_daily_CSV.zip": ("mom", ["Mom"]),
        }
        names = {"Mkt-RF": "Market minus risk free", "SMB": "Size", "HML": "Value", "RMW": "Profitability", "CMA": "Investment", "RF": "Risk free rate", "Mom": "Momentum"}
        for fname, (tag, wanted) in files.items():
            r = fetch(base + fname)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            text = z.read(z.namelist()[0]).decode("latin-1")
            cols, header = {}, None
            for line in text.splitlines():
                p = [x.strip() for x in line.split(",")]
                if header is None:
                    if len(p) >= 2 and any(w in p for w in wanted):
                        header = p
                    continue
                if not re.fullmatch(r"\d{8}", p[0]):
                    continue
                d = f"{p[0][:4]}-{p[0][4:6]}-{p[0][6:8]}"
                for i, name in enumerate(header):
                    if name in wanted and i < len(p) and p[i] not in ("-99.99", "-999", ""):
                        cols.setdefault(name, []).append((d, p[i]))
            for name, obs in cols.items():
                sid = "ff:" + re.sub(r"[^a-z0-9]+", "_", name.lower())
                run_.rows += upsert_series(con, sid, "factors_french", f"Fama-French factor: {names[name]}", "Percent per day", "Daily", obs, "United States", "Factors")
        con.commit()


def shiller(con):
    with Run(con, "shiller") as run_:
        r = fetch("https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls")
        book = xlrd.open_workbook(file_contents=r.content)
        s = book.sheet_by_name("Data")
        head_row = next(i for i in range(15) if str(s.cell_value(i, 0)).strip() == "Date")
        head = [str(s.cell_value(head_row, c)).strip() for c in range(s.ncols)]
        want = {"P": ("S&P composite price, monthly from 1871", "Index"), "D": ("S&P composite dividend", "USD"), "E": ("S&P composite earnings", "USD"),
                "CPI": ("Shiller CPI", "Index"), "CAPE": ("Shiller CAPE ratio", "Ratio")}
        cols = {k: [] for k in want}
        for i in range(head_row + 1, s.nrows):
            raw = s.cell_value(i, 0)
            if not isinstance(raw, float):
                continue
            year, month = int(raw), int(round((raw - int(raw)) * 100))
            if not 1 <= month <= 12:
                continue
            d = f"{year:04d}-{month:02d}-01"
            for k in want:
                if k in head:
                    cols[k].append((d, s.cell_value(i, head.index(k))))
        for k, obs in cols.items():
            title, units = want[k]
            run_.rows += upsert_series(con, f"shiller:{k}", "valuation_shiller", title, units, "Monthly", obs, "United States", "Valuation")
        con.commit()


STEPS = [fred, treasury, ecb_fx, eia, worldbank_pink, worldbank_indicators, cboe_vix, gpr, epu, french, shiller]


def run(con):
    for step in STEPS:
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
