"""Licence and coverage summary, straight from the catalogue."""
import pathlib
import sqlite3

db = pathlib.Path(__file__).resolve().parent.parent / "data" / "rehyn_markets.db"
c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
total = c.execute("SELECT sum(rows) FROM cat_dataset").fetchone()[0]
print("total rows", f"{total:,}")
for t, n, r in c.execute("SELECT tier, sum(rows>0), sum(rows) FROM cat_dataset GROUP BY tier ORDER BY sum(rows) DESC"):
    print(f"{t:<11} {n:>3} datasets {r:>12,} rows {r / total:6.1%}")
for name, r in c.execute("SELECT c.name, sum(d.rows) FROM cat_dataset d JOIN cat_category c ON c.id=d.category_id GROUP BY c.id ORDER BY c.sort"):
    print(f"{name:<28} {r:>12,}")
print("datasets listed", c.execute("SELECT count(*) FROM cat_dataset").fetchone()[0], "held", c.execute("SELECT count(*) FROM cat_dataset WHERE rows>0").fetchone()[0])
print("assets", c.execute("SELECT count(*) FROM ref_asset WHERE last_price IS NOT NULL").fetchone()[0])
print("latest run failures", c.execute("SELECT step, status FROM cat_run WHERE status IN ('failed','running') ORDER BY run_id DESC LIMIT 8").fetchall())
print("held steps", sorted({r[0] for r in c.execute("SELECT step FROM cat_run WHERE status='held'")}))
