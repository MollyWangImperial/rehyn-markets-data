"""Data quality checks. Prices are compared across independent sources and stored in cat_quality."""
import numpy as np
import pandas as pd

from core import Run, now_iso

# Same quantity from two unrelated publishers: asset symbol, series id, transform on the series, label, tolerance.
PAIRS = [
    ("VIX", "cboe:VIX", lambda s: s, "VIX: Yahoo vs Cboe", 0.005),
    ("US10Y", "ust:10yr", lambda s: s, "10 year yield: Yahoo vs US Treasury", 0.02),
    ("EUR/USD", "ecb:USD", lambda s: s, "EUR/USD: Yahoo vs ECB reference rate", 0.01),
    ("BRENT", "eia:RBRTEd", lambda s: s, "Brent: Yahoo futures vs EIA spot", 0.05),
    ("WTI", "eia:RWTCd", lambda s: s, "WTI: Yahoo futures vs EIA spot", 0.03),
]


def _px(con, symbol):
    return pd.read_sql_query(
        "SELECT p.date, p.close FROM px_daily p JOIN ref_asset a USING(asset_id) WHERE a.symbol=? ORDER BY p.date",
        con, params=(symbol,), parse_dates=["date"],
    ).set_index("date")["close"]


def _ts(con, sid):
    return pd.read_sql_query("SELECT date, value FROM ts_obs WHERE series_id=? ORDER BY date", con, params=(sid,), parse_dates=["date"]).set_index("date")["value"]


def run(con):
    with Run(con, "verify") as run_:
        con.execute("""CREATE TABLE IF NOT EXISTS cat_quality(
            check_name TEXT PRIMARY KEY, kind TEXT, compared INTEGER, median_gap REAL, p99_gap REAL, passed INTEGER, detail TEXT, checked_at TEXT)""")
        stamp = now_iso()
        out = []
        for sym, sid, fn, label, tol in PAIRS:
            a, b = _px(con, sym), fn(_ts(con, sid))
            j = pd.concat([a, b], axis=1, join="inner").dropna()
            j = j[(j.iloc[:, 0] > 0) & (j.iloc[:, 1] > 0)]
            if j.empty:
                out.append((label, "cross source", 0, None, None, 0, "no overlapping dates", stamp))
                continue
            gap = (j.iloc[:, 0] / j.iloc[:, 1] - 1).abs()
            med, p99 = float(gap.median()), float(gap.quantile(0.99))
            out.append((label, "cross source", len(j), med, p99, int(med <= tol), f"median gap {med:.3%} against a tolerance of {tol:.1%}", stamp))

        bad = con.execute("SELECT count(*) FROM px_daily WHERE high < low OR close <= 0 AND asset_id NOT IN (SELECT asset_id FROM ref_asset WHERE asset_class IN ('Rates','Commodity'))").fetchone()[0]
        total = con.execute("SELECT count(*) FROM px_daily").fetchone()[0]
        out.append(("Bars with high below low, or a non-positive close", "sanity", total, None, None, int(bad / max(total, 1) < 1e-4), f"{bad:,} of {total:,} bars", stamp))

        stale = con.execute("SELECT count(*) FROM ref_asset WHERE last_price IS NOT NULL AND last_price < date('now','-10 days')").fetchone()[0]
        none = con.execute("SELECT count(*) FROM ref_asset WHERE last_price IS NULL").fetchone()[0]
        out.append(("Instruments with a price in the last 10 days", "coverage", None, None, None, int(stale == 0 and none == 0), f"{stale} stale, {none} with no prices", stamp))

        jumps = []
        for a in con.execute("SELECT asset_id, symbol FROM ref_asset WHERE asset_class='Equity'").fetchall():
            s = pd.read_sql_query("SELECT date, coalesce(adj_close, close) px FROM px_daily WHERE asset_id=? ORDER BY date", con, params=(a["asset_id"],)).set_index("date")["px"]
            r = s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
            hit = r[(r > 1.5) | (r < -0.75)]
            jumps += [(a["symbol"], d, float(v)) for d, v in hit.items()]
        out.append(("Equity days moving over +150% or under -75%", "sanity", None, None, None, int(len(jumps) < 60), f"{len(jumps)} days, for example {jumps[:4]}", stamp))

        con.executemany("INSERT OR REPLACE INTO cat_quality VALUES(?,?,?,?,?,?,?,?)", out)
        con.commit()
        run_.rows = len(out)
        for row in out:
            print(("PASS " if row[5] else "FAIL ") + row[0] + " | " + str(row[6]))
