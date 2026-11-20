"""Applies the current matching rules to what is already stored: relinks headlines to tracked assets with the patterns
in news_assets.py, and re-reads stored GDELT events with the rules and sentences in s_gdelt_raw.py, dropping events no
rule keeps. Run it after changing a pattern or rule; the next sentiment run then recomputes every asset.

  python -I ingest/relink_news.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import init_db  # noqa: E402
import news_assets  # noqa: E402
import s_gdelt_raw as g  # noqa: E402

con = init_db()
match = news_assets.Matcher(news_assets.build(con))
rows = con.execute("SELECT url, title FROM nw_article WHERE dataset_id='news_gdelt' AND theme='asset'").fetchall()
links = [(url, a) for url, title in rows for a in match(title or "")]
con.execute("DELETE FROM nw_asset_link")
con.executemany("INSERT OR IGNORE INTO nw_asset_link(url, asset) VALUES(?,?)", links)
print(f"{len(rows):,} headlines, {len(links):,} links")

kept = dropped = 0
for eid, a1, c1, a2, c2, code, root, quad, mentions, place, gc in con.execute(
        "SELECT event_id, actor1, actor1_country, actor2, actor2_country, event_code, root_code, quad_class, mentions, place, place_country FROM geo_gdelt_event").fetchall():
    e = dict(a1=a1 or "", c1=c1 or "", a2=a2 or "", c2=c2 or "", code=code, root=root, quad=quad or 0, mentions=mentions or 0, place=place or "", gc=gc or "")
    hits = [a for a, rule in g.RULES.items() if rule(e)]
    text = g.sentence(e) if hits else None
    if text:
        con.execute("UPDATE geo_gdelt_event SET assets=?, sentence=? WHERE event_id=?", ("," + ",".join(hits) + ",", text, eid))
        kept += 1
    else:
        con.execute("DELETE FROM geo_gdelt_event WHERE event_id=?", (eid,))
        dropped += 1
# Sentences may have changed, so their scores are redone.
con.execute("DELETE FROM nw_sentiment WHERE ref LIKE 'gdelt-event:%'")
con.execute("DELETE FROM live_sentiment WHERE as_of=(SELECT max(as_of) FROM live_sentiment)")
con.commit()
print(f"events: {kept:,} kept, {dropped:,} dropped")
