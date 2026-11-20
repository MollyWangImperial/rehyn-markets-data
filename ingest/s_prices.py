"""Daily prices. Yahoo chart endpoint for listed instruments, Coinbase Exchange candles for crypto."""
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from core import Run, fetch, restricted

CHART ="https://query1.finance.yahoo.com/v8/finance/chart/"


EPOCH = dt.datetime(1970, 1, 1)


def _day(ts, offset):
    # Yahoo stamps each bar at the exchange open, so apply the exchange offset before taking the date.
    # Plain date arithmetic, because time.gmtime raises on Windows for anything before 1970.
    return (EPOCH + dt.timedelta(seconds=ts + offset)).strftime("%Y-%m-%d")


def yahoo_bars(feed, start):
    # range=max silently downgrades to monthly or quarterly bars, so always send explicit periods.
    r = fetch(CHART + quote(feed, safe=""), params={
        "period1": start, "period2": int(time.time()) + 86400, "interval": "1d",
        "events": "div,split", "includeAdjustedClose": "true",
    }, ok_404=True)
    if r is None:
        return None
    res = r.json()["chart"]["result"]
    if not res:
        return None
    res = res[0]
    ts = res.get("timestamp") or []
    if not ts:
        return None
    offset = res["meta"].get("gmtoffset") or 0
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    bars = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        bars.append((_day(t, offset), q["open"][i], q["high"][i], q["low"][i], c, adj[i], q["volume"][i]))
    ev = res.get("events") or {}
    acts = [(_day(int(k), offset), "dividend", v.get("amount")) for k, v in (ev.get("dividends") or {}).items()]
    for k, v in (ev.get("splits") or {}).items():
        den = v.get("denominator") or 1
        acts.append((_day(int(k), offset), "split", (v.get("numerator") or 0) / den))
    return bars, acts, res["meta"]


def write_bars(con, asset_id, bars, acts):
    con.executemany(
        "INSERT OR REPLACE INTO px_daily VALUES(?,?,?,?,?,?,?,?)",
        [(asset_id, d, o, h, l, c, a, v) for d, o, h, l, c, a, v in bars],
    )
    if acts:
        con.executemany("INSERT OR REPLACE INTO px_action VALUES(?,?,?,?)", [(asset_id, d, k, v) for d, k, v in acts])
    con.execute(
        """UPDATE ref_asset SET first_price=(SELECT min(date) FROM px_daily WHERE asset_id=?1),
             last_price=(SELECT max(date) FROM px_daily WHERE asset_id=?1) WHERE asset_id=?1""",
        (asset_id,),
    )


def yahoo_missing(con):
    yahoo(con, only_missing=True)


@restricted("Yahoo's terms bar automated collection and commercial use")
def yahoo(con, full=True, only_missing=False):
    with Run(con, "prices_yahoo") as run_:
        assets = con.execute(
            "SELECT asset_id, symbol, feed_symbol, last_price FROM ref_asset WHERE asset_class<>'Crypto'"
            + (" AND last_price IS NULL" if only_missing else "") + " ORDER BY asset_id"
        ).fetchall()
        missing = []

        def pull(a):
            start = -2208988800
            if not full and a["last_price"]:
                start = int(dt.datetime.fromisoformat(a["last_price"]).replace(tzinfo=dt.timezone.utc).timestamp()) - 7 * 86400
            try:
                return a, yahoo_bars(a["feed_symbol"], start)
            except Exception as e:
                return a, e

        with ThreadPoolExecutor(3) as ex:
            for i, (a, out) in enumerate(ex.map(pull, assets), 1):
                if out is None or isinstance(out, Exception):
                    missing.append(a["symbol"] + (f" ({type(out).__name__})" if out is not None else ""))
                    continue
                bars, acts, meta = out
                write_bars(con, a["asset_id"], bars, acts)
                con.execute(
                    "UPDATE ref_asset SET exchange=coalesce(exchange, ?), currency=coalesce(?, currency) WHERE asset_id=?",
                    (meta.get("fullExchangeName") or meta.get("exchangeName"), meta.get("currency"), a["asset_id"]),
                )
                run_.rows += len(bars)
                if i % 25 == 0:
                    con.commit()
                    print(f"  {i}/{len(assets)} assets, {run_.rows:,} bars", flush=True)
        con.commit()
        if missing:
            run_.note(f"no data for {len(missing)}: {', '.join(missing[:40])}")


@restricted("Coinbase market data terms allow personal or research use only")
def coinbase(con):
    with Run(con, "prices_crypto") as run_:
        assets = con.execute("SELECT asset_id, symbol, feed_symbol FROM ref_asset WHERE asset_class='Crypto'").fetchall()
        for a in assets:
            url = f"https://api.exchange.coinbase.com/products/{a['feed_symbol']}/candles"
            end = dt.datetime.now(dt.timezone.utc)
            bars = {}
            for _ in range(20):
                start = end - dt.timedelta(days=300)
                r = fetch(url, params={"granularity": 86400, "start": start.isoformat(), "end": end.isoformat()}, ok_404=True)
                rows = r.json() if r is not None else []
                if not rows:
                    break
                for t, low, high, op, close, vol in rows:
                    bars[time.strftime("%Y-%m-%d", time.gmtime(t))] = (op, high, low, close, close, vol)
                end = start
            if not bars:
                run_.note(f"no candles for {a['symbol']}")
                continue
            write_bars(con, a["asset_id"], [(d, *v) for d, v in sorted(bars.items())], [])
            run_.rows += len(bars)
            con.commit()
