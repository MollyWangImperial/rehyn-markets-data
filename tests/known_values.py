"""Checks the database against independently known figures, and recomputes one event study by hand."""
import pathlib
import sqlite3
import sys

db = pathlib.Path(__file__).resolve().parent.parent / "data" / "rehyn_markets.db"
c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
px = "SELECT close FROM px_daily p JOIN ref_asset a USING(asset_id) WHERE a.symbol=? AND p.date=?"
ts = "SELECT value FROM ts_obs WHERE series_id=? AND date=?"
fact = """SELECT value FROM co_fact f JOIN ref_asset a ON a.cik=f.cik WHERE a.symbol=? AND f.concept=? AND f.period_end=?
          AND julianday(f.period_end)-julianday(f.period_start) BETWEEN 340 AND 380"""

CHECKS = [
    ("S&P 500 close, Covid low", px, ("SPX", "2020-03-23"), 2237.40, 0.01),
    ("S&P 500 close, Black Monday", px, ("SPX", "1987-10-19"), 224.84, 0.01),
    ("VIX record close", px, ("VIX", "2020-03-16"), 82.69, 0.01),
    ("WTI spot went negative", ts, ("eia:RWTCd", "2020-04-20"), -36.98, 0.01),
    ("Brent spot record", ts, ("eia:RBRTEd", "2008-07-03"), 143.95, 0.01),
    ("ECB euro record high", ts, ("ecb:USD", "2008-07-15"), 1.5990, 0.0001),
    ("10 year Treasury low", ts, ("ust:10yr", "2020-08-04"), 0.52, 0.001),
    ("US unemployment peak", ts, ("fred:UNRATE", "2020-04-01"), 14.8, 0.11),
    ("Fed upper target after Covid cut", ts, ("fred:DFEDTARU", "2020-03-16"), 0.25, 0.001),
    ("Apple FY2024 revenue", fact, ("AAPL", "revenue", "2024-09-28"), 391035e6, 1e6),
    ("Apple FY2024 net income", fact, ("AAPL", "net_income", "2024-09-28"), 93736e6, 1e6),
    ("Microsoft FY2023 revenue", fact, ("MSFT", "revenue", "2023-06-30"), 211915e6, 1e6),
    ("Nvidia FY2024 revenue", fact, ("NVDA", "revenue", "2024-01-28"), 60922e6, 1e6),
]


def main():
    bad = 0
    for label, sql, args, want, tol in CHECKS:
        row = c.execute(sql, args).fetchone()
        got = row[0] if row else None
        ok = got is not None and abs(got - want) <= tol
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'} {label:<36} want {want:,.2f} got {got if got is None else format(got, ',.2f')}")

    # Recompute a 20 day return by hand for one event and compare with the stored figure.
    ev = c.execute("SELECT event_id, date, title FROM ev_event WHERE family='Fed rate cut' AND date>='2019-01-01' ORDER BY date LIMIT 1").fetchone()
    aid = c.execute("SELECT asset_id FROM ref_asset WHERE symbol='SPX'").fetchone()[0]
    stored = c.execute("SELECT base_date, r20 FROM x_event_return WHERE event_id=? AND asset_id=?", (ev[0], aid)).fetchone()
    days = c.execute("SELECT date, coalesce(adj_close, close) FROM px_daily WHERE asset_id=? AND date>=? ORDER BY date LIMIT 21", (aid, stored[0])).fetchall()
    hand = days[20][1] / days[0][1] - 1
    ok = abs(hand - stored[1]) < 1e-9
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL'} Event study recomputed: {ev[2][:44]} | base {stored[0]} ({days[0][0]}), 20 days later {days[20][0]}, stored {stored[1]:+.4%}, by hand {hand:+.4%}")
    print(f"{len(CHECKS) + 1} checks, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
