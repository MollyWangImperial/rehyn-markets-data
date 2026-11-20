"""Builds a clean copy of a database, ready to upload to Turso.

Usage: python -I ingest/export_hosted.py [source.db output_folder]

With no arguments it copies the full database. That copy is private: it holds restricted data, so it must never back a public service.
For the cleared copy, pass the public.db from public_edition.py and a folder of its own.
Stops with an error if any table count differs from the source or the file fails Turso's rules.
"""
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(sys.argv[1]).resolve().as_posix() if len(sys.argv) > 2 else (ROOT / "data" / "rehyn_markets.db").as_posix()
OUT = (pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "data" / "hosted") / "rehyn_markets.db"
LIMIT = 2 * 1024 ** 3  # Turso's documented limit for creating a database from a file


def counts(c):
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'fts_doc_%' ORDER BY name")]
    return {n: c.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for f in OUT.parent.glob(OUT.name + "*"):
        f.unlink()
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    src.execute(f"VACUUM INTO '{OUT.as_posix()}'")
    want = counts(src)
    src.close()

    c = sqlite3.connect(OUT)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    got = counts(c)
    assert got == want, {k: (want.get(k), got.get(k)) for k in set(want) | set(got) if want.get(k) != got.get(k)}
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    rules = {"page_size": c.execute("PRAGMA page_size").fetchone()[0], "auto_vacuum": c.execute("PRAGMA auto_vacuum").fetchone()[0],
             "encoding": c.execute("PRAGMA encoding").fetchone()[0], "journal_mode": c.execute("PRAGMA journal_mode").fetchone()[0]}
    assert rules == {"page_size": 4096, "auto_vacuum": 0, "encoding": "UTF-8", "journal_mode": "wal"}, rules
    hits = c.execute("SELECT count(*) FROM fts_doc WHERE fts_doc MATCH 'inflation'").fetchone()[0]
    assert hits > 0, "search index returned nothing"
    c.close()

    size = OUT.stat().st_size
    assert size < LIMIT, f"{size} bytes is over the 2 GB file limit"
    (OUT.parent / "manifest.json").write_text(json.dumps({"bytes": size, "tables": want}, indent=1), encoding="utf-8")
    print(f"ready: {OUT} | {size / 1e9:.2f} GB | {sum(want.values()):,} rows in {len(want)} tables | search test {hits:,} hits")


if __name__ == "__main__":
    sys.exit(main())
