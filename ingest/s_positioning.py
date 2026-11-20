"""Positioning and attention: CFTC futures positions, FINRA short volume, Wikipedia page views, Cboe options."""
import datetime as dt
import json
from urllib.parse import quote

import universe as U
from core import Run, fetch, restricted, upsert_series

# CFTC contract market codes for the markets Rehyn tracks.
COT_MARKETS = {
    "067651": "WTI crude", "023651": "Natural gas", "088691": "Gold", "084691": "Silver", "085692": "Copper",
    "002602": "Corn", "001602": "Wheat", "005602": "Soybeans", "083731": "Coffee", "080732": "Sugar", "073732": "Cocoa",
    "099741": "Euro FX", "096742": "British pound", "097741": "Japanese yen", "092741": "Swiss franc", "232741": "Australian dollar",
    "090741": "Canadian dollar", "095741": "Mexican peso", "098662": "US Dollar Index", "133741": "Bitcoin", "13874A": "S&P 500 E-mini",
    "209742": "Nasdaq 100 E-mini", "239742": "Russell 2000 E-mini", "043602": "10 year Treasury note", "020601": "US Treasury bond", "1170E1": "VIX futures",
}

OPTION_SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "AVGO", "JPM", "BAC", "XOM", "CVX",
                  "LMT", "BA", "DAL", "CCL", "INTC", "GLD", "USO", "TLT", "HYG", "EEM", "EWZ", "FXI", "XLE", "XLF"]


def cot(con):
    with Run(con, "cftc_cot") as run_:
        for code, name in COT_MARKETS.items():
            offset = 0
            while True:
                r = fetch("https://publicreporting.cftc.gov/resource/6dca-aqww.json", params={
                    "cftc_contract_market_code": code, "$limit": 5000, "$offset": offset, "$order": "report_date_as_yyyy_mm_dd",
                    "$select": "report_date_as_yyyy_mm_dd,open_interest_all,noncomm_positions_long_all,noncomm_positions_short_all,"
                               "comm_positions_long_all,comm_positions_short_all,nonrept_positions_long_all,nonrept_positions_short_all",
                })
                rows = r.json()
                con.executemany("INSERT OR REPLACE INTO pos_cot VALUES(?,?,?,?,?,?,?,?,?,?)", [
                    (code, name, x["report_date_as_yyyy_mm_dd"][:10], x.get("open_interest_all"), x.get("noncomm_positions_long_all"),
                     x.get("noncomm_positions_short_all"), x.get("comm_positions_long_all"), x.get("comm_positions_short_all"),
                     x.get("nonrept_positions_long_all"), x.get("nonrept_positions_short_all")) for x in rows])
                run_.rows += len(rows)
                if len(rows) < 5000:
                    break
                offset += 5000
            con.commit()


@restricted("FINRA's terms ban commercial use, building a database and scraping")
def short_volume(con, days=120):
    with Run(con, "finra_short") as run_:
        known = {r[0] for r in con.execute("SELECT symbol FROM ref_asset WHERE asset_class IN ('Equity','ETF')")}
        d = dt.date.today()
        for _ in range(days):
            d -= dt.timedelta(days=1)
            if d.weekday() >= 5:
                continue
            # Market holidays have no file, and the CDN answers those with 403 rather than 404.
            try:
                r = fetch(f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt", ok_404=True, retries=2)
            except RuntimeError:
                continue
            if r is None or r.text.lstrip().startswith("<"):
                continue
            rows = []
            for line in r.text.splitlines()[1:]:
                p = line.split("|")
                if len(p) >= 5 and p[1] in known:
                    rows.append((d.isoformat(), p[1], p[2], p[3], p[4]))
            con.executemany("INSERT OR REPLACE INTO pos_short_volume VALUES(?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)


def pageviews(con, top=200):
    """Daily Wikipedia views since 2015 for the largest assets and the attention topics."""
    with Run(con, "wiki_pageviews") as run_:
        assets = con.execute(
            """SELECT a.symbol, a.name, a.wiki_title FROM ref_asset a
               LEFT JOIN (SELECT asset_id, avg(close*volume) dollars FROM px_daily WHERE date>=date('now','-90 days') GROUP BY asset_id) v
                 ON v.asset_id=a.asset_id
               WHERE a.wiki_title IS NOT NULL ORDER BY a.asset_class<>'Equity' DESC, v.dollars DESC LIMIT ?""", (top,)
        ).fetchall()
        items = [(t, None) for t in U.ATTENTION_TOPICS] + [(a["wiki_title"], a["symbol"]) for a in assets]
        have = {r[0] for r in con.execute("SELECT series_id FROM ts_series WHERE dataset_id='attention_wiki'")}
        items = [i for i in items if f"wiki:{i[0]}" not in have]
        end = dt.date.today().strftime("%Y%m%d")
        missed = 0
        for title, symbol in items:
            page = quote(title.replace(" ", "_"), safe="")
            url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{page}/daily/20150701/{end}"
            r = fetch(url, ok_404=True, retries=2)
            if r is None:
                missed += 1
                continue
            obs = [(f"{x['timestamp'][:4]}-{x['timestamp'][4:6]}-{x['timestamp'][6:8]}", x["views"]) for x in r.json().get("items", [])]
            label = f"Wikipedia daily views: {title}" + (f" ({symbol})" if symbol else "")
            run_.rows += upsert_series(con, f"wiki:{title}", "attention_wiki", label, "Page views", "Daily", obs, None, "Attention")
            con.commit()
        run_.note(f"{len(items)} pages, {missed} not found")


@restricted("Cboe requires a signed licence, and OPRA a vendor agreement, even for delayed data")
def options(con):
    """Delayed chains from Cboe's public file. The latest chain is kept per symbol; the summary builds history day by day."""
    with Run(con, "cboe_options") as run_:
        con.execute("""CREATE TABLE IF NOT EXISTS px_option_chain(
            symbol TEXT, contract TEXT, expiry TEXT, right TEXT, strike REAL, bid REAL, ask REAL, iv REAL, delta REAL,
            open_interest REAL, volume REAL, snapshot TEXT, PRIMARY KEY(symbol, contract)) WITHOUT ROWID""")
        con.execute("""CREATE TABLE IF NOT EXISTS px_option_summary(
            symbol TEXT, date TEXT, price REAL, iv30 REAL, call_oi REAL, put_oi REAL, call_volume REAL, put_volume REAL,
            put_call_oi REAL, PRIMARY KEY(symbol, date)) WITHOUT ROWID""")
        missing = []
        for sym in OPTION_SYMBOLS:
            r = fetch(f"https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json", ok_404=True, retries=2)
            if r is None:
                missing.append(sym)
                continue
            body = r.json()
            data, stamp = body["data"], body.get("timestamp", "")
            rows, oi, vol = [], {"C": 0.0, "P": 0.0}, {"C": 0.0, "P": 0.0}
            for o in data.get("options") or []:
                code = o["option"]
                tail = code[len(sym):]
                if len(tail) < 15:
                    continue
                expiry, right, strike = f"20{tail[:2]}-{tail[2:4]}-{tail[4:6]}", tail[6], int(tail[7:]) / 1000
                oi[right] += o.get("open_interest") or 0
                vol[right] += o.get("volume") or 0
                rows.append((sym, code, expiry, right, strike, o.get("bid"), o.get("ask"), o.get("iv"), o.get("delta"), o.get("open_interest"), o.get("volume"), stamp))
            con.execute("DELETE FROM px_option_chain WHERE symbol=?", (sym,))
            con.executemany("INSERT OR REPLACE INTO px_option_chain VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.execute("INSERT OR REPLACE INTO px_option_summary VALUES(?,?,?,?,?,?,?,?,?)", (
                sym, stamp[:10], data.get("current_price"), data.get("iv30"), oi["C"], oi["P"], vol["C"], vol["P"], oi["P"] / oi["C"] if oi["C"] else None))
            con.commit()
            run_.rows += len(rows)
        if missing:
            run_.note(f"no chain for {', '.join(missing)}")


def run(con):
    for step in (cot, short_volume, pageviews, options):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
