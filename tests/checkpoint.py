"""Folds the write-ahead log back into the database. Writers slow badly once the log grows large."""
import pathlib
import sqlite3
import time

db = pathlib.Path(__file__).resolve().parent.parent / "data" / "rehyn_markets.db"
c = sqlite3.connect(db, timeout=180)
s = time.time()
print("busy, log pages, checkpointed:", c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone(), f"{time.time() - s:.1f}s")
wal = db.with_name(db.name + "-wal")
print("log now", round(wal.stat().st_size / 1e6, 1), "MB, database", round(db.stat().st_size / 1e6, 1), "MB")
