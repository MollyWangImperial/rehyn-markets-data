"""Instrument master: index members from Wikipedia, US listings from Nasdaq Trader, plus universe.py."""
import re

from bs4 import BeautifulSoup

import universe as U
from core import Run, fetch, restricted

WIKI_API = "https://en.wikipedia.org/w/api.php"


def wiki_html(page):
    r = fetch(WIKI_API, params={"action": "parse", "page": page, "format": "json", "prop": "text", "redirects": 1})
    return BeautifulSoup(r.json()["parse"]["text"]["*"], "lxml")


def _cells(tr):
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]


def _table_with(soup, *needles):
    """First wikitable whose header row contains every needle."""
    for t in soup.find_all("table", class_="wikitable"):
        head = [h.lower() for h in _cells(t.find("tr"))]
        if all(any(n in h for h in head) for n in needles):
            return t, head
    return None, []


def _col(head, needle):
    return next((i for i, h in enumerate(head) if needle in h), None)


def sp500(con):
    t, head = _table_with(wiki_html("List_of_S&P_500_companies"), "symbol", "gics sector")
    if t is None:
        raise RuntimeError("S&P 500 table not found")
    ix = {k: _col(head, k) for k in ("symbol", "security", "gics sector", "sub-industry", "headquarters", "date added", "cik")}
    rows = []
    for tr in t.find_all("tr")[1:]:
        c = _cells(tr)
        if len(c) < 6:
            continue
        cik = re.sub(r"\D", "", c[ix["cik"]]) if ix["cik"] is not None else ""
        rows.append(("SP500", c[ix["symbol"]], c[ix["security"]], c[ix["gics sector"]], c[ix["sub-industry"]],
                     c[ix["headquarters"]], c[ix["date added"]], int(cik) if cik else None))
    con.executemany("INSERT OR REPLACE INTO ref_index_member VALUES(?,?,?,?,?,?,?,?)", rows)
    return rows


def nasdaq100(con):
    # Wikipedia dropped the ticker table from this page, so read Nasdaq's own list.
    r = fetch("https://api.nasdaq.com/api/quote/list-type/nasdaq100", timeout=30, retries=2)
    data = r.json()["data"]["data"]["rows"]
    rows = [("NDX", d["symbol"], d["companyName"], None, None, None, None, None) for d in data]
    con.executemany("INSERT OR REPLACE INTO ref_index_member VALUES(?,?,?,?,?,?,?,?)", rows)
    return rows


def ftse100(con):
    t, head = _table_with(wiki_html("FTSE_100_Index"), "ticker", "company")
    if t is None:
        raise RuntimeError("FTSE 100 table not found")
    sym, name, sec = _col(head, "ticker"), _col(head, "company"), _col(head, "sector")
    rows = []
    for tr in t.find_all("tr")[1:]:
        c = _cells(tr)
        if len(c) <= max(sym, name):
            continue
        rows.append(("UKX", c[sym].rstrip("."), c[name], c[sec] if sec is not None and sec < len(c) else None, None, None, None, None))
    con.executemany("INSERT OR REPLACE INTO ref_index_member VALUES(?,?,?,?,?,?,?,?)", rows)
    return rows


def listings(con):
    n = 0
    r = fetch("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
    rows = []
    for line in r.text.splitlines()[1:]:
        p = line.split("|")
        if len(p) < 7 or p[0].startswith("File Creation") or p[3] == "Y":
            continue
        rows.append((p[0], p[1], "NASDAQ", 1 if p[6] == "Y" else 0, None))
    r = fetch("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
    names = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}
    for line in r.text.splitlines()[1:]:
        p = line.split("|")
        if len(p) < 7 or p[0].startswith("File Creation") or p[6] == "Y":
            continue
        rows.append((p[0], p[1], names.get(p[2], p[2]), 1 if p[4] == "Y" else 0, None))
    con.executemany("INSERT OR REPLACE INTO ref_listing VALUES(?,?,?,?,?)", rows)
    n += len(rows)
    r = fetch("https://www.sec.gov/include/ticker.txt")
    ciks = []
    for line in r.text.splitlines():
        p = line.split("\t")
        if len(p) == 2 and p[1].isdigit():
            ciks.append((int(p[1]), p[0].upper()))
    con.executemany("UPDATE ref_listing SET cik=? WHERE symbol=?", ciks)
    return n, {s: c for c, s in ciks}


def add_asset(con, symbol, feed, dataset, name, cls, currency=None, country=None, sector=None, industry=None,
              cik=None, wiki=None, exchange=None):
    con.execute(
        """INSERT INTO ref_asset(symbol, feed_symbol, price_dataset, name, asset_class, exchange, currency, country,
             sector, industry, cik, wiki_title) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET feed_symbol=excluded.feed_symbol, price_dataset=excluded.price_dataset,
             name=coalesce(excluded.name, name), asset_class=excluded.asset_class,
             exchange=coalesce(excluded.exchange, exchange), currency=coalesce(excluded.currency, currency),
             country=coalesce(excluded.country, country), sector=coalesce(excluded.sector, sector),
             industry=coalesce(excluded.industry, industry), cik=coalesce(excluded.cik, cik),
             wiki_title=coalesce(excluded.wiki_title, wiki_title)""",
        (symbol, feed, dataset, name, cls, exchange, currency, country, sector, industry, cik, wiki),
    )


@restricted("Reads Nasdaq lists, whose terms are personal and non-commercial")
def run(con):
    with Run(con, "reference") as run_:
        sp = sp500(con)
        try:
            nd = nasdaq100(con)
        except Exception as e:
            nd = []
            run_.note(f"Nasdaq-100 list unavailable, most members are in the S&P 500 anyway: {e}")
        uk = ftse100(con)
        n_list, cik_of = listings(con)
        run_.note(f"SP500 {len(sp)}, NDX {len(nd)}, UKX {len(uk)}, US listings {n_list}")

        for _, sym, name, sector, sub, hq, _, cik in sp:
            country = "United States"
            add_asset(con, sym, sym.replace(".", "-"), "px_equity_us", name, "Equity", "USD", country, sector, sub,
                      cik or cik_of.get(sym), name)
        for _, sym, name, sector, sub, _, _, _ in nd:
            add_asset(con, sym, sym.replace(".", "-"), "px_equity_us", name, "Equity", "USD", None, sector, sub,
                      cik_of.get(sym), name)
        for _, sym, name, sector, _, _, _, _ in uk:
            add_asset(con, f"{sym}.L", f"{sym.replace('.', '-')}.L", "px_equity_global", name, "Equity", "GBP",
                      "United Kingdom", sector, None, None, name, "LSE")
        for feed, sym, name, cur, country, wiki in U.EXTRA_EQUITIES:
            ds = "px_equity_us" if cur == "USD" else "px_equity_global"
            add_asset(con, sym, feed, ds, name, "Equity", cur, country, None, None, cik_of.get(sym), wiki)
        for sym, name in U.ETFS:
            add_asset(con, sym, sym, "px_etf", name, "ETF", "USD", cik=None)
        for feed, sym, name, cur, country, wiki in U.INDICES:
            add_asset(con, sym, feed, "px_index", name, "Index", cur, country, wiki=wiki)
        for feed, sym, name, cur, country, wiki in U.RATES:
            add_asset(con, sym, feed, "px_rates_yahoo", name, "Rates", cur, country, wiki=wiki)
        for feed, sym, name, cur, country, wiki in U.COMMODITIES:
            add_asset(con, sym, feed, "px_commodity_futures", name, "Commodity", cur, country, wiki=wiki)
        for feed, sym, name, cur, country, wiki in U.FX:
            add_asset(con, sym, feed, "px_fx_yahoo", name, "FX", cur, country, wiki=wiki)
        for feed, sym, name, wiki in U.CRYPTO:
            add_asset(con, sym, feed, "px_crypto", name, "Crypto", "USD", wiki=wiki, exchange="Coinbase")
        con.commit()
        run_.rows = con.execute("SELECT count(*) FROM ref_asset").fetchone()[0]
