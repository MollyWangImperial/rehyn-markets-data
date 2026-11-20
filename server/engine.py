"""Answers plain English questions from the database.

A question is parsed for assets, series, dates and intent, then answered with read-only SQL.
Every number comes from a query. Answers record the steps, the SQL and the datasets they used,
so the page can show where each figure came from and what licence it carries.
"""
import datetime as dt
import os
import pathlib
import re
import sqlite3
import statistics
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = pathlib.Path(os.environ.get("REHYN_DB", ROOT / "data" / "rehyn_markets.db"))
PUBLIC = os.environ.get("REHYN_EDITION") == "public"
QUERY_SECONDS = 20
SPOT = [(r"\bwti\b", "eia:RWTCd"), (r"\bbrent\b|\boil\b|\bcrude\b", "eia:RBRTEd"), (r"natural gas|henry hub", "eia:RNGWHHDd")]

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"

ALIASES = {
    "gold": "XAU/USD", "silver": "XAG/USD", "oil": "BRENT", "brent": "BRENT", "crude": "BRENT", "wti": "WTI", "natural gas": "NATGAS",
    "copper": "COPPER", "wheat": "WHEAT", "corn": "CORN", "soybeans": "SOY", "coffee": "KC", "cocoa": "COCOA", "sugar": "SUGAR",
    "bitcoin": "BTC/USD", "btc": "BTC/USD", "ether": "ETH/USD", "ethereum": "ETH/USD", "solana": "SOL/USD", "dogecoin": "DOGE/USD",
    "s&p 500": "SPX", "s&p500": "SPX", "s&p": "SPX", "sp500": "SPX", "spx": "SPX", "the market": "SPX", "stocks": "SPX",
    "dow jones": "DJI", "dow": "DJI", "nasdaq 100": "NDX", "nasdaq": "NDX", "russell 2000": "RUT", "russell": "RUT", "small caps": "IWM",
    "ftse 100": "UKX", "ftse": "UKX", "dax": "DAX", "cac 40": "CAC", "nikkei": "NKY", "hang seng": "HSI", "euro stoxx": "SX5E", "kospi": "KOSPI",
    "shanghai": "SHCOMP", "sensex": "SENSEX", "bovespa": "IBOV", "vix": "VIX", "dollar index": "DXY", "dxy": "DXY", "us dollar": "DXY", "the dollar": "DXY",
    "euro": "EUR/USD", "eurusd": "EUR/USD", "pound": "GBP/USD", "sterling": "GBP/USD", "gbpusd": "GBP/USD", "yen": "USD/JPY", "usdjpy": "USD/JPY",
    "swiss franc": "USD/CHF", "yuan": "USD/CNY", "renminbi": "USD/CNY", "rupee": "USD/INR", "real": "USD/BRL", "colombian peso": "USD/COP", "mexican peso": "USD/MXN",
    "lira": "USD/TRY", "rouble": "USD/RUB", "ruble": "USD/RUB", "rand": "USD/ZAR", "won": "USD/KRW",
    "google": "GOOGL", "alphabet": "GOOGL", "facebook": "META", "meta": "META", "amazon": "AMZN", "tesla": "TSLA", "microsoft": "MSFT", "nvidia": "NVDA",
    "apple": "AAPL", "netflix": "NFLX", "jpmorgan": "JPM", "jp morgan": "JPM", "goldman": "GS", "goldman sachs": "GS", "berkshire": "BRK.B", "exxon": "XOM", "exxonmobil": "XOM",
    "chevron": "CVX", "boeing": "BA", "lockheed": "LMT", "lockheed martin": "LMT", "raytheon": "RTX", "tsmc": "TSM", "intel": "INTC", "amd": "AMD", "broadcom": "AVGO",
    "delta": "DAL", "delta air lines": "DAL", "carnival": "CCL", "embraer": "EMBJ", "ecopetrol": "EC", "bancolombia": "CIB", "mercadolibre": "MELI", "equinor": "EQNR",
    "shell": "SHEL", "bp": "BP", "bae": "BA.L", "bae systems": "BA.L", "rolls-royce": "RR.L", "rheinmetall": "RHM.DE", "alibaba": "BABA", "tencent": "0700.HK", "samsung": "005930.KS",
    "toyota": "TM", "sony": "SONY", "asml": "ASML", "ryanair": "RYAAY", "novo nordisk": "NVO",
    "semiconductors": "SMH", "chips": "SMH", "defence stocks": "ITA", "defense stocks": "ITA", "airlines": "JETS", "homebuilders": "XHB", "regional banks": "KRE", "banks": "XLF",
    "energy stocks": "XLE", "tech stocks": "XLK", "emerging markets": "EEM", "long bonds": "TLT", "treasuries": "TLT", "high yield": "HYG", "gold miners": "GDX",
    "uranium": "URA", "solar": "TAN", "colombia": "COLO", "brazil": "EWZ", "taiwan": "EWT", "china": "FXI", "japan": "EWJ",
}
# Country words are only assets when nothing else in the question claims them.
SOFT_ALIASES = {"colombia", "brazil", "taiwan", "china", "japan", "banks", "chips", "stocks", "the market", "real", "delta", "won", "meta", "oil", "gold", "solar"}

STOP_NAMES = {"target", "gap", "ball", "fox", "news", "block", "match", "general", "united", "american", "first", "international", "national", "southern",
              "public", "progressive", "state", "realty", "best", "global", "fair", "hub", "apa", "ppl", "next", "kind", "smith", "airlines", "energy", "bank", "trust",
              "health", "mobile", "electronic", "live", "market", "markets", "group", "capital", "financial", "oil", "gas", "motors", "foods", "data", "corning", "chubb"}
STOP_SYMBOLS = {"A", "I", "IT", "ALL", "ON", "ARE", "FOR", "AND", "OR", "THE", "BY", "AT", "NOW", "US", "UK", "EU", "GDP", "CPI", "FOMC", "ETF", "EPS", "PE", "COT", "AI",
                "WHAT", "WHEN", "HOW", "IS", "AS", "DO", "IN", "TO", "SEC", "OPEC", "NATO", "OF", "SO", "HAS", "HE", "BE", "GO", "MA", "KEY", "LOW", "CAN", "NEW", "ONE", "TWO", "WAR", "FED"}

SERIES = [
    (r"core cpi", "fred:CPILFESL", False), (r"\binflation\b", "fred:CPIAUCSL", True), (r"\bcpi\b|consumer prices?", "fred:CPIAUCSL", False),
    (r"core pce", "fred:PCEPILFE", False), (r"\bpce\b", "fred:PCEPI", False), (r"producer price|\bppi\b", "fred:PPIACO", False),
    (r"breakeven", "fred:T10YIE", False), (r"unemployment|jobless rate", "fred:UNRATE", False), (r"payrolls?|jobs report|nonfarm", "fred:PAYEMS", False),
    (r"jobless claims|initial claims", "fred:ICSA", False), (r"job openings|jolts", "fred:JTSJOL", False), (r"wages|hourly earnings", "fred:CES0500000003", False),
    (r"\bus gdp\b|real gdp", "fred:GDPC1", False), (r"industrial production", "fred:INDPRO", False), (r"retail sales", "fred:RSAFS", False),
    (r"housing starts", "fred:HOUST", False), (r"home prices?|house prices?|case.?shiller", "fred:CSUSHPINSA", False), (r"mortgage", "fred:MORTGAGE30US", False),
    (r"consumer sentiment|michigan", "fred:UMCSENT", False), (r"fed funds|federal funds|policy rate|fed rate|interest rates?", "fred:DFF", False),
    (r"balance sheet|fed assets", "fred:WALCL", False), (r"\bm2\b|money supply", "fred:M2SL", False), (r"reverse repo", "fred:RRPONTSYD", False),
    (r"2s10s|10y.?2y|curve spread", "fred:T10Y2Y", False), (r"real yield", "fred:DFII10", False),
    (r"10.?y(ea)?r?\b.*(yield|treasury|note)|10 year", "ust:10yr", False), (r"2.?y(ea)?r?\b.*(yield|treasury|note)|2 year", "ust:2yr", False),
    (r"30.?y(ea)?r?\b.*(yield|treasury|bond)|30 year", "ust:30yr", False), (r"3.?month (yield|bill|treasury)", "ust:3mo", False),
    (r"high yield spread|junk spread|credit spreads?", "fred:BAMLH0A0HYM2", False), (r"investment grade spread", "fred:BAMLC0A0CM", False),
    (r"financial stress", "fred:STLFSI4", False), (r"financial conditions", "fred:NFCI", False), (r"national debt|debt to gdp", "fred:GFDEGDQ188S", False),
    (r"geopolitical risk|\bgpr\b", "gpr:GPRD", False), (r"policy uncertainty|\bepu\b", "epu:US_daily", False), (r"\bcape\b|shiller p/?e", "shiller:CAPE", False),
    (r"momentum factor", "ff:mom", False), (r"value factor", "ff:hml", False), (r"size factor", "ff:smb", False), (r"recessions?", "fred:USREC", False),
]

# Series with an open source direct from the agency. These win over the FRED copy when collected.
PREFER = {"fred:CPIAUCSL": "bls:CUSR0000SA0", "fred:CPILFESL": "bls:CUSR0000SA0L1E", "fred:PPIACO": "bls:WPU00000000", "fred:UNRATE": "bls:LNS14000000",
          "fred:PAYEMS": "bls:CES0000000001", "fred:CIVPART": "bls:LNS11300000", "fred:CES0500000003": "bls:CES0500000003", "fred:JTSJOL": "bls:JTS000000000000000JOL"}

COUNTRIES = {"united states": "USA", "china": "CHN", "japan": "JPN", "germany": "DEU", "united kingdom": "GBR", "uk": "GBR", "france": "FRA", "italy": "ITA", "spain": "ESP",
             "canada": "CAN", "australia": "AUS", "south korea": "KOR", "korea": "KOR", "india": "IND", "brazil": "BRA", "colombia": "COL", "mexico": "MEX", "argentina": "ARG",
             "russia": "RUS", "ukraine": "UKR", "turkey": "TUR", "saudi arabia": "SAU", "iran": "IRN", "iraq": "IRQ", "israel": "ISR", "egypt": "EGY", "south africa": "ZAF",
             "nigeria": "NGA", "indonesia": "IDN", "vietnam": "VNM", "poland": "POL", "norway": "NOR", "switzerland": "CHE", "netherlands": "NLD", "sweden": "SWE",
             "venezuela": "VEN", "pakistan": "PAK", "taiwan": "TWN"}
WDI = [(r"gdp growth", "NY.GDP.MKTP.KD.ZG"), (r"\bgdp\b", "NY.GDP.MKTP.CD"), (r"inflation|cpi", "FP.CPI.TOTL.ZG"), (r"unemployment", "SL.UEM.TOTL.ZS"),
       (r"government debt|national debt|\bdebt\b", "GC.DOD.TOTL.GD.ZS"), (r"current account", "BN.CAB.XOKA.GD.ZS"), (r"\btrade\b", "NE.TRD.GNFS.ZS"),
       (r"military|defen[cs]e spending", "MS.MIL.XPND.GD.ZS"), (r"reserves", "FI.RES.TOTL.CD"), (r"population", "SP.POP.TOTL")]

CONCEPTS = [
    (r"free cash flow|\bfcf\b", "fcf", "Free cash flow"), (r"operating cash flow", "operating_cash_flow", "Operating cash flow"), (r"capex|capital spending", "capex", "Capital spending"),
    (r"buybacks?|repurchase", "buybacks", "Share buybacks"), (r"dividends? paid", "dividends_paid", "Dividends paid"), (r"gross profit", "gross_profit", "Gross profit"),
    (r"operating (income|profit)", "operating_income", "Operating income"), (r"net income|net profit|profit|earnings(?! per)", "net_income", "Net income"),
    (r"\beps\b|earnings per share", "eps_diluted", "Diluted EPS"), (r"research|r&d", "rnd", "Research and development"), (r"long.?term debt|\bdebt\b", "long_term_debt", "Long term debt"),
    (r"\bcash\b", "cash", "Cash"), (r"total assets|\bassets\b", "assets", "Total assets"), (r"liabilities", "liabilities", "Total liabilities"), (r"shareholders.? equity|book value", "equity", "Shareholders' equity"),
    (r"inventor", "inventory", "Inventory"), (r"shares outstanding", "shares_outstanding", "Shares outstanding"), (r"revenues?|\bsales\b|turnover", "revenue", "Revenue"),
]

FAMILIES = [
    (r"opec", "OPEC output decision"), (r"(fed|federal reserve|fomc|rate).{0,24}(cut|lower|eas)|cut.{0,18}\brates?\b|\bbp cuts?\b", "Fed rate cut"),
    (r"(fed|federal reserve|fomc|rate).{0,24}(hike|rais|rise|increase)|hike", "Fed rate hike"), (r"taiwan", "Taiwan Strait tension"), (r"hormuz|red sea|tanker|shipping attack", "Gulf shipping or Hormuz attack"),
    (r"pipeline|refinery", "Pipeline or energy infrastructure attack"), (r"invasion|invade|invades|attacks?\b|war\b|wars\b|strikes?\b", "Invasion or interstate attack"), (r"\bcoups?\b", "Coup"),
    (r"sanction", "Sanctions imposed"), (r"tariff|trade war", "Tariff action"), (r"bank (failure|collapse|rescue|run)|bailout|banking crisis", "Bank failure or rescue"),
    (r"default|debt crisis", "Sovereign default or debt crisis"), (r"pandemic|outbreak", "Pandemic or outbreak declaration"), (r"earthquake|hurricane|tsunami|disaster", "Major earthquake or disaster"),
    (r"election", "National election result"), (r"export control|chip (ban|curb)", "Export controls on chips"), (r"vix.{0,16}(spike|above|over|40)", "VIX closes above 40"),
    (r"crash|big falls?|sell.?off", "S&P 500 one day fall of 4% or more"), (r"(oil|brent).{0,14}(spike|surge|jump)", "Brent one day rise of 8% or more"),
    (r"(oil|brent).{0,14}(crash|plunge|collapse)", "Brent one day fall of 8% or more"), (r"gold.{0,14}(spike|surge|jump)", "Gold one day rise of 3.5% or more"),
]
PANEL = ["SPX", "XAU/USD", "BRENT", "DXY", "US10Y", "VIX"]

SECTORS = {"energy": "Energy", "tech": "Information Technology", "technology": "Information Technology", "financials": "Financials", "banks": "Financials", "healthcare": "Health Care",
           "health care": "Health Care", "industrials": "Industrials", "utilities": "Utilities", "materials": "Materials", "real estate": "Real Estate", "consumer staples": "Consumer Staples",
           "consumer discretionary": "Consumer Discretionary", "communication": "Communication Services"}

WORDS_STOP = set("""a an the of on in at to for from by with and or is are was were be been do does did what which who whom how when where why show me tell give get find list all any
 about over into after before than that this those these it its as has have had will would can could should please look up latest recent news headlines article articles happened happen
 today this week month year years day days since last past data database between there their them they you your i we our""".split())

COT_NAMES = {"gold": "088691", "silver": "084691", "copper": "085692", "oil": "067651", "crude": "067651", "wti": "067651", "natural gas": "023651", "corn": "002602", "wheat": "001602",
             "soybeans": "005602", "coffee": "083731", "sugar": "080732", "cocoa": "073732", "euro": "099741", "pound": "096742", "sterling": "096742", "yen": "097741", "swiss franc": "092741",
             "australian dollar": "232741", "canadian dollar": "090741", "mexican peso": "095741", "dollar": "098662", "bitcoin": "133741", "s&p": "13874A", "nasdaq": "209742", "russell": "239742",
             "10 year": "043602", "treasury": "020601", "vix": "1170E1"}


def connect():
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    if PUBLIC:
        # Anyone can run SQL here, so one slow query must not hold the server.
        stop = time.monotonic() + QUERY_SECONDS
        con.set_progress_handler(lambda: time.monotonic() > stop, 200000)
    return con


def pct(v, digits=1):
    if v is None:
        return "n/a"
    return f"{'▲' if v >= 0 else '▼'} {abs(v) * 100:.{digits}f}%"


def tone(v):
    return "" if v is None else ("u" if v >= 0 else "d")


def cell(v, digits=1):
    return {"v": pct(v, digits), "t": tone(v)}


def money(v, currency=None, cls=None):
    if v is None:
        return "n/a"
    if cls == "Rates":
        return f"{v:.2f}%"
    sign = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "HKD": "HK$", "USX": "", "GBp": ""}.get(currency, "") if cls in ("Equity", "ETF", "Commodity", "Crypto") else ""
    digits = 2 if abs(v) < 1000 else 0 if abs(v) >= 100000 else 2
    if cls == "FX":
        digits = 4 if abs(v) < 20 else 2
    tail = "p" if currency == "GBp" and cls == "Equity" else ""
    return f"{sign}{v:,.{digits}f}{tail}"


def big(v, unit=None):
    if v is None:
        return "n/a"
    a, s = abs(v), "-" if v < 0 else ""
    p = "$" if unit == "USD" else ""
    for div, tag in ((1e12, "tn"), (1e9, "bn"), (1e6, "m")):
        if a >= div:
            return f"{s}{p}{a / div:,.2f}{tag}"
    return f"{s}{p}{a:,.2f}" if a < 1000 else f"{s}{p}{a:,.0f}"


def day(d):
    if not d:
        return ""
    y, m, x = str(d)[:10].split("-")
    return f"{int(x)} {list(MONTHS)[int(m) - 1].title()} {y}"


def thin(points, limit=900):
    if len(points) <= limit:
        return points
    step = len(points) / limit
    picked = [points[int(i * step)] for i in range(limit)]
    if picked[-1] != points[-1]:
        picked.append(points[-1])
    return picked


class Dates:
    def __init__(self, start=None, end=None, label=None, exact=None):
        self.start, self.end, self.label, self.exact = start, end, label, exact


def parse_dates(text):
    t, today = text.lower(), dt.date.today()

    def make(y, m, d):
        try:
            return dt.date(int(y), int(m), int(d))
        except ValueError:
            return None

    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m and make(*m.groups()):
        d = make(*m.groups())
        return Dates(d.isoformat(), d.isoformat(), day(d.isoformat()), d.isoformat())
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTH_RE}\s+(\d{{4}})\b", t)
    if m and make(m.group(3), MONTHS[m.group(2)], m.group(1)):
        d = make(m.group(3), MONTHS[m.group(2)], m.group(1))
        return Dates(d.isoformat(), d.isoformat(), day(d.isoformat()), d.isoformat())
    m = re.search(rf"\b{MONTH_RE}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", t)
    if m and make(m.group(3), MONTHS[m.group(1)], m.group(2)):
        d = make(m.group(3), MONTHS[m.group(1)], m.group(2))
        return Dates(d.isoformat(), d.isoformat(), day(d.isoformat()), d.isoformat())
    m = re.search(r"\b(?:from|between)\s+((?:19|20)\d{2})\s*(?:to|and|until|-|–)\s*((?:19|20)\d{2})\b", t)
    if m:
        return Dates(f"{m.group(1)}-01-01", f"{m.group(2)}-12-31", f"{m.group(1)} to {m.group(2)}")
    m = re.search(rf"\bsince\s+(?:{MONTH_RE}\s+)?((?:19|20)\d{{2}})\b", t)
    if m:
        month = MONTHS.get(m.group(1), 1) if m.group(1) else 1
        return Dates(f"{m.group(2)}-{month:02d}-01", None, f"since {m.group(2)}")
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|week|month|year)s?\b", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "week": 7, "month": 30.44, "year": 365.25}[unit]
        return Dates((today - dt.timedelta(days=int(days))).isoformat(), None, f"last {n} {unit}s")
    m = re.search(r"\b(?:last|past)\s+(week|month|year|decade)\b", t)
    if m:
        days = {"week": 7, "month": 31, "year": 366, "decade": 3653}[m.group(1)]
        return Dates((today - dt.timedelta(days=days)).isoformat(), None, f"last {m.group(1)}")
    if re.search(r"\bthis year\b|\bytd\b|year to date", t):
        return Dates(f"{today.year}-01-01", None, "this year")
    m = re.search(rf"\b{MONTH_RE}\s+((?:19|20)\d{{2}})\b", t)
    if m:
        mo, y = MONTHS[m.group(1)], int(m.group(2))
        end = (dt.date(y + mo // 12, mo % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        return Dates(f"{y}-{mo:02d}-01", end, f"{m.group(1).title()} {y}")
    m = re.search(r"\b((?:19|20)\d{2})\b", t)
    if m:
        return Dates(f"{m.group(1)}-01-01", f"{m.group(1)}-12-31", m.group(1))
    return Dates()


class Entities:
    """Name and symbol lookup, built once from ref_asset."""

    def __init__(self, con):
        self.assets = {r["symbol"]: dict(r) for r in con.execute("SELECT * FROM ref_asset WHERE last_price IS NOT NULL")}
        self.names = {}
        for sym, a in self.assets.items():
            if a["asset_class"] != "Equity" or not a["name"]:
                continue
            n = a["name"].lower()
            n = re.sub(r",?\s+(incorporated|inc\.?|corporation|corp\.?|company|co\.?|plc|holdings?|group|ltd\.?|limited|class [a-c]|\(class [a-c]\))\s*$", "", n).strip()
            n = re.sub(r",?\s+(inc\.?|corp\.?|plc)\s*$", "", n).strip()
            if len(n) >= 4 and n not in STOP_NAMES and n not in self.names:
                self.names[n] = sym

    def find(self, text):
        """Returns symbols in the order they appear. Explicit tickers and names outrank the soft words."""
        low = f" {text.lower()} "
        hits, taken = [], []

        def free(a, b):
            return all(b <= x or a >= y for x, y in taken)

        scan = re.sub(r"S&P(\s*500)?", lambda m: " " * len(m.group(0)), text, flags=re.I)
        for tok in re.finditer(r"\$?\b[A-Z][A-Z0-9]{0,5}(?:[./-][A-Z0-9]{1,3})?\b", scan):
            word = tok.group(0).lstrip("$")
            marked = tok.group(0).startswith("$")
            if word in self.assets and (marked or (len(word) > 1 and word not in STOP_SYMBOLS)):
                hits.append((tok.start() + 1, word))
                taken.append((tok.start() + 1, tok.end() + 1))
        for table, soft in ((ALIASES, False), (self.names, False)):
            for key in sorted(table, key=len, reverse=True):
                for m in re.finditer(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", low):
                    sym = table[key]
                    if sym in self.assets and free(m.start(), m.end()) and (key not in SOFT_ALIASES):
                        hits.append((m.start(), sym))
                        taken.append((m.start(), m.end()))
        for key in sorted(SOFT_ALIASES, key=len, reverse=True):
            for m in re.finditer(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", low):
                sym = ALIASES.get(key)
                if sym in self.assets and free(m.start(), m.end()):
                    hits.append((m.start() + 100000, sym))
                    taken.append((m.start(), m.end()))
        out = []
        for _, sym in sorted(hits):
            if sym not in out:
                out.append(sym)
        return out

    def find_hard(self, text):
        low = text.lower()
        soft = {ALIASES[k] for k in SOFT_ALIASES if k in ALIASES and re.search(rf"\b{re.escape(k)}\b", low)}
        return [s for s in self.find(text) if s not in soft or re.search(rf"\b{re.escape(s)}\b", text)]


_entities = None


def entities(con):
    global _entities
    if _entities is None:
        _entities = Entities(con)
    return _entities


def strip_dates(text):
    text = re.sub(rf"\b(?:\d{{1,2}}\s+)?{MONTH_RE}\s+(?:19|20)\d{{2}}\b", " ", text, flags=re.I)
    return re.sub(r"\b(?:19|20)\d{2}\b", " ", text)


def fts_terms(text, mode="AND"):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9&'-]+", text.lower())
    keep = [w for w in words if w not in WORDS_STOP and len(w) > 1]
    if not keep:
        return None
    return f" {mode} ".join('"' + w.replace('"', "") + '"' for w in keep[:8])


class Answer:
    def __init__(self, con, question):
        self.con, self.q = con, question
        self.steps, self.blocks, self.sql, self.datasets = [], [], [], []
        self.title, self.note = None, None

    def step(self, text):
        self.steps.append(text)

    def rows(self, sql, args=(), show=True):
        if show:
            self.sql.append(" ".join(sql.split()))
        return self.con.execute(sql, args).fetchall()

    def use(self, *ids):
        for i in ids:
            if i and i not in self.datasets:
                self.datasets.append(i)

    def add(self, block_type, **body):
        self.blocks.append({"type": block_type, **body})

    def lede(self, text):
        self.add("lede", text=text)

    def table(self, columns, rows, title=None):
        self.add("table", columns=columns, rows=rows, title=title)

    def payload(self):
        marks = ",".join("?" * len(self.datasets)) or "''"
        labels = [dict(r) for r in self.con.execute(
            f"SELECT id, name, source_name, tier, licence, terms_url, attribution FROM cat_dataset WHERE id IN ({marks})", self.datasets)]
        return {"question": self.q, "steps": self.steps, "blocks": self.blocks, "sql": self.sql, "sources": labels, "note": self.note}


def price_rows(ans, asset, d):
    where, args = "asset_id=?", [asset["asset_id"]]
    if d.start:
        where += " AND date>=?"
        args.append(d.start)
    if d.end:
        where += " AND date<=?"
        args.append(d.end)
    return ans.rows(f"SELECT date, open, high, low, close, coalesce(adj_close, close) adj, volume FROM px_daily WHERE {where} ORDER BY date", args)


def default_window(d):
    if d.start or d.end:
        return d
    return Dates((dt.date.today() - dt.timedelta(days=1827)).isoformat(), None, "last 5 years")


def answer_asset(ans, sym, ents, d):
    asset = ents.assets[sym]
    d = default_window(d)
    ans.step(f"Found {asset['name']} ({sym}), {asset['asset_class'].lower()}")
    rows = price_rows(ans, asset, d)
    ans.use(asset["price_dataset"], "x_asset_metric")
    ans.step(f"Read {len(rows):,} daily bars from px_daily")
    if not rows:
        ans.lede(f"The database has no {asset['name']} prices for {d.label}. Its history runs from {day(asset['first_price'])} to {day(asset['last_price'])}.")
        return
    cls, cur = asset["asset_class"], asset["currency"]
    first, last = rows[0], rows[-1]
    level = cls in ("Rates",) or sym == "VIX"
    adj = [r["adj"] for r in rows]
    change = adj[-1] / adj[0] - 1 if adj[0] else None
    peak, dd = adj[0], 0.0
    for v in adj:
        peak = max(peak, v)
        if peak:
            dd = min(dd, v / peak - 1)
    rets = [adj[i] / adj[i - 1] - 1 for i in range(1, len(adj)) if adj[i - 1]]
    vol = statistics.pstdev(rets) * 252 ** 0.5 if len(rets) > 5 else None
    hi = max(rows, key=lambda r: r["high"] or r["close"])
    lo = min(rows, key=lambda r: r["low"] or r["close"])
    move = "up" if (change or 0) >= 0 else "down"
    total = "total return, dividends included" if cls in ("Equity", "ETF") else "change"
    span = f"over the {d.label}" if (d.label or "").startswith("last") else f"in {d.label}" if re.fullmatch(r"\d{4}|[A-Z][a-z]{2} \d{4}", d.label or "") else d.label or ""
    ans.lede(f"{asset['name']} closed at {money(last['close'], cur, cls)} on {day(last['date'])}, {move} {abs(change or 0) * 100:.1f}% {span} ({total}).")
    ans.add("stats", items=[
        {"label": "Last close", "value": money(last["close"], cur, cls), "tone": ""},
        {"label": f"Change, {d.label}", "value": pct(change), "tone": tone(change)},
        {"label": "Period high", "value": money(hi["high"] or hi["close"], cur, cls), "sub": day(hi["date"]), "tone": ""},
        {"label": "Period low", "value": money(lo["low"] or lo["close"], cur, cls), "sub": day(lo["date"]), "tone": ""},
        {"label": "Worst drawdown", "value": pct(dd), "tone": "d"} if not level else {"label": "Bars", "value": f"{len(rows):,}", "tone": ""},
        {"label": "Volatility", "value": f"{vol * 100:.1f}%" if vol else "n/a", "sub": "annualised", "tone": ""},
    ])
    pts = [{"t": r["date"], "v": r["close"], "o": r["open"], "h": r["high"], "l": r["low"]} for r in rows]
    ans.add("chart", kind="price", title=f"{asset['name']}, daily close", series=[{"name": sym, "points": thin(pts)}],
            unit=cur if cls in ("Equity", "ETF", "Commodity", "Crypto") else "", candles=len(pts) <= 300, up=(change or 0) >= 0)
    m = ans.rows("SELECT * FROM x_asset_metric WHERE asset_id=?", (asset["asset_id"],))
    if m and not (d.exact):
        x = m[0]
        ans.table(["Measure", "Value"], [
            ["20 trading day median return, full history", cell(x["med20"], 2)], ["Last 20 trading days", cell(x["r20d"])], ["Year to date", cell(x["ytd"])], ["One year", cell(x["r1y"])],
            ["RSI 14", f"{x['rsi14']:.1f}" if x["rsi14"] is not None else "n/a"], ["Beta to the S&P 500", f"{x['beta_spx']:.2f}" if x["beta_spx"] is not None else "n/a"],
            ["Now below all time high", cell(x["dd_now"])], ["Largest fall on record", f"{pct(x['max_dd'])} to {day(x['max_dd_date'])}"],
            ["Best day", f"{pct(x['best_day'])} on {day(x['best_day_date'])}"], ["Worst day", f"{pct(x['worst_day'])} on {day(x['worst_day_date'])}"], ["History in database", f"{x['history_years']} years"],
        ], title="Current measures")


def answer_compare(ans, syms, ents, d):
    d = default_window(d)
    ans.step("Comparing " + ", ".join(syms[:4]))
    if len(syms) > 4:
        ans.note = f"Charts show four assets at most, so {', '.join(syms[4:])} {'was' if len(syms) == 5 else 'were'} left out."
    syms = syms[:4]
    data = {}
    for s in syms:
        a = ents.assets[s]
        rows = price_rows(ans, a, d)
        ans.use(a["price_dataset"])
        if rows:
            data[s] = {r["date"]: r["adj"] for r in rows}
    if len(data) < 2:
        ans.lede("There is not enough overlapping history to compare those assets over that period.")
        return
    start = max(min(v) for v in data.values())
    series, table = [], []
    for s, px in data.items():
        dates = sorted(x for x in px if x >= start)
        base = px[dates[0]]
        pts = [{"t": x, "v": px[x] / base * 100} for x in dates]
        series.append({"name": s, "points": thin(pts, 500)})
        vals = [px[x] for x in dates]
        rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
        peak, dd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1)
        table.append([ents.assets[s]["name"], cell(vals[-1] / base - 1), f"{statistics.pstdev(rets) * 252 ** 0.5 * 100:.1f}%", cell(dd), day(dates[-1])])
    best = max(table, key=lambda r: float(r[1]["v"].split()[1].rstrip("%")) * (1 if r[1]["t"] == "u" else -1))
    ans.lede(f"Since {day(start)}, the common start date, {best[0]} moved the most: {best[1]['v']}.")
    ans.add("chart", kind="compare", title=f"Rebased to 100 on {day(start)}", series=series, unit="")
    ans.table(["Asset", "Total change", "Volatility", "Worst drawdown", "Latest"], table)


def answer_series(ans, sid, yoy, d):
    if sid in PREFER and ans.rows("SELECT 1 FROM ts_series WHERE series_id=?", (PREFER[sid],), show=False):
        sid = PREFER[sid]
    meta = ans.rows("SELECT * FROM ts_series WHERE series_id=?", (sid,))
    if not meta:
        ans.lede("That series is not in the public library." if PUBLIC else f"Series {sid} has not been collected yet.")
        return
    meta = meta[0]
    ans.use(meta["dataset_id"])
    ans.step(f"Matched the series {meta['title']}")
    where, args = "series_id=?", [sid]
    if d.end:
        where += " AND date<=?"
        args.append(d.end)
    rows = ans.rows(f"SELECT date, value FROM ts_obs WHERE {where} ORDER BY date", args)
    ans.step(f"Read {len(rows):,} observations from ts_obs")
    title, units = meta["title"], meta["units"]
    if yoy and len(rows) > 13:
        rows = [{"date": rows[i]["date"], "value": (rows[i]["value"] / rows[i - 12]["value"] - 1) * 100} for i in range(12, len(rows))]
        title, units = "US consumer price inflation, year on year", "Percent"
    if d.start:
        rows = [r for r in rows if r["date"] >= d.start]
    if not rows:
        ans.lede(f"No {title} observations for {d.label}.")
        return
    last = rows[-1]
    vals = [r["value"] for r in rows]
    rank = sum(v <= last["value"] for v in vals) / len(vals)
    fmt = lambda v: f"{v:,.2f}" if abs(v) < 1000 else big(v) if abs(v) >= 1e7 else f"{v:,.0f}"
    ans.lede(f"{title}: {fmt(last['value'])} {('(' + units + ')') if units else ''} at {day(last['date'])}. That sits higher than {rank * 100:.0f}% of readings since {day(rows[0]['date'])}.")
    ans.add("stats", items=[
        {"label": "Latest", "value": fmt(last["value"]), "sub": day(last["date"]), "tone": ""},
        {"label": "Highest", "value": fmt(max(vals)), "sub": day(max(rows, key=lambda r: r["value"])["date"]), "tone": ""},
        {"label": "Lowest", "value": fmt(min(vals)), "sub": day(min(rows, key=lambda r: r["value"])["date"]), "tone": ""},
        {"label": "Median", "value": fmt(statistics.median(vals)), "tone": ""},
    ])
    ans.add("chart", kind="line", title=title, series=[{"name": title, "points": thin([{"t": r["date"], "v": r["value"]} for r in rows])}], unit=units or "")


def answer_curve(ans, d):
    ans.step("Reading the Treasury curve")
    ans.use("rates_treasury")
    order = ["1mo", "3mo", "6mo", "1yr", "2yr", "3yr", "5yr", "7yr", "10yr", "20yr", "30yr"]
    latest = ans.rows("SELECT max(date) m FROM ts_obs WHERE series_id='ust:10yr'")[0]["m"]
    when = d.exact or (d.end if d.end and d.end < latest else latest)
    got = ans.rows("SELECT series_id, value, date FROM ts_obs WHERE series_id LIKE 'ust:%' AND date=(SELECT max(date) FROM ts_obs WHERE series_id='ust:10yr' AND date<=?)", (when,))
    by = {r["series_id"].split(":")[1]: r["value"] for r in got}
    pts = [[k.replace("mo", " month").replace("yr", " year"), f"{by[k]:.2f}%"] for k in order if k in by]
    if not pts:
        ans.lede("No Treasury curve for that date.")
        return
    spread = by.get("10yr", 0) - by.get("2yr", 0)
    ans.lede(f"On {day(got[0]['date'])} the 10 year yield was {by.get('10yr', 0):.2f}% and the 2 year {by.get('2yr', 0):.2f}%, a spread of {spread * 100:+.0f}bp. The curve is {'inverted' if spread < 0 else 'upward sloping'} at that point.")
    ans.add("chart", kind="bars", title=f"US Treasury curve, {day(got[0]['date'])}", bars=[{"label": a, "value": float(b.rstrip('%'))} for a, b in pts], unit="%")


def study_family(ans, family, d, text):
    where, args = "family=?", [family]
    if d.start:
        where += " AND date>=?"
        args.append(d.start)
    if d.end:
        where += " AND date<=?"
        args.append(d.end)
    m = re.search(r"(\d{2,3})\s*(?:bp|basis point)", text.lower())
    if m and family.startswith("Fed"):
        where += " AND abs(magnitude)=?"
        args.append(int(m.group(1)))
    return ans.rows(f"SELECT * FROM ev_event WHERE {where} ORDER BY date", args), (m.group(1) + "bp ") if m and family.startswith("Fed") else ""


def answer_event_study(ans, family, syms, ents, d, text):
    ans.step(f"Matched the event family: {family}")
    events, size = study_family(ans, family, d, text)
    ans.use("ev_library", "x_event_return")
    ans.step(f"Found {len(events)} dated events in ev_event")
    if not events:
        ans.lede(f"The library has no {size}{family.lower()} events for that period.")
        return
    ids = [e["event_id"] for e in events]
    marks = ",".join("?" * len(ids))
    assets = syms or PANEL
    summary = []
    for s in assets:
        a = ents.assets.get(s)
        if not a:
            continue
        ans.use(a["price_dataset"])
        rows = ans.rows(f"SELECT r.*, e.date, e.title, e.source_url FROM x_event_return r JOIN ev_event e USING(event_id) WHERE r.asset_id=? AND r.event_id IN ({marks}) ORDER BY e.date", [a["asset_id"], *ids], show=False)
        r20 = [r["r20"] for r in rows if r["r20"] is not None]
        if len(r20) < 1:
            continue
        med = lambda k: statistics.median([r[k] for r in rows if r[k] is not None]) if any(r[k] is not None for r in rows) else None
        hit = sum(v > 0 for v in r20) / len(r20)
        summary.append((a, rows, r20, med("r1"), med("r5"), statistics.median(r20), med("r60"), hit))
    ans.sql.append(f"SELECT e.date, e.title, a.symbol, r.r1, r.r5, r.r20, r.r60 FROM v_event_study WHERE family='{family}'")
    ans.step("Measured moves 1, 5, 20 and 60 trading days after each event")
    if not summary:
        ans.lede("Those assets have no price history around these events.")
        return
    if len(syms) == 1:
        a, rows, r20, m1, m5, m20, m60, hit = summary[0]
        ans.lede(f"After {len(r20)} {size}{family.lower()} events, {a['name']} moved a median {pct(m20)} over 20 trading days and rose in {hit * 100:.0f}% of them. The range was {pct(min(r20))} to {pct(max(r20))}.")
        ans.add("stats", items=[
            {"label": "Median, 5 days", "value": pct(m5), "tone": tone(m5)}, {"label": "Median, 20 days", "value": pct(m20), "tone": tone(m20)},
            {"label": "Median, 60 days", "value": pct(m60), "tone": tone(m60)}, {"label": "Rose in", "value": f"{sum(v > 0 for v in r20)} of {len(r20)}", "tone": ""},
        ])
        recent = [r for r in rows if r["r20"] is not None][-24:]
        ans.add("chart", kind="diverging", title=f"{a['name']}, 20 trading days after each event", bars=[{"label": r["date"], "value": r["r20"] * 100, "note": r["title"][:90]} for r in recent], unit="%")
        ans.table(["Date", "Event", "1 day", "5 days", "20 days", "60 days"],
                  [[day(r["date"]), {"v": r["title"][:96], "href": r["source_url"]}, cell(r["r1"]), cell(r["r5"]), cell(r["r20"]), cell(r["r60"])] for r in reversed(rows)][:40], title="Every event in the sample")
    else:
        lead = summary[0]
        ans.lede(f"Across {len(events)} {size}{family.lower()} events, here is how each asset moved. {lead[0]['name']} had a median of {pct(lead[5])} after 20 trading days.")
        ans.add("chart", kind="diverging", title="Median move 20 trading days after the event", bars=[{"label": x[0]["symbol"], "value": x[5] * 100} for x in summary], unit="%")
        ans.table(["Asset", "Events", "1 day", "5 days", "20 days", "60 days", "Rose in"], [
            [x[0]["name"], str(len(x[2])), cell(x[3]), cell(x[4]), cell(x[5]), cell(x[6]), f"{x[7] * 100:.0f}%"] for x in summary], title="Median moves")
        ans.table(["Date", "Event"], [[day(e["date"]), {"v": e["title"][:110], "href": e["source_url"]}] for e in reversed(events)][:30], title="Events in the sample")
    origin = events[0]["origin"] or ""
    if "Wikipedia" in origin:
        ans.use("events_wiki")
        ans.note = "Events in this family were matched by keywords in the dated record, so some may be loose matches. Check the list."
    ans.add("disc", text="Measured from the last close before each event. Small samples and overlapping crises limit what this shows. Past patterns do not guarantee future moves. Information only, not investment advice.")


def answer_fundamentals(ans, sym, ents, text, d):
    a = ents.assets[sym]
    if not a["cik"]:
        ans.lede(f"{a['name']} has no SEC filings, so reported financials are not available. US listed companies are covered.")
        return
    low = text.lower()
    found = [(c, label) for pat, c, label in CONCEPTS if re.search(pat, low)] or [("revenue", "Revenue"), ("net_income", "Net income")]
    names = {c for c, _ in found}
    drop = ({"cash"} if names & {"fcf", "operating_cash_flow"} else set()) | ({"net_income"} if names & {"gross_profit", "operating_income"} else set())
    found = [f for f in found if f[0] not in drop]
    ans.use("co_financials")
    quarterly = bool(re.search(r"quarter", low))
    span = "BETWEEN 80 AND 100" if quarterly else "BETWEEN 340 AND 380"
    for concept, label in found[:2]:
        def read(c):
            return ans.rows(
                f"""SELECT period_end, value, first_value, first_filed, unit FROM co_fact WHERE cik=? AND concept=?
                    AND (period_start='' OR julianday(period_end)-julianday(period_start) {span}) ORDER BY period_end""", (a["cik"], c))
        if concept == "fcf":
            ocf = {r["period_end"]: r["value"] for r in read("operating_cash_flow") if r["value"] is not None}
            cap = {r["period_end"]: r["value"] for r in read("capex") if r["value"] is not None}
            rows = [{"period_end": k, "value": ocf[k] - cap[k], "unit": "USD", "first_filed": None, "first_value": None} for k in sorted(ocf) if k in cap]
        else:
            rows = read(concept)
        ans.step(f"Read {len(rows)} {'quarterly' if quarterly else 'annual'} {label.lower()} figures from SEC filings")
        if d.start:
            rows = [r for r in rows if r["period_end"] >= d.start]
        if d.end:
            rows = [r for r in rows if r["period_end"] <= d.end]
        if not rows:
            ans.lede(f"No {label.lower()} found for {a['name']} in SEC filings for that period.")
            continue
        rows = rows[-40:] if quarterly else rows[-16:]
        last, prev = rows[-1], rows[-2] if len(rows) > 1 else None
        unit = "USD" if (last["unit"] or "").startswith("USD") else None
        growth = last["value"] / prev["value"] - 1 if prev and prev["value"] else None
        show = (lambda v: f"${v:.2f}") if concept == "eps_diluted" else (lambda v: big(v, unit))
        tail = f", {pct(growth)} on the prior {'quarter' if quarterly else 'year'}" if growth is not None else ""
        ans.lede(f"{a['name']} reported {label.lower()} of {show(last['value'])} for the period ended {day(last['period_end'])}{tail}.")
        ans.add("chart", kind="bars", title=f"{a['name']}: {label}", bars=[{"label": r["period_end"][:7] if quarterly else r["period_end"][:4], "value": r["value"], "note": show(r["value"])} for r in rows], unit="", fmt="big")
        ans.table(["Period ended", label, "First reported", "First filed"], [
            [day(r["period_end"]), show(r["value"]), show(r["first_value"]) if r["first_value"] is not None else "", day(r["first_filed"])] for r in reversed(rows)])


def answer_filings(ans, sym, ents, text, d):
    a = ents.assets[sym]
    ans.use("co_filings")
    low = text.lower()
    forms = [f for f in ("8-K", "10-K", "10-Q", "DEF 14A", "S-1") if f.lower() in low]
    where, args = "cik=?", [a["cik"]]
    if forms:
        where += f" AND form IN ({','.join('?' * len(forms))})"
        args += forms
    else:
        where += " AND form NOT IN ('4','3','5','144','4/A')"
    if d.start:
        where += " AND filed>=?"
        args.append(d.start)
    if d.end:
        where += " AND filed<=?"
        args.append(d.end)
    rows = ans.rows(f"SELECT * FROM co_filing WHERE {where} ORDER BY filed DESC LIMIT 40", args)
    ans.step(f"Read {len(rows)} filings from co_filing")
    if not rows:
        ans.lede(f"No matching filings for {a['name']}.")
        return
    ans.lede(f"Latest {' and '.join(forms) if forms else 'SEC'} filings for {a['name']}. The most recent is a {rows[0]['form']} filed on {day(rows[0]['filed'])}.")
    ans.table(["Filed", "Form", "Period", "8-K items", "Document"], [
        [day(r["filed"]), r["form"], day(r["report_date"]), r["items"] or "", {"v": (r["doc_desc"] or r["doc"] or "Open")[:40],
         "href": f"https://www.sec.gov/Archives/edgar/data/{r['cik']}/{r['accession'].replace('-', '')}/{r['doc']}"}] for r in rows])


def answer_insider(ans, sym, ents, d):
    a = ents.assets[sym]
    ans.use("co_insider")
    args = [sym]
    where = "symbol=? AND code IN ('P','S')"
    if d.start:
        where += " AND tx_date>=?"
        args.append(d.start)
    rows = ans.rows(f"SELECT * FROM co_insider_tx WHERE {where} ORDER BY tx_date DESC LIMIT 400", args)
    ans.step(f"Read {len(rows)} open market trades from co_insider_tx")
    if not rows:
        ans.lede(f"No open market insider trades for {a['name']} in the last 12 quarters on file.")
        return
    bought = sum((r["shares"] or 0) * (r["price"] or 0) for r in rows if r["code"] == "P")
    sold = sum((r["shares"] or 0) * (r["price"] or 0) for r in rows if r["code"] == "S")
    ans.lede(f"Insiders at {a['name']} sold {big(sold, 'USD')} and bought {big(bought, 'USD')} of stock on the open market across the {len(rows)} trades shown, the latest on {day(rows[0]['tx_date'])}.")
    ans.table(["Date", "Insider", "Role", "Trade", "Shares", "Price", "Value"], [
        [day(r["tx_date"]), (r["owner"] or "").title(), (r["role"] or "")[:28], {"v": "Bought" if r["code"] == "P" else "Sold", "t": "u" if r["code"] == "P" else "d"},
         f"{r['shares']:,.0f}" if r["shares"] else "", f"${r['price']:,.2f}" if r["price"] else "", big((r["shares"] or 0) * (r["price"] or 0), "USD")] for r in rows[:40]])


def answer_funds(ans, text, target, ents):
    ans.use("co_holdings")
    table = ans.rows("SELECT 1 FROM sqlite_master WHERE name='co_fund_holding'", show=False)
    period = ans.rows("SELECT max(period) p FROM co_fund_holding", show=False)[0]["p"] if table else None
    if not period:
        ans.lede("Fund holdings are not collected yet. The SEC asks crawlers to give a contact address, and this one has none so far.")
        return
    names = [r["manager"] for r in ans.rows("SELECT DISTINCT manager FROM co_fund_holding WHERE period=?", (period,), show=False)]
    words = [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in WORDS_STOP and w not in ("holdings", "hold", "holds", "owns", "fund", "funds", "hedge", "portfolio", "stake", "stakes", "position", "positions")]
    manager = next((m for m in names if any(w in m.lower() for w in words)), None)
    if manager:
        rows = ans.rows("SELECT issuer, title, shares, value_usd FROM co_fund_holding WHERE manager=? AND period=? ORDER BY value_usd DESC LIMIT 25", (manager, period))
        total = ans.rows("SELECT sum(value_usd) v, count(*) n FROM co_fund_holding WHERE manager=? AND period=?", (manager, period), show=False)[0]
        ans.step(f"Read {total['n']} positions from the latest 13F")
        ans.lede(f"{manager.title()} reported {total['n']} long positions worth {big(total['v'], 'USD')} at {day(period)}. {rows[0]['issuer'].title()} is the largest, at {rows[0]['value_usd'] / total['v'] * 100:.1f}% of the reported total.")
        ans.table(["Issuer", "Class", "Shares", "Value", "Share of total"], [[r["issuer"].title(), r["title"], f"{r['shares']:,.0f}", big(r["value_usd"], "USD"), f"{r['value_usd'] / total['v'] * 100:.1f}%"] for r in rows])
    elif target:
        a = ents.assets[target]
        key = re.sub(r"[,.].*$", "", a["name"]).upper().split(" ")[0]
        rows = ans.rows("SELECT manager, issuer, shares, value_usd FROM co_fund_holding WHERE period=? AND issuer LIKE ? ORDER BY value_usd DESC LIMIT 25", (period, key + "%"))
        ans.step(f"Searched 13F holdings for {a['name']}")
        if not rows:
            ans.lede(f"None of the tracked managers report a position in {a['name']} at {day(period)}.")
            return
        ans.lede(f"{len({r['manager'] for r in rows})} tracked managers report a position in {a['name']} at {day(period)}, led by {rows[0]['manager'].title()} with {big(rows[0]['value_usd'], 'USD')}.")
        ans.table(["Manager", "Issuer", "Shares", "Value"], [[r["manager"].title(), r["issuer"].title(), f"{r['shares']:,.0f}", big(r["value_usd"], "USD")] for r in rows])
    else:
        rows = ans.rows("SELECT manager, sum(value_usd) v, count(*) n FROM co_fund_holding WHERE period=? GROUP BY manager ORDER BY v DESC", (period,))
        ans.lede(f"{len(rows)} tracked managers, from their 13F filings at {day(period)}.")
        ans.table(["Manager", "Reported value", "Positions"], [[r["manager"].title(), big(r["v"], "USD"), f"{r['n']:,}"] for r in rows])
    ans.note = "13F filings show long US positions up to 45 days after quarter end. They leave out shorts, most non-US holdings and cash."


def answer_dividends(ans, sym, ents, d):
    a = ents.assets[sym]
    ans.use("px_actions")
    rows = ans.rows("SELECT date, kind, value FROM px_action WHERE asset_id=? ORDER BY date DESC", (a["asset_id"],))
    ans.step(f"Read {len(rows)} corporate actions from px_action")
    divs = [r for r in rows if r["kind"] == "dividend"]
    splits = [r for r in rows if r["kind"] == "split"]
    if not rows:
        ans.lede(f"{a['name']} has no dividends or splits on file.")
        return
    year = sum(r["value"] for r in divs if r["date"] >= (dt.date.today() - dt.timedelta(days=365)).isoformat())
    ans.lede(f"{a['name']} has {len(divs)} dividends and {len(splits)} splits on file. Dividends over the last 12 months total {year:.2f} per share.")
    if len(divs) > 2:
        by = {}
        for r in divs:
            by[r["date"][:4]] = by.get(r["date"][:4], 0) + r["value"]
        ans.add("chart", kind="bars", title="Dividends per share by year", bars=[{"label": k, "value": by[k]} for k in sorted(by)[-20:]], unit="")
    if splits:
        ans.table(["Date", "Split ratio"], [[day(r["date"]), f"{r['value']:g} for 1"] for r in splits], title="Splits")


def answer_cot(ans, text, d):
    low = text.lower()
    code = next((c for k, c in sorted(COT_NAMES.items(), key=lambda x: -len(x[0])) if k in low), None)
    ans.use("pos_cot")
    if not code:
        rows = ans.rows("""SELECT market, report_date, speculator_net, open_interest FROM v_cot_net
                           WHERE report_date=(SELECT max(report_date) FROM pos_cot) ORDER BY abs(speculator_net*1.0/open_interest) DESC""")
        ans.lede("Speculator net positions, latest weekly report, largest relative to open interest first.")
        ans.table(["Market", "Report", "Speculators net", "Share of open interest"], [[r["market"], day(r["report_date"]), f"{r['speculator_net']:,.0f}", cell(r["speculator_net"] / r["open_interest"]) if r["open_interest"] else ""] for r in rows])
        return
    where, args = "market_code=?", [code]
    if d.start:
        where += " AND report_date>=?"
        args.append(d.start)
    rows = ans.rows(f"SELECT * FROM v_cot_net WHERE {where} ORDER BY report_date", args)
    ans.step(f"Read {len(rows):,} weekly reports from pos_cot")
    if not rows:
        ans.lede("No positioning reports for that market and period.")
        return
    last = rows[-1]
    rank = sum(r["speculator_net"] <= last["speculator_net"] for r in rows) / len(rows)
    ans.lede(f"Speculators are net {'long' if last['speculator_net'] >= 0 else 'short'} {abs(last['speculator_net']):,.0f} contracts of {last['market']} as of {day(last['report_date'])}, higher than {rank * 100:.0f}% of weekly readings since {day(rows[0]['report_date'])}.")
    ans.add("chart", kind="line", title=f"{last['market']}: speculator net position", series=[{"name": "Speculators net", "points": thin([{"t": r["report_date"], "v": r["speculator_net"]} for r in rows])}], unit="Contracts")


def answer_short(ans, sym, ents):
    ans.use("pos_short")
    rows = ans.rows("SELECT date, short_volume, total_volume FROM pos_short_volume WHERE symbol=? ORDER BY date", (sym,))
    ans.step(f"Read {len(rows)} days from pos_short_volume")
    if not rows:
        ans.lede(f"No short volume on file for {sym}. Listed US equities and ETFs are covered.")
        return
    share = [{"t": r["date"], "v": r["short_volume"] / r["total_volume"] * 100} for r in rows if r["total_volume"]]
    ans.lede(f"Short sales were {share[-1]['v']:.1f}% of reported {sym} volume on {day(share[-1]['t'])}, against a {len(share)} day average of {statistics.mean(p['v'] for p in share):.1f}%.")
    ans.add("chart", kind="line", title=f"{sym}: short sale share of reported volume", series=[{"name": "Short share", "points": share}], unit="%")
    ans.note = "Short sale volume counts trades, and is not short interest, which is the open position."


def answer_options(ans, sym, ents):
    ans.use("px_options")
    held = not ans.rows("SELECT 1 FROM sqlite_master WHERE name='px_option_summary'", show=False)
    s = [] if held else ans.rows("SELECT * FROM px_option_summary WHERE symbol=? ORDER BY date DESC LIMIT 1", (sym,))
    if not s:
        ans.lede(f"No option data is held for {sym}. Collection is on hold because Cboe and OPRA need a signed licence, even for delayed chains.")
        return
    s = s[0]
    rows = ans.rows("SELECT expiry, right, strike, open_interest, volume, iv, delta, bid, ask FROM px_option_chain WHERE symbol=? ORDER BY open_interest DESC LIMIT 15", (sym,))
    ans.step("Read the latest delayed chain")
    iv = s["iv30"]
    ans.lede(f"{sym} 30 day implied volatility is {iv:.1f}% as of {day(s['date'])}, with {s['put_call_oi']:.2f} puts open for each call." if iv else f"Latest {sym} chain from {day(s['date'])}.")
    ans.add("stats", items=[{"label": "Underlying", "value": f"${s['price']:,.2f}", "tone": ""}, {"label": "30 day implied vol", "value": f"{iv:.1f}%" if iv else "n/a", "tone": ""},
                            {"label": "Call open interest", "value": big(s["call_oi"]), "tone": ""}, {"label": "Put open interest", "value": big(s["put_oi"]), "tone": ""}])
    ans.table(["Expiry", "Type", "Strike", "Open interest", "Volume", "Bid", "Ask"], [
        [day(r["expiry"]), "Call" if r["right"] == "C" else "Put", f"{r['strike']:,.2f}", f"{r['open_interest']:,.0f}", f"{r['volume'] or 0:,.0f}", f"{r['bid']:.2f}", f"{r['ask']:.2f}"] for r in rows], title="Largest open interest")


def answer_attention(ans, syms, ents, text, d):
    ans.use("attention_wiki")
    sid = None
    if syms and ents.assets[syms[0]].get("wiki_title"):
        sid = "wiki:" + ents.assets[syms[0]]["wiki_title"]
    rows = ans.rows("SELECT series_id, title FROM ts_series WHERE dataset_id='attention_wiki'", show=False)
    if not any(r["series_id"] == sid for r in rows):
        terms = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in WORDS_STOP and w not in ("attention", "views", "wikipedia", "page", "interest", "public")]
        sid = next((r["series_id"] for r in rows if any(t in r["series_id"].lower() for t in terms)), None)
    if not sid:
        ans.lede("No attention series matches that. Ask about a large company or a topic such as recession, tariffs or the Federal Reserve.")
        return
    answer_series(ans, sid, False, d if d.start else Dates((dt.date.today() - dt.timedelta(days=1096)).isoformat(), None, "last 3 years"))


def answer_odds(ans, text):
    ans.use("geo_predictions")
    terms = fts_terms(re.sub(r"\b(odds|probability|chance|chances|polymarket|kalshi|prediction|markets?|likely|likelihood)\b", " ", text, flags=re.I), "OR")
    latest = "snapshot_at=(SELECT max(snapshot_at) FROM geo_prediction g2 WHERE g2.venue=g.venue)"
    if terms:
        rows = ans.rows(f"""SELECT g.* FROM fts_doc f JOIN geo_prediction g ON g.market_id=f.ref WHERE fts_doc MATCH ? AND f.kind='prediction' AND {latest}
                            GROUP BY g.venue, g.market_id ORDER BY g.volume DESC LIMIT 30""", (terms,))
    else:
        rows = ans.rows(f"SELECT g.* FROM geo_prediction g WHERE {latest} ORDER BY g.volume DESC LIMIT 30")
    ans.step(f"Found {len(rows)} open markets")
    if not rows:
        ans.lede("No open prediction markets match that.")
        return
    ans.lede(f"Live implied odds from {len({r['venue'] for r in rows})} venue{'s' if len({r['venue'] for r in rows}) > 1 else ''}, largest volume first. Prices are crowd bets, not forecasts from Rehyn.")
    ans.table(["Question", "Implied odds", "Volume", "Closes", "Venue"], [
        [{"v": (r["question"] or "")[:96], "href": r["url"]}, f"{(r['prob_yes'] or 0) * 100:.0f}%", big(r["volume"], "USD") if r["volume"] else "", day(r["closes"]), r["venue"]] for r in rows])


def answer_sanctions(ans, text):
    ans.use("geo_sanctions")
    terms = fts_terms(re.sub(r"\b(sanctions?|sanctioned|ofac|sdn|list|on|against)\b", " ", text, flags=re.I), "AND")
    if not terms:
        rows = ans.rows("SELECT program, count(*) n FROM geo_sanction GROUP BY program ORDER BY n DESC LIMIT 25")
        total = ans.rows("SELECT count(*) n FROM geo_sanction")[0]["n"]
        ans.lede(f"The OFAC list holds {total:,} names. These programmes are the largest.")
        ans.table(["Programme", "Names"], [[r["program"] or "", f"{r['n']:,}"] for r in rows])
        return
    rows = ans.rows("SELECT s.* FROM fts_doc f JOIN geo_sanction s ON s.uid=f.ref WHERE fts_doc MATCH ? AND f.kind='sanction' ORDER BY rank LIMIT 30", (terms,))
    ans.step(f"Found {len(rows)} names on the OFAC list")
    ans.lede(f"{len(rows)} matching name{'s' if len(rows) != 1 else ''} on the OFAC list." if rows else "No matching name on the OFAC list.")
    if rows:
        ans.table(["Name", "Type", "Programme", "Remarks"], [[r["name"] or "", r["kind"] or "Entity", r["program"] or "", (r["remarks"] or "")[:80]] for r in rows])


def answer_conflict(ans, text, d):
    ans.use("geo_conflict")
    low = text.lower()
    country = next((c for c in sorted(COUNTRIES, key=len, reverse=True) if re.search(rf"\b{c}\b", low)), None)
    where, args = "1=1", []
    if country:
        where += " AND country LIKE ?"
        args.append(f"%{country.title() if country != 'uk' else 'United Kingdom'}%")
    if d.start:
        where += " AND date_start>=?"
        args.append(d.start)
    if d.end:
        where += " AND date_start<=?"
        args.append(d.end)
    rows = ans.rows(f"SELECT substr(date_start,1,4) y, sum(deaths) deaths, count(*) n FROM geo_conflict_event WHERE {where} GROUP BY y ORDER BY y", args)
    if not rows:
        ans.lede("No conflict events match that in the UCDP record.")
        return
    top = ans.rows(f"SELECT conflict, country, sum(deaths) deaths, min(date_start) a, max(date_end) b FROM geo_conflict_event WHERE {where} GROUP BY conflict ORDER BY deaths DESC LIMIT 12", args)
    ans.step(f"Read {sum(r['n'] for r in rows):,} events from geo_conflict_event")
    place = country.title() if country else "worldwide"
    ans.lede(f"UCDP records {sum(r['deaths'] for r in rows):,} deaths in {sum(r['n'] for r in rows):,} events {('in ' + place) if country else place}, counting events with at least five deaths, through {rows[-1]['y']}.")
    ans.add("chart", kind="bars", title=f"Recorded deaths by year, {place}", bars=[{"label": r["y"], "value": r["deaths"]} for r in rows[-30:]], unit="", fmt="big")
    ans.table(["Conflict", "Country", "Deaths", "From", "To"], [[r["conflict"], r["country"], f"{r['deaths']:,}", day(r["a"]), day(r["b"])] for r in top], title="Largest conflicts in this view")


def answer_docs(ans, text, d, dataset=None):
    terms = fts_terms(strip_dates(re.sub(r"\b(statements?|fomc|federal register|executive orders?|press releases?|documents?)\b", " ", text, flags=re.I)), "AND")
    ds = dataset or ("docs_fed" if re.search(r"fomc|federal reserve|\bfed\b", text.lower()) else "docs_federal_register")
    ans.use(ds)
    where, args = "r.dataset_id=?", [ds]
    if re.search(r"executive order", text.lower()):
        where += " AND r.kind='Executive order'"
    elif re.search(r"fomc|statement", text.lower()):
        where += " AND r.kind LIKE 'Monetary%'"
    if d.start:
        where += " AND r.date>=?"
        args.append(d.start)
    if d.end:
        where += " AND r.date<=?"
        args.append(d.end)
    if terms:
        rows = ans.rows(f"SELECT r.* FROM fts_doc f JOIN doc_release r ON r.id=f.ref WHERE fts_doc MATCH ? AND f.kind='document' AND {where} ORDER BY r.date DESC LIMIT 25", [terms, *args])
    else:
        rows = ans.rows(f"SELECT r.* FROM doc_release r WHERE {where} ORDER BY r.date DESC LIMIT 25", args)
    ans.step(f"Found {len(rows)} official documents")
    ans.lede(f"{len(rows)} official document{'s' if len(rows) != 1 else ''}, newest first." if rows else "No official documents match that.")
    ans.add("items", items=[{"date": day(r["date"]), "source": r["institution"], "tag": r["kind"], "title": r["title"], "body": (r["abstract"] or "")[:260], "url": r["url"]} for r in rows])


def answer_news(ans, text, d):
    clean = strip_dates(re.sub(r"\b(news|headlines?|articles?|stories|latest|recent|coverage)\b", " ", text, flags=re.I))
    terms = fts_terms(clean, "AND") or fts_terms(text, "OR")
    where, args = "", []
    if d.start:
        where += " AND f.date>=?"
        args.append(d.start)
    if d.end:
        where += " AND f.date<=?"
        args.append(d.end)
    if not terms:
        rows = ans.rows("SELECT * FROM nw_article WHERE published IS NOT NULL ORDER BY published DESC LIMIT 25")
        hits = [{"date": day(r["published"]), "source": r["source"], "title": r["title"], "body": r["summary"] or "", "url": r["url"]} for r in rows]
        ans.use("news_rss")
        ans.lede("Latest headlines in the database.")
        ans.add("items", items=hits)
        return
    arts = ans.rows(f"""SELECT a.*, f.date d FROM fts_doc f JOIN nw_article a ON a.id=f.ref WHERE fts_doc MATCH ? AND f.kind='article'{where} ORDER BY f.date DESC LIMIT 18""", [terms, *args])
    evs = ans.rows(f"""SELECT e.* FROM fts_doc f JOIN nw_event e ON e.id=f.ref WHERE fts_doc MATCH ? AND f.kind='event'{where} ORDER BY f.date DESC LIMIT 18""", [terms, *args])
    if not arts and not evs and " AND " in terms:
        return _news_or(ans, clean, where, args)
    ans.step(f"Found {len(arts)} headlines and {len(evs)} dated events")
    _news_out(ans, arts, evs)


def _news_or(ans, clean, where, args):
    terms = fts_terms(clean, "OR")
    arts = ans.rows(f"SELECT a.*, f.date d FROM fts_doc f JOIN nw_article a ON a.id=f.ref WHERE fts_doc MATCH ? AND f.kind='article'{where} ORDER BY rank LIMIT 18", [terms, *args])
    evs = ans.rows(f"SELECT e.* FROM fts_doc f JOIN nw_event e ON e.id=f.ref WHERE fts_doc MATCH ? AND f.kind='event'{where} ORDER BY rank LIMIT 18", [terms, *args])
    ans.step(f"No exact match, widened to any word: {len(arts)} headlines and {len(evs)} events")
    _news_out(ans, arts, evs)


def _news_out(ans, arts, evs):
    import json
    if arts:
        ans.use(*{a["dataset_id"] for a in arts})
    if evs:
        ans.use("events_wiki")
    if not arts and not evs:
        ans.lede("Nothing in the news or event record matches that.")
        return
    ans.lede(f"{len(arts)} headlines and {len(evs)} dated events match, newest first.")
    if arts:
        ans.add("items", title="Headlines", items=[{"date": day(a["published"]), "source": a["source"], "title": a["title"], "body": a["summary"] or "", "url": a["url"]} for a in arts])
    if evs:
        ans.add("items", title="Dated events", items=[{"date": day(e["date"]), "source": "Wikipedia", "tag": e["category"], "title": e["text"][:240], "body": e["topic"] or "",
                                                         "url": (json.loads(e["sources"] or "[]") or [None])[0]} for e in evs])


def answer_day(ans, d, ents):
    when = d.exact
    ans.step(f"Reading {day(when)}")
    marks = ["SPX", "UKX", "NKY", "BRENT", "XAU/USD", "DXY", "VIX", "US10Y", "BTC/USD"]
    rows = []
    for s in marks:
        a = ents.assets.get(s)
        if not a:
            continue
        r = ans.rows("SELECT date, close, adj_close FROM px_daily WHERE asset_id=? AND date<=? ORDER BY date DESC LIMIT 2", (a["asset_id"], when), show=False)
        if len(r) == 2 and r[0]["date"] == when and r[1]["close"]:
            ans.use(a["price_dataset"])
            rows.append([a["name"], money(r[0]["close"], a["currency"], a["asset_class"]), cell(r[0]["close"] / r[1]["close"] - 1)])
    evs = ans.rows("SELECT * FROM nw_event WHERE date=? ORDER BY category LIMIT 24", (when,))
    fed = ans.rows("SELECT * FROM doc_release WHERE date=? LIMIT 10", (when,))
    fam = ans.rows("SELECT * FROM ev_event WHERE date=? LIMIT 8", (when,))
    if not rows and not evs and not fed:
        ans.lede(f"Nothing is recorded for {day(when)}. It may be a weekend or a date before the record starts.")
        return
    ans.lede(f"{day(when)}: {len(rows)} markets traded, with {len(evs)} events in the dated record.")
    if rows:
        ans.table(["Market", "Close", "Day move"], rows, title="Markets that day")
    if fam:
        ans.use("ev_library")
        ans.table(["Family", "Event"], [[e["family"], {"v": e["title"][:110], "href": e["source_url"]}] for e in fam], title="In the event library")
    if evs:
        import json
        ans.use("events_wiki")
        ans.add("items", title="Dated events", items=[{"date": e["category"] or "", "source": "Wikipedia", "title": e["text"][:260], "body": e["topic"] or "", "url": (json.loads(e["sources"] or "[]") or [None])[0]} for e in evs])
    if fed:
        ans.use("docs_fed")
        ans.add("items", title="Official documents", items=[{"date": day(r["date"]), "source": r["institution"], "title": r["title"], "url": r["url"], "body": ""} for r in fed])


def answer_extremes(ans, sym, ents, text, d):
    a = ents.assets[sym]
    low = text.lower()
    worst = bool(re.search(r"worst|biggest (fall|drop|loss)|largest (fall|drop)", low))
    rows = price_rows(ans, a, d)
    ans.use(a["price_dataset"])
    flagged = {r["date"] for r in ans.rows("SELECT date FROM x_price_flag WHERE asset_id=?", (a["asset_id"],), show=False)}
    moves = [(rows[i]["date"], rows[i]["adj"] / rows[i - 1]["adj"] - 1, rows[i]["close"]) for i in range(1, len(rows)) if rows[i - 1]["adj"] and rows[i]["date"] not in flagged]
    moves.sort(key=lambda x: x[1], reverse=not worst)
    ans.step(f"Ranked {len(moves):,} daily moves")
    top = moves[:15]
    if not top:
        ans.lede("Not enough history for that.")
        return
    word = "worst" if worst else "best"
    ans.lede(f"{a['name']}'s {word} day {d.label or 'on record'} was {day(top[0][0])}, at {pct(top[0][1], 2)}.")
    table = []
    for date, r, close in top:
        ev = ans.rows("SELECT text FROM nw_event WHERE date=? AND category LIKE 'Business%' LIMIT 1", (date,), show=False)
        table.append([day(date), cell(r, 2), money(close, a["currency"], a["asset_class"]), (ev[0]["text"][:90] if ev else "")])
    ans.use("events_wiki")
    ans.table(["Date", "Move", "Close", "In the news that day"], table)


def answer_rank(ans, ents, text, d):
    low = text.lower()
    worst = bool(re.search(r"worst|biggest (fall|drop|loser)|losers|fallers", low))
    col = "ytd"
    label = "Year to date"
    if re.search(r"\btoday\b|\bday\b", low):
        col, label = "r1d", "Latest day"
    elif re.search(r"\bweek\b", low):
        col, label = "r5d", "Last 5 days"
    elif re.search(r"\bmonth\b", low):
        col, label = "r20d", "Last 20 days"
    elif re.search(r"\b(12 months|one year|1 year|past year|last year)\b", low):
        col, label = "r1y", "One year"
    cls = next((c for k, c in (("etf", "ETF"), ("commodit", "Commodity"), ("crypto", "Crypto"), ("currenc", "FX"), ("index", "Index"), ("indices", "Index")) if k in low), "Equity")
    where, args = "a.asset_class=?", [cls]
    sector = next((v for k, v in SECTORS.items() if k in low), None)
    if sector:
        where += " AND a.sector=?"
        args.append(sector)
    rows = ans.rows(f"""SELECT a.symbol, a.name, a.sector, a.price_dataset, m.close, m.{col} r, m.vol20, m.as_of, a.currency, a.asset_class FROM x_asset_metric m JOIN ref_asset a USING(asset_id)
                        WHERE {where} AND m.{col} IS NOT NULL AND m.as_of>=date('now','-10 days') ORDER BY m.{col} {'ASC' if worst else 'DESC'} LIMIT 20""", args)
    ans.use("x_asset_metric", *{r["price_dataset"] for r in rows})
    ans.step(f"Ranked {cls.lower()} assets by {label.lower()}")
    if not rows:
        ans.lede("No assets match that ranking.")
        return
    ans.lede(f"{rows[0]['name']} leads the {'fallers' if worst else 'gainers'} among {(sector + ' ') if sector else ''}{cls.lower()} assets: {pct(rows[0]['r'])}, {label.lower()}.")
    ans.add("chart", kind="diverging", title=f"{label} change", bars=[{"label": r["symbol"], "value": r["r"] * 100} for r in rows[:12]], unit="%")
    ans.table(["Asset", "Symbol", "Sector", label, "Close", "Volatility"], [
        [r["name"], r["symbol"], r["sector"] or "", cell(r["r"]), money(r["close"], r["currency"], r["asset_class"]), f"{(r['vol20'] or 0) * 100:.0f}%"] for r in rows])


def answer_catalogue(ans, text):
    low = text.lower()
    rows = ans.rows("SELECT d.*, c.name category FROM cat_dataset d JOIN cat_category c ON c.id=d.category_id ORDER BY c.sort, d.name")
    if re.search(r"licen[cs]|\bfee|\bpaid|cost|free to", low):
        ans.step("Reading licence labels from the catalogue")
        held = [r for r in rows if r["rows"]]
        count = lambda t: sum(1 for r in held if r["tier"] == t)
        rows_in = lambda t: sum(r["rows"] for r in held if r["tier"] == t)
        ans.lede(f"Of the {len(held)} datasets we hold, {count('OPEN')} are free to use, {count('TERMS')} need a terms check, {count('PERMISSION')} need written permission and {count('FEE')} need a paid licence. "
                 f"{rows_in('PERMISSION') + rows_in('FEE'):,} rows cannot be shown to paying users as things stand.")
        order = {"FEE": 0, "PERMISSION": 1, "TERMS": 2, "OPEN": 3}
        ans.add("license", items=[{"id": r["id"], "name": r["name"], "tier": r["tier"], "status": r["status"], "source": r["source_name"], "licence": r["licence"],
                                   "note": r["licence_note"] or r["gap_note"] or "", "price": r["price_note"] or "", "rows": r["rows"], "terms": r["terms_url"]}
                                  for r in sorted(rows, key=lambda x: order[x["tier"]]) if r["tier"] != "OPEN"])
        return
    ans.step("Reading the catalogue")
    total = sum(r["rows"] or 0 for r in rows)
    ans.lede(f"The database holds {total:,} rows across {sum(1 for r in rows if r['rows'])} datasets, in {len({r['category'] for r in rows})} categories.")
    ans.add("license", items=[{"id": r["id"], "name": r["name"], "tier": r["tier"], "status": r["status"], "source": r["source_name"], "licence": r["licence"], "note": r["blurb"] or "", "price": "", "rows": r["rows"], "terms": r["terms_url"]} for r in rows if r["rows"]])


def answer_sql(ans, text):
    sql = text.strip().rstrip(";")
    if ";" in sql:
        ans.lede("Only one statement can run at a time.")
        return
    ans.step("Running your SQL read only")
    rows = ans.con.execute(f"SELECT * FROM ({sql}) LIMIT 200").fetchall()
    ans.sql.append(sql)
    ans.lede(f"{len(rows)} row{'s' if len(rows) != 1 else ''}{', showing the first 200' if len(rows) == 200 else ''}.")
    if rows:
        cols = list(rows[0].keys())
        ans.table(cols, [[("" if r[c] is None else (f"{r[c]:,.4g}" if isinstance(r[c], float) else str(r[c])[:120])) for c in cols] for r in rows])
    for t in re.findall(r"\b(?:from|join)\s+([a-z_]+)", sql, flags=re.I):
        for r in ans.con.execute("SELECT id FROM cat_dataset WHERE table_name=? LIMIT 4", (t.lower(),)):
            ans.use(r["id"])


def answer_search(ans, ents, text, d):
    terms = fts_terms(text, "AND") or fts_terms(text, "OR")
    ans.step("Searching all text in the database")
    if not terms:
        ans.lede("Try naming an asset, an indicator, a date or a topic.")
        return
    series = ans.rows("SELECT series_id, title, dataset_id, last_date FROM ts_series WHERE " + " AND ".join("title LIKE ?" for _ in terms.split(" AND ")) + " LIMIT 8",
                      [f"%{w.strip(chr(34))}%" for w in terms.split(" AND ")], show=False)
    if len(series) >= 1 and not re.search(r"\bnews\b", text.lower()):
        ans.step(f"Found a matching series: {series[0]['title']}")
        answer_series(ans, series[0]["series_id"], False, d)
        if len(series) > 1:
            ans.table(["Other matching series", "Latest"], [[s["title"], day(s["last_date"])] for s in series[1:]])
        return
    answer_news(ans, text, d)


def route(ans, ents):
    text = ans.q.strip()
    low = text.lower()
    d = parse_dates(text)

    if re.match(r"\s*(select|with)\b", low):
        return answer_sql(ans, text)
    if re.search(r"licen[cs]|\bneeds? (a )?fee|\bpaid data|free to use|what (data|datasets)|which datasets|list (of )?(datasets|tables)|what do you have|what.s in (the|this) database", low):
        return answer_catalogue(ans, text)
    if d.exact and re.search(r"happen|on |what|market|news", low) and not ents.find_hard(text):
        return answer_day(ans, d, ents)
    if re.fullmatch(r"\s*(on\s+)?[\d\w ,-]{6,20}\s*", low) and d.exact:
        return answer_day(ans, d, ents)

    syms = ents.find(text)
    hard = ents.find_hard(text)
    asks_after = re.search(r"\b(after|following|react|reaction|respond|response|analog|analogue|when|history of|in the wake)\b", low)
    family = next((f for p, f in FAMILIES if re.search(p, low)), None)
    if family and (asks_after or (family.startswith("Fed") and syms)):
        focus = [s for s in syms if s not in {ALIASES.get(w) for w in ("oil", "taiwan", "china") if w in low and family.startswith(("OPEC", "Taiwan", "Gulf"))}] or []
        if family.startswith("OPEC") and re.search(r"\b(brent|oil|crude)\b", low.replace("oil output", "").replace("oil production", "")):
            focus = ["BRENT"] + [s for s in focus if s != "BRENT"]
        return answer_event_study(ans, family, focus, ents, d, text)

    target = (hard or syms or [None])[0]
    if re.search(r"\byield curve\b(?! spread)", low):
        return answer_curve(ans, d)
    if target and re.search(r"revenue|\bsales\b|turnover|net income|profit|earnings|\beps\b|margin|cash flow|\bfcf\b|capex|buyback|\bdebt\b|\bcash\b|total assets|liabilities|shareholders|book value|inventor|r&d|financials|fundamentals", low):
        return answer_fundamentals(ans, target, ents, text, d)
    if target and re.search(r"\bfiling|8-k|10-k|10-q|annual report|proxy|\bsec\b", low):
        return answer_filings(ans, target, ents, text, d)
    if target and re.search(r"insider|director.{0,12}(buy|sell|sold|bought)|officer.{0,12}(buy|sell|sold|bought)", low):
        return answer_insider(ans, target, ents, d)
    if re.search(r"\b13f\b|who (owns|holds)|\bholdings\b|hedge funds?\b(?!.{0,12}(long|short))|\bfunds? (own|hold)|what does .{3,40} (own|hold)", low):
        return answer_funds(ans, text, target, ents)
    if target and re.search(r"dividend|stock split|\bsplits?\b", low):
        return answer_dividends(ans, target, ents, d)
    if re.search(r"positioning|\bcot\b|commitments? of traders|speculators?|net long|net short|hedge funds?.{0,12}(long|short)", low):
        return answer_cot(ans, text, d)
    if target and re.search(r"short (volume|interest|selling|sales?)", low):
        return answer_short(ans, target, ents)
    if target and re.search(r"\boptions?\b|put.?call|implied vol|\biv\b", low):
        return answer_options(ans, target, ents)
    if re.search(r"attention|page ?views|wikipedia views|public interest", low):
        return answer_attention(ans, syms, ents, text, d)
    if re.search(r"\bodds\b|probabilit|polymarket|kalshi|prediction market|chances? of", low):
        return answer_odds(ans, text)
    if re.search(r"sanction|\bofac\b|\bsdn\b", low) and not asks_after:
        return answer_sanctions(ans, text)
    if re.search(r"conflict|fatalit|war deaths|ucdp|battle deaths|deaths in", low):
        return answer_conflict(ans, text, d)
    if re.search(r"fomc|fed statement|executive order|federal register|press release", low):
        return answer_docs(ans, text, d)
    if re.search(r"\bnews\b|headlines?|articles?|stories|coverage", low):
        return answer_news(ans, text, d)
    if re.search(r"\b(best|worst|top|biggest|largest)\b.{0,40}\b(performers?|gainers?|losers?|fallers?|movers?|stocks?|shares|etfs?|commodit|crypto|currenc|indices)\b", low):
        return answer_rank(ans, ents, text, d)
    if target and re.search(r"\b(best|worst|biggest|largest)\b.{0,24}\b(day|days|session|fall|drop|gain)\b", low):
        return answer_extremes(ans, target, ents, text, d)

    # Country indicators: "inflation in Turkey", "GDP of Brazil", "geopolitical risk Taiwan".
    country = next((c for c in sorted(COUNTRIES, key=len, reverse=True) if re.search(rf"\b{c}\b", low)), None)
    if country and "geopolitical risk" in low:
        return answer_series(ans, f"gpr:GPRC_{COUNTRIES[country][:3]}", False, d)
    if country and country != "united states":
        code = next((c for p, c in WDI if re.search(p, low)), None)
        if code:
            return answer_series(ans, f"wdi:{COUNTRIES[country]}:{code}", False, d)

    macro = next(((sid, yoy) for p, sid, yoy in SERIES if re.search(p, low)), None)
    if macro and not hard:
        return answer_series(ans, macro[0], macro[1], d)
    if PUBLIC:
        spot = next((sid for p, sid in SPOT if re.search(p, low)), None)
        if spot:
            return answer_series(ans, spot, False, d)
        if re.search(r"\bprices?\b|\bcharts?\b|\bcloses?\b|\bcompare\b|\bvs\b|versus|perform|\breturns?\b", low):
            return not_public(ans)
    if len(hard) >= 2 or (len(syms) >= 2 and re.search(r"\bcompare\b|\bvs\b|versus|against", low)):
        return answer_compare(ans, hard if len(hard) >= 2 else syms, ents, d)
    if target and (hard or re.search(r"\bprice|chart|close|ohlc|perform|return|history|volatil|drawdown\b", low) or len(low.split()) <= 3):
        if d.exact:
            return answer_day_asset(ans, target, ents, d)
        return answer_asset(ans, target, ents, d)
    if macro:
        return answer_series(ans, macro[0], macro[1], d)
    return answer_search(ans, ents, text, d)


def answer_day_asset(ans, sym, ents, d):
    a = ents.assets[sym]
    ans.use(a["price_dataset"])
    r = ans.rows("SELECT * FROM px_daily WHERE asset_id=? AND date<=? ORDER BY date DESC LIMIT 2", (a["asset_id"], d.exact))
    if not r or r[0]["date"] != d.exact:
        ans.lede(f"{a['name']} did not trade on {day(d.exact)}." + (f" The last close before it was {money(r[0]['close'], a['currency'], a['asset_class'])} on {day(r[0]['date'])}." if r else ""))
        return
    x = r[0]
    change = x["close"] / r[1]["close"] - 1 if len(r) > 1 and r[1]["close"] else None
    ans.lede(f"{a['name']} closed at {money(x['close'], a['currency'], a['asset_class'])} on {day(x['date'])}, {pct(change, 2)} on the day.")
    fmt = lambda v: money(v, a["currency"], a["asset_class"])
    ans.add("stats", items=[{"label": "Open", "value": fmt(x["open"]), "tone": ""}, {"label": "High", "value": fmt(x["high"]), "tone": ""}, {"label": "Low", "value": fmt(x["low"]), "tone": ""},
                            {"label": "Close", "value": fmt(x["close"]), "tone": ""}, {"label": "Volume", "value": big(x["volume"]), "tone": ""}, {"label": "Day move", "value": pct(change, 2), "tone": tone(change)}])


def not_public(ans, *_):
    ans.lede("Daily market prices and the studies built on them are not in the public library. Try a company's revenue, filings or insider trades, or an economic series.")


if PUBLIC:
    answer_asset = answer_compare = answer_day = answer_day_asset = answer_event_study = answer_extremes = answer_rank = not_public
    answer_dividends = answer_short = answer_options = answer_odds = answer_funds = not_public


def ask(question):
    con = connect()
    try:
        ans = Answer(con, question)
        ans.step("Reading your question")
        try:
            route(ans, entities(con))
        except sqlite3.Error as e:
            ans.blocks = []
            ans.lede(f"That query could not run: {e}")
        if not ans.blocks:
            ans.lede("Nothing in the database matches that yet.")
        return ans.payload()
    finally:
        con.close()
