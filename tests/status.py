"""Prints collection progress without touching the database."""
import pathlib
import sqlite3

db = pathlib.Path(__file__).resolve().parent.parent / "data" / "rehyn_markets.db"
c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
for label, sql in [
    ("price bars", "select count(*) from px_daily"),
    ("company facts", "select count(*) from co_fact"),
    ("filings", "select count(*) from co_filing"),
    ("insider trades", "select count(*) from co_insider_tx"),
    ("series obs", "select count(*) from ts_obs"),
    ("gdelt articles", "select count(*) from nw_article where dataset_id='news_gdelt'"),
    ("gdelt windows done", "select count(*) from cat_gdelt_done"),
    ("rss articles", "select count(*) from nw_article where dataset_id='news_rss'"),
    ("wiki events", "select count(*) from nw_event"),
    ("wiki latest", "select max(date) from nw_event"),
    ("documents", "select count(*) from doc_release"),
    ("pageview series", "select count(*) from ts_series where dataset_id='attention_wiki'"),
    ("conflict events", "select count(*) from geo_conflict_event"),
    ("sanctions", "select count(*) from geo_sanction"),
    ("library events", "select count(*) from ev_event"),
]:
    try:
        print(f"{label:<20} {c.execute(sql).fetchone()[0]}")
    except sqlite3.Error as e:
        print(f"{label:<20} {e}")
size = sum(p.stat().st_size for p in db.parent.glob(db.name + "*"))
print(f"{'size on disk':<20} {size / 1e9:.2f} GB")
