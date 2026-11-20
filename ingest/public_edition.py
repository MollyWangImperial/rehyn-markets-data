"""Builds the public library. Data comes only from datasets with no licence fee: Free to use, and Check terms where the
only conditions are a credit line or a notice. Every other dataset is listed in the catalogue with its label, conditions
and published price, so the site keeps a full licence register, but none of its rows are copied.

Usage: python -I ingest/public_edition.py <folder for public.db and public.db.gz>

Stops with an error if a row from a dataset that is not hosted reaches the output.
"""
import datetime as dt
import lzma
import pathlib
import shutil
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "data" / "rehyn_markets.db").as_posix()
EMPTY = ("px_daily", "px_action", "ref_index_member", "ref_listing", "pos_short_volume", "ev_event", "geo_prediction",
         "x_asset_metric", "x_regime", "x_event_return", "x_price_flag", "cat_quality", "cat_run", "cat_gdelt_done")
# Hosted: no fee, no next step owed to the owner (such as a permission to ask for), and a tier that allows reuse.
HOSTED = "licence_fee='None' AND coalesce(licence_route,'')='' AND tier IN ('OPEN','TERMS') AND table_name IS NOT NULL AND rows>0"
PART = 45 * 1024 * 1024


def build(out):
    if out.exists():
        out.unlink()
    c = sqlite3.connect(f"file:{out.as_posix()}", uri=True)
    c.execute(f"ATTACH 'file:{SRC}?mode=ro' AS s")
    c.execute("PRAGMA main.synchronous=OFF")

    objects = c.execute("SELECT type, name, sql FROM s.sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'fts_doc%' AND name NOT LIKE 'sqlite_%'").fetchall()
    for kind, name, sql in objects:
        if kind == "table":
            # The public copy marks datasets it does not host as held, which the main schema did not allow before.
            c.execute(sql.replace("'not_collected','blocked')", "'not_collected','blocked','held')") if name == "cat_dataset" else sql)
    c.execute(c.execute("SELECT sql FROM s.sqlite_master WHERE name='fts_doc'").fetchone()[0])

    hosted = c.execute(f"SELECT id, table_name, row_filter FROM s.cat_dataset WHERE {HOSTED}").fetchall()
    ids = [r[0] for r in hosted]
    marks = ",".join("?" * len(ids))
    for ds, table, flt in hosted:
        if table == "ts_obs":
            # Series are copied by the dataset they belong to, so a name pattern can never pull in another dataset's series.
            c.execute("INSERT OR IGNORE INTO main.ts_obs SELECT * FROM s.ts_obs WHERE series_id IN (SELECT series_id FROM s.ts_series WHERE dataset_id=?)", (ds,))
        else:
            c.execute(f'INSERT OR IGNORE INTO main."{table}" SELECT * FROM s."{table}"' + (f" WHERE {flt}" if flt else ""))

    c.execute(f"INSERT INTO main.ts_series SELECT * FROM s.ts_series WHERE dataset_id IN ({marks})", ids)
    # The whole catalogue is listed. Datasets that are not hosted keep their labels and notes, but show no rows or dates here.
    c.execute("INSERT INTO main.cat_dataset SELECT * FROM s.cat_dataset")
    c.execute(f"""UPDATE main.cat_dataset SET rows=0, first_date=NULL, last_date=NULL, refreshed_at=NULL,
                  status=CASE WHEN status IN ('not_collected','blocked') THEN status ELSE 'held' END WHERE id NOT IN ({marks})""", ids)
    c.execute("INSERT INTO main.cat_category SELECT * FROM s.cat_category")
    c.execute("INSERT INTO main.cat_source SELECT * FROM s.cat_source")
    # Search needs to recognise companies. Sector labels and price dates stay out: GICS is licensed and the dates describe held data.
    today = dt.date.today().isoformat()
    c.execute("""INSERT INTO main.ref_asset(asset_id, symbol, name, asset_class, country, currency, cik, last_price)
                 SELECT asset_id, symbol, name, asset_class, country, currency, cik, ? FROM s.ref_asset WHERE asset_class='Equity' AND cik IS NOT NULL""", (today,))
    c.execute(f"INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT title, body, kind, ref, date, dataset FROM s.fts_doc WHERE dataset IN ({marks})", ids)
    c.commit()

    for kind, _, sql in objects:
        if kind in ("index", "view"):
            c.execute(sql)
    c.execute("INSERT INTO fts_doc(fts_doc) VALUES('optimize')")
    c.commit()
    c.execute("DETACH s")
    c.execute("VACUUM")
    c.execute("ANALYZE")
    c.commit()
    return c, set(ids)


def verify(c, ids):
    for t in EMPTY:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone():
            n = c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            assert n == 0, f"{t} has {n} rows"
    checks = {
        "ts_series": "SELECT DISTINCT dataset_id FROM ts_series",
        "nw_article": "SELECT DISTINCT dataset_id FROM nw_article",
        "doc_release": "SELECT DISTINCT dataset_id FROM doc_release",
        "fts_doc": "SELECT DISTINCT dataset FROM fts_doc",
    }
    for name, sql in checks.items():
        extra = {r[0] for r in c.execute(sql)} - ids
        assert not extra, f"{name} holds {extra}"
    n = c.execute("SELECT count(*) FROM ts_obs WHERE series_id NOT IN (SELECT series_id FROM ts_series)").fetchone()[0]
    assert n == 0, f"{n} ts_obs rows have no public series"
    fee = {r[0] for r in c.execute("SELECT id FROM cat_dataset WHERE licence_fee<>'None' OR coalesce(licence_route,'')<>'' OR tier NOT IN ('OPEN','TERMS')")}
    assert not fee & ids, f"datasets with a fee are hosted: {fee & ids}"
    shown = {r[0] for r in c.execute("SELECT id FROM cat_dataset WHERE rows>0")}
    assert shown <= ids, f"rows shown for datasets that are not hosted: {shown - ids}"
    # Each table that only belongs to datasets that are not hosted must be empty.
    for table, in c.execute(f"SELECT DISTINCT table_name FROM cat_dataset WHERE table_name IS NOT NULL AND table_name NOT IN (SELECT table_name FROM cat_dataset WHERE id IN ({','.join('?' * len(ids))}))", list(ids)).fetchall():
        if table in ("ref_asset",):
            continue
        if c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            n = c.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            assert n == 0, f"{table} belongs only to datasets that are not hosted, yet has {n} rows"
    assert c.execute("SELECT count(*) FROM ref_asset WHERE sector IS NOT NULL OR industry IS NOT NULL OR price_dataset IS NOT NULL").fetchone()[0] == 0


def main():
    folder = pathlib.Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "public.db"
    c, ids = build(out)
    verify(c, ids)
    for name, sql in (("datasets listed", "SELECT count(*) FROM cat_dataset"), ("datasets hosted", "SELECT count(*) FROM cat_dataset WHERE rows>0"),
                      ("companies", "SELECT count(*) FROM ref_asset"), ("series", "SELECT count(*) FROM ts_series"), ("indexed texts", "SELECT count(*) FROM fts_doc")):
        print(name, c.execute(sql).fetchone()[0])
    c.close()
    # xz, in parts under GitHub's recommended 50 MB file size. The site's build joins public.db.xz.000, .001 and so on, then unpacks them.
    for old in folder.glob("public.db.xz.*"):
        old.unlink()
    packed = folder / "public.db.xz"
    with open(out, "rb") as f, lzma.open(packed, "wb", preset=9) as g:
        shutil.copyfileobj(f, g, 1 << 24)
    parts = 0
    with open(packed, "rb") as f:
        while chunk := f.read(PART):
            (folder / f"public.db.xz.{parts:03d}").write_bytes(chunk)
            parts += 1
    print("db MB", out.stat().st_size // 1048576, "| xz MB", packed.stat().st_size // 1048576, "|", parts, "part" if parts == 1 else "parts")
    packed.unlink()


if __name__ == "__main__":
    main()
