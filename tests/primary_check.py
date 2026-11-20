"""Compares each primary series with the held FRED copy over the dates they share.

A large gap means the wrong series or a parsing fault. Run: python -I tests/primary_check.py
"""
import pathlib
import sqlite3
import statistics

DB = (pathlib.Path(__file__).resolve().parent.parent / "data" / "rehyn_markets.db").as_posix()
PAIRS = [
    ("frb:effr", "fred:DFF", 1, 0.02), ("frb:m2", "fred:M2SL", 1, 0.5), ("frb:assets", "fred:WALCL", 1, 0.5),
    ("frb:usd_broad", "fred:DTWEXBGS", 1, 0.5), ("frb:ip", "fred:INDPRO", 1, 0.5),
    ("ust:real_10yr", "fred:DFII10", 1, 0.02), ("ust:spread_10y2y", "fred:T10Y2Y", 1, 0.02), ("ust:spread_10y3m", "fred:T10Y3M", 1, 0.02),
    ("ust:breakeven_10y", "fred:T10YIE", 1, 0.02), ("ust:breakeven_5y", "fred:T5YIE", 1, 0.02), ("pmms:30y", "fred:MORTGAGE30US", 1, 0.02),
]


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bad = 0
    for a, b, scale, tol in PAIRS:
        rows = c.execute("SELECT x.value*?, y.value FROM ts_obs x JOIN ts_obs y ON y.date=x.date AND y.series_id=? WHERE x.series_id=?", (scale, b, a)).fetchall()
        if not rows:
            print(f"NO OVERLAP {a} {b}")
            bad += 1
            continue
        if "spread" in a or "breakeven" in a or "real" in a or "effr" in a or "pmms" in a:
            gaps = [abs(x - y) for x, y in rows]
        else:
            gaps = [abs(x / y - 1) * 100 for x, y in rows if y]
        med, worst = statistics.median(gaps), max(gaps)
        ok = med <= tol
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {a:20} vs {b:20} {len(rows):>6} shared  median gap {med:.4f}  worst {worst:.3f}")
    fy = c.execute("SELECT sum(value)/1e9 FROM ts_obs WHERE series_id='fiscal:deficit_month' AND date BETWEEN '2024-10-01' AND '2025-09-01'").fetchone()[0]
    fred = c.execute("SELECT value/1e3 FROM ts_obs WHERE series_id='fred:FYFSD' AND date='2025-09-30'").fetchone()
    print(f"FY2025 deficit from months {fy:.1f}bn, FRED FYFSD {fred[0] if fred else None}bn")
    print("months", c.execute("SELECT count(*), min(date), max(date) FROM ts_obs WHERE series_id='fiscal:deficit_month'").fetchone())
    print("debt", c.execute("SELECT min(date), max(date), count(*) FROM ts_obs WHERE series_id='fiscal:debt_total'").fetchone())
    print("failed checks:", bad)


if __name__ == "__main__":
    main()
