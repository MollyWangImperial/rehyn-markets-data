"""The assets news sentiment is tracked for: every asset on the site, every equity in ref_asset, the main commodities,
currencies, indices and crypto, and any asset a reader has asked for. Each has a pattern a headline must match.

Company names are matched as exact phrases with their capitals, or by a ticker in brackets such as "(NYSE: TGT)". A name
that is also an ordinary word (Target, Visa, Block) only counts when the headline reads as company news, a commodity
word (gold, silver, corn) only in market news, and a country fund only in economic or political news.
"""
import re
from dataclasses import dataclass, field

# Context a headline needs before an ambiguous name counts.
COMPANY = re.compile(r"\b(stocks?|earnings|revenue|profit|quarterly|quarter|guidance|outlook|forecast|CEO|IPO|valuation|NYSE|Nasdaq|"
                     r"layoffs|downgrade[sd]?|upgrade[sd]?|merger|acquisitions?|acquires?|acquired|buyback|dividend|analysts?|"
                     r"shareholders?|market cap|recalls?|shares (rose|fell|jumped|slid|surged|tumbled|dropped|gained|climbed|sank|"
                     r"plunged|soared|rallied|rise|fall|jump|slide|surge|tumble|drop|gain|climb|sink|plunge|soar|rally))\b", re.I)
COMMODITY = re.compile(r"\b(prices?|futures|ounces?|bullion|tonnes?|bushels?|markets?|rally|record|demand|supply|exports?|imports?|"
                       r"production|output|harvest|crops?|traders|investors|mines?|mining|reserves|ETFs?|spot|shortage|tariffs?)\b", re.I)
ECONOMY = re.compile(r"\b(econom\w*|inflation|GDP|central bank|currency|exports?|imports?|trade|budget|bonds?|debt|rates?|stocks?|"
                     r"markets?|investors|tariffs?|oil|growth|recession|elections?|president|government|fiscal|banks?|IMF)\b", re.I)

# Site id, GDELT query for the live search, pattern the text must match, whether Federal Reserve policy releases count,
# and the context the pattern needs (None: it counts on its own).
ASSETS = [
    ("BTC", "bitcoin", r"bitcoin|\bbtc\b", False, None),
    ("XAU", '("gold price" OR "gold prices" OR "price of gold" OR bullion)',
     r"bullion|gold (price|prices|futures|ETFs?|reserves|demand|miners?|market)|price of gold|spot gold|gold (rises|rose|falls|fell|hits|climbs|slips|"
     r"jumps|drops|gains|rallies|slides|surges|tumbles|steadies|edges|holds|extends|retreats|rebounds|loses)|(buy|hold|sell|own) gold", True, None),
    ("BRENT", '("Brent crude" OR "oil prices" OR "crude oil")',
     r"\bbrent (crude|oil|futures|prices?)|crude (oil|prices?|futures|exports?|imports?|output|production|inventor(y|ies)|stocks|supply|demand)|"
     r"oil (prices?|futures|market|output|production|supply|demand|exports?|imports?)|\bOPEC\b", False, None),
    ("KC", '(arabica OR "coffee prices" OR "coffee futures")', r"coffee|arabica", False, COMMODITY),
    ("NVDA", "nvidia", r"nvidia", False, None),
    ("AAPL", '(Apple AND (iPhone OR shares OR stock OR "Tim Cook"))', r"\bApple\b", False, re.compile(COMPANY.pattern + r"|iPhone|iPad|App Store|Tim Cook", re.I)),
    ("INTC", '(Intel AND (chip OR chips OR shares OR stock OR foundry))', r"\bIntel\b", False, re.compile(COMPANY.pattern + r"|\bchips?\b|foundry|processors?|semiconductor", re.I)),
    ("TSM", '(TSMC OR "Taiwan Semiconductor")', r"tsmc|taiwan semiconductor", False, None),
    ("GFS", "GlobalFoundries", r"globalfoundries", False, None),
    ("XOM", '(ExxonMobil OR "Exxon Mobil" OR Exxon)', r"exxon", False, None),
    ("CVX", '(Chevron AND (oil OR shares OR stock OR Hess))', r"\bChevron\b", False, None),
    ("OXY", '"Occidental Petroleum"', r"occidental petroleum|\bOxy\b", False, None),
    ("EQNR", "Equinor", r"equinor", False, None),
    ("EC", "Ecopetrol", r"ecopetrol", False, None),
    ("LMT", '"Lockheed Martin"', r"lockheed", False, None),
    ("BA.", '"BAE Systems"', r"bae systems", False, None),
    ("ERJ", "Embraer", r"embraer", False, None),
    ("DAL", '"Delta Air Lines"', r"delta air", False, None),
    ("CCL", '("Carnival Corp" OR "Carnival Cruise")', r"carnival (corp|cruise|shares|stock)", False, None),
    ("RYAAY", "Ryanair", r"ryanair", False, None),
    ("DOW", '("Dow Inc" OR "Dow Chemical")', r"dow inc|dow chemical", False, None),
    ("DHI", '("D.R. Horton" OR "DR Horton")', r"d\.?r\.? horton", True, None),
    ("SCHW", '"Charles Schwab"', r"schwab", True, None),
    ("MELI", '(MercadoLibre OR "Mercado Libre")', r"mercado ?libre", False, None),
    ("CIB", "Bancolombia", r"bancolombia", False, None),
    ("KRE", '("regional banks" OR "regional bank" OR "regional lenders")', r"regional (bank|lender)", True, None),
    ("QQQ", '(Nasdaq AND (stocks OR index OR tech))', r"nasdaq", True, None),
    ("IWM", '("Russell 2000" OR "small caps" OR "small-cap stocks")', r"russell 2000|small.?cap (stocks|shares|index)|small caps", True, None),
    ("SPY", '("S&P 500" OR "Wall Street stocks")', r"s&p 500|\bS&P\b|wall street (stocks|shares|rally|slump|closes|ends|opens)|stock market", True, None),
    ("HSI", '("Hang Seng" OR "Hong Kong stocks" OR "Hong Kong shares")', r"hang seng|hong kong (stocks|shares)", False, None),
    ("SX5E", '("Euro Stoxx" OR "European stocks" OR "European shares")', r"stoxx|european (stocks|shares|equities|markets)", False, None),
    ("EWZ", '(Bovespa OR Ibovespa OR "Brazilian stocks" OR "Brazil economy")', r"bovespa|\bbrazil(ian)?\b", False, ECONOMY),
    ("GXG", '(Colombia AND (economy OR markets OR stocks OR peso))', r"\bcolombia(n)?\b", False, ECONOMY),
    ("EEM", '("emerging markets" AND (stocks OR equities OR assets OR currencies))', r"emerging.market", True, None),
    ("US2Y", '("Treasury yields" OR "two-year yield" OR "2-year yield" OR "Treasury bonds")',
     r"treasury (yields?|bonds?|notes?|bills?|market)|treasuries|bond yields?|(2|two|10|ten|30|5|five)-year (yield|note|treasury)", True, None),
    ("TLT", '("Treasury bonds" OR "long-term Treasuries" OR "bond market" OR "30-year yield")',
     r"treasury (yields?|bonds?|market)|treasuries|bond (market|yields?)|(10|ten|30|thirty)-year (yield|bond|treasury)", True, None),
    ("DXY", '("dollar index" OR "U.S. dollar" OR "US dollar" OR greenback)',
     r"U\.?S\.? dollar|dollar index|greenback|\bdollar (rises|falls|slides|gains|weakens|strengthens|rallies|slumps|climbs|drops|edges|steadies|firms)", True, None),
    ("EUR/USD", '(euro AND dollar)', r"\beuro\b", True, re.compile(ECONOMY.pattern + r"|dollar|ECB|currenc", re.I)),
    ("USD/JPY", '(yen AND dollar)', r"\byen\b", True, None),
    ("CHF/USD", '"Swiss franc"', r"swiss franc", False, None),
    ("INR/USD", '("Indian rupee" OR rupee)', r"rupee", False, None),
    ("TWD/USD", '("Taiwan dollar" OR "Taiwanese dollar")', r"taiwan(ese)? dollar", False, None),
    ("USD/COP", '("Colombian peso" OR "peso colombiano")', r"colombian peso", False, None),
]
SITE_IDS = {a[0] for a in ASSETS}

# Commodities, currencies, indices and crypto in ref_asset that are not site assets: pattern and the context it needs.
MACRO = {
    "WTI": (r"\bWTI\b|west texas intermediate", None), "NATGAS": (r"natural gas|\bLNG\b|henry hub", None), "COPPER": (r"\bcopper\b", COMMODITY),
    "XAG/USD": (r"\bsilver\b", COMMODITY), "PLATINUM": (r"platinum", COMMODITY), "PALLADIUM": (r"palladium", COMMODITY), "WHEAT": (r"\bwheat\b", COMMODITY),
    "CORN": (r"\bcorn\b", COMMODITY), "SOY": (r"soybeans?|\bsoy\b", COMMODITY), "SUGAR": (r"\bsugar\b", COMMODITY), "COCOA": (r"\bcocoa\b", COMMODITY),
    "COTTON": (r"\bcotton\b", COMMODITY), "CATTLE": (r"\bcattle\b", COMMODITY), "HEATOIL": (r"heating oil|\bdiesel\b", COMMODITY),
    "RBOB": (r"gasoline|petrol price", None), "ETH/USD": (r"\bethereum\b|\bether\b|\bETH\b", None), "SOL/USD": (r"\bsolana\b", None),
    "XRP/USD": (r"\bXRP\b", None), "DOGE/USD": (r"dogecoin", None), "ADA/USD": (r"\bcardano\b", None), "LINK/USD": (r"\bchainlink\b", None),
    "LTC/USD": (r"litecoin", None), "AUD/USD": (r"australian dollar|\baussie dollar", None), "GBP/USD": (r"\bsterling\b|british pound", None),
    "USD/BRL": (r"brazilian real", None), "USD/CAD": (r"canadian dollar|\bloonie\b", None), "USD/CNY": (r"\byuan\b|renminbi", None),
    "USD/KRW": (r"korean won", None), "USD/MXN": (r"mexican peso", None), "USD/RUB": (r"\brouble\b|\bruble\b", None),
    "USD/TRY": (r"turkish lira|\blira\b", None), "USD/ZAR": (r"south african rand", None),
    "DAX": (r"\bDAX\b|german (stocks|shares)", None), "CAC": (r"cac 40|french (stocks|shares)", None), "UKX": (r"\bFTSE\b|london (stocks|shares)", None),
    "NKY": (r"nikkei|japanese (stocks|shares)|tokyo (stocks|shares)", None), "KOSPI": (r"kospi|korean (stocks|shares)", None),
    "SHCOMP": (r"shanghai composite|csi 300|chinese (stocks|shares)|china (stocks|shares)", None), "TAIEX": (r"taiex|taiwan (stocks|shares)", None),
    "SENSEX": (r"sensex|\bnifty\b|indian (stocks|shares)", None), "ASX200": (r"\bASX\b|australian (stocks|shares)", None),
    "TSX": (r"\bTSX\b|canadian (stocks|shares)", None), "IPC": (r"mexican (stocks|shares)", None), "DJI": (r"dow jones industrial|\bthe dow\b", None),
    "VIX": (r"\bVIX\b|volatility index|fear gauge", None),
}
# Ids the site or ref_asset use for an asset tracked under another id. The site maps these the same way.
ALIASES = {"BTC/USD": "BTC", "XAU/USD": "XAU", "GLD": "XAU", "USD/INR": "INR/USD", "USD/CHF": "CHF/USD", "USD/TWD": "TWD/USD",
           "SPX": "SPY", "NDX": "QQQ", "IXIC": "QQQ", "RUT": "IWM", "IBOV": "EWZ", "US10Y": "TLT", "US30Y": "TLT", "US5Y": "US2Y", "US3M": "US2Y"}
# Names a company is commonly called besides its listed name.
ALSO = {"GOOGL": ["Google"], "GOOG": ["Google"], "META": ["Facebook"], "F": ["Ford"], "BRK.B": ["Berkshire Hathaway", "Berkshire"],
        "GS": ["Goldman Sachs", "Goldman"], "JPM": ["JPMorgan"], "BAC": ["Bank of America"], "WFC": ["Wells Fargo"], "NOC": ["Northrop"],
        "RTX": ["Raytheon"], "KO": ["Coca-Cola"], "MCD": ["McDonald's"], "DIS": ["Disney"], "TSLA": ["Tesla"], "MSFT": ["Microsoft"],
        "AMZN": ["Amazon.com"], "WMT": ["Walmart"], "BA": ["Boeing"], "UNH": ["UnitedHealth"], "PG": ["Procter & Gamble", "P&G"]}

LEGAL = re.compile(r"\b(incorporated|inc|corporation|corp|company|co|plc|ltd|limited|holdings?|group|class [a-c]|n\.?v|s\.?a|ag|se|the)\b\.?", re.I)
COMMON = set("""general american united first national international global southern northern eastern western pacific public royal digital
energy health capital financial target visa oracle block match ball fox news booking progressive discover paramount domino gap snap
mosaic waste live crown dollar regions state street equity simon genuine consolidated universal republic stryker motors steel amazon
alphabet best home church marathon texas illinois charles hartford cincinnati rocket alexandria arab""".split())
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&.'’-]*|&")
# Words next to an ordinary word that show it is not the company: "price target", "Target Price", "its target".
SOFT_STOP = {"price", "its", "their", "his", "her", "a", "an", "sets", "set", "raises", "raised", "cuts", "cut", "lowers", "lowered", "new",
             "revenue", "marketing", "earnings", "inflation", "growth", "sales", "profit", "on", "off", "hits", "hit", "misses", "beats", "student", "work", "travel",
             "valuation", "ambitious", "annual", "emissions", "climate", "shareholder-approved", "500", "the", "our", "your", "key", "main", "primary"}
SOFT_NEXT = {"shares", "stock", "stocks", "stores", "store", "ceo", "corp", "inc", "earnings", "sales", "results", "reports", "posts", "beats", "misses",
             "cuts", "raises", "says", "plans", "announces", "names", "sees", "expects", "shoppers", "customers", "recalls", "unveils", "launches",
             "lifts", "lowers", "slashes", "warns", "reported", "agrees", "buys", "sells", "acquires", "settles", "sues", "invests", "hires", "layoffs"}
TICKER = re.compile(r"\((?:NYSE|NASDAQ|Nasdaq|LSE|TSX)?:?\s?([A-Z][A-Z.]{0,6})\)")


@dataclass
class Asset:
    """rx counts on its own; weak counts only with ctx in the same text. Equities also list their names for fast lookup."""
    id: str
    name: str
    rx: re.Pattern = None
    query: str = ""
    fed: bool = False
    weak: re.Pattern = None
    ctx: re.Pattern = COMPANY
    names: list = field(default_factory=list)   # exact phrases that count on their own
    soft: list = field(default_factory=list)    # exact phrases that need ctx

    def matches(self, text):
        return bool(self.rx and self.rx.search(text)) or bool(self.weak and self.weak.search(text) and self.ctx.search(text))


def _equity(symbol, name):
    core = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9&.'’ -]+", " ", LEGAL.sub("", name))).strip(" .,-")
    if len(core) < 3:
        return None
    names, soft = [core] + ALSO.get(symbol, []), []
    if len(core.split()) == 1 and (len(core) <= 4 or core.lower() in COMMON):
        names.remove(core)
        soft.append(core)
    alt = lambda xs: "|".join(re.escape(x) for x in sorted(xs, key=len, reverse=True))  # noqa: E731
    tick = re.escape(symbol.split(".")[0])
    rx = re.compile((r"\b(" + alt(names) + r")\b|" if names else "") + r"\((?:NYSE|NASDAQ|Nasdaq|LSE|TSX)?:?\s?" + tick + r"\)")
    return Asset(symbol, name, rx, f'"{core}"', weak=re.compile(r"\b(" + alt(soft) + r")\b") if soft else None, names=names, soft=soft)


FUND = re.compile(r"\b(ishares|spdr|vanguard|invesco|global x|vaneck|wisdomtree|proshares|direxion|first trust|etf|etn|trust|fund|"
                  r"index fund|ordinary shares|class [a-c]|adr|ads|the)\b\.?", re.I)


def requested(asset_id, name):
    """An asset a reader asked for, matched by its name without fund family or legal words ("iShares Russell 2000 ETF"
    becomes "Russell 2000"), and by its ticker in brackets. A short one word name needs company news around it."""
    clean = lambda s: re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9&.'’ -]+", " ", s)).strip(" .,-")  # noqa: E731
    core = clean(LEGAL.sub("", FUND.sub("", name or ""))) or clean(name or "") or asset_id
    names = sorted({core, clean(name or "")} - {""}, key=len, reverse=True)
    tick = re.escape(asset_id.split("/")[0].split(".")[0])
    alt = "|".join(re.escape(x) for x in names)
    ticker = r"\((?:NYSE|NASDAQ|Nasdaq|LSE|TSX)?:?\s?" + tick + r"\)"
    if len(core.split()) == 1 and (len(core) <= 4 or core.lower() in COMMON):
        a = Asset(asset_id, name, re.compile(ticker), f'"{core}"', weak=re.compile(r"\b(" + alt + r")\b"))
    else:
        a = Asset(asset_id, name, re.compile(r"\b(" + alt + r")\b|" + ticker, re.I), f'"{core}"')
    a.search = core
    return a


def build(con):
    """Every tracked asset: site assets first, then assets readers asked for, ref_asset equities and the macro list."""
    out = []
    for a, q, p, fed, ctx in ASSETS:
        rx = re.compile(p, re.I)
        out.append(Asset(a, a, None, q, fed, weak=rx, ctx=ctx) if ctx else Asset(a, a, rx, q, fed))
    seen = set(SITE_IDS) | set(ALIASES)
    for asset, name in con.execute("SELECT asset, name FROM live_sentiment_request WHERE status IN ('pending','running','done')"):
        if asset not in seen and name:
            out.append(requested(asset, name))
            seen.add(asset)
    for sym, name, cls in con.execute("SELECT symbol, name, asset_class FROM ref_asset WHERE name IS NOT NULL ORDER BY symbol"):
        if sym in seen:
            continue
        if cls == "Equity":
            a = _equity(sym, name)
        elif sym in MACRO:
            p, ctx = MACRO[sym]
            a = Asset(sym, name, None, weak=re.compile(p, re.I), ctx=ctx) if ctx else Asset(sym, name, re.compile(p, re.I))
        else:
            a = None
        if a:
            out.append(a)
            seen.add(sym)
    return out


class Matcher:
    """Finds the tracked assets a headline names. Company names are looked up as exact phrases of up to six words and
    tickers in brackets by symbol; the hundred or so pattern based assets are checked one by one."""

    def __init__(self, assets):
        self.phrases, self.tickers, self.patterned = {}, {}, []
        for a in assets:
            if a.names or a.soft:
                for p in a.names:
                    self.phrases.setdefault(p, []).append((a, True))
                for p in a.soft:
                    self.phrases.setdefault(p, []).append((a, False))
                self.tickers.setdefault(a.id.split(".")[0], a)
            else:
                self.patterned.append(a)
        self.longest = max((len(p.split()) for p in self.phrases), default=1)

    def __call__(self, text):
        found = {}
        words = [re.sub(r"(['’]s|[.'’-]+)$", "", w) for w in WORD.findall(text)]
        for n in range(1, self.longest + 1):
            for i in range(len(words) - n + 1):
                for a, strong in self.phrases.get(" ".join(words[i:i + n]), ()):
                    # An ordinary word used as a name counts when a company verb or noun follows it ("Target cuts", "Visa
                    # shares"), or when it opens a headline that reads as company news, and never after "price" or "its".
                    before = words[i - 1].lower() if i else ""
                    after = words[i + n].lower() if i + n < len(words) else ""
                    if strong or (before not in SOFT_STOP and (after in SOFT_NEXT or (i == 0 and a.ctx.search(text)))):
                        found[a.id] = a
        for m in TICKER.finditer(text):
            a = self.tickers.get(m.group(1).split(".")[0])
            if a:
                found[a.id] = a
        for a in self.patterned:
            if a.id not in found and a.matches(text):
                found[a.id] = a
        return list(found)
