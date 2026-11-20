"""Runs the news sentiment pipeline (s_sentiment.py) and sends what changed to Turso, which the site's AI service reads:
news sentiment's own database when SENTIMENT_DB_URL and SENTIMENT_DB_TOKEN are in data/collector.env, otherwise the
Rehyn database. Meant to run every 15 minutes from Windows Task Scheduler; the daily collector also runs it.

Writes are kept to what changed: tables keep their rows in the primary key with no extra index (Turso counts each index
entry as a write), schema statements run only when a table is missing, and a reading is resent only when its rounded
figures change.

  python -I ingest/sentiment_job.py

Only the live_ tables are written, and only rows that changed: each asset's latest reading, its new items and the items
that dropped out. The first send, or one after a failed send, writes everything. Requests readers made on the site
are read from Turso first and marked done after. A log is appended to data/daily/sentiment.log.
"""
import argparse
import datetime as dt
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core import ROOT, init_db  # noqa: E402
import checkin  # noqa: E402
import model_store  # noqa: E402
import s_sentiment  # noqa: E402
import sync_turso  # noqa: E402

TABLES = ("live_sentiment_latest", "live_sentiment_item", "live_sentiment_daily", "live_sentiment_request")
RESYNC = ROOT / "data" / "sentiment_resync"


def target():
    """Where the results go: news sentiment's own Turso database when SENTIMENT_DB_URL and SENTIMENT_DB_TOKEN (a token
    that can write) are in data/collector.env, otherwise the Rehyn database. The model is always read from the Rehyn
    database, which only costs reads."""
    cfg = {}
    for line in (ROOT / "data" / "collector.env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    if cfg.get("SENTIMENT_DB_URL") and cfg.get("SENTIMENT_DB_TOKEN"):
        return sync_turso.Remote(cfg["SENTIMENT_DB_URL"], cfg["SENTIMENT_DB_TOKEN"])
    return model_store.remote()


def _insert(table, rows):
    return (f"INSERT OR REPLACE INTO {table} VALUES " + ",".join(["(" + ",".join("?" * len(rows[0])) + ")"] * len(rows)), [v for row in rows for v in row])


def prepare(con, r):
    """Creates the live_ tables in Turso when missing and copies new requests down. Returns True when Turso is empty.
    Schema statements run only when something is missing, so a normal run writes nothing but data."""
    there = {row[0] for row in r.rows("SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
    # A latest table from the earlier layout is replaced; the run then sends everything.
    if "live_sentiment_latest" in there and "s30" not in {row[1] for row in r.rows("SELECT cid, name FROM pragma_table_info('live_sentiment_latest')")}:
        r.run([("DROP TABLE live_sentiment_latest", [])])
        there.discard("live_sentiment_latest")
    for name, sql in con.execute(f"SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN {TABLES}"):
        if name not in there:
            r.run([(sql, [])])
    old = [f"DROP {kind} {name}" for kind, name in (("INDEX", "ix_live_item_date"), ("TABLE", "x_sentiment"), ("TABLE", "x_sentiment_item")) if name in there]
    if old:
        r.run([(sql, []) for sql in old])
    # Requests readers made are copied down, so the assets they name stay tracked; request_job.py analyses them.
    asked = r.rows("SELECT asset, name, requested_at, status, done_at FROM live_sentiment_request WHERE status IN ('pending','running','done')")
    if asked:
        con.executemany("INSERT OR IGNORE INTO live_sentiment_request(asset, name, requested_at, status, done_at) VALUES(?,?,?,?,?)", [tuple(p) for p in asked])
        con.commit()
    return r.rows("SELECT count(*) FROM live_sentiment_latest")[0][0] == 0


def send(con, r, changes, handled, full):
    stmts = []
    if full:
        latest = con.execute("SELECT * FROM live_sentiment_latest").fetchall()
        items = con.execute("SELECT * FROM live_sentiment_item").fetchall()
        daily = con.execute("SELECT * FROM live_sentiment_daily").fetchall()
        stmts += [(f"DELETE FROM {t}", []) for t in ("live_sentiment_latest", "live_sentiment_item", "live_sentiment_daily")]
        stmts += [_insert("live_sentiment_latest", latest[i:i + 60]) for i in range(0, len(latest), 60)]
        stmts += [_insert("live_sentiment_item", items[i:i + 60]) for i in range(0, len(items), 60)]
        stmts += [_insert("live_sentiment_daily", daily[i:i + 200]) for i in range(0, len(daily), 200)]
    else:
        rows = [c[0] for c in changes.values() if c[0]]
        stmts += [_insert("live_sentiment_latest", rows[i:i + 60]) for i in range(0, len(rows), 60)]
        days = [d for c in changes.values() for d in c[3]]
        stmts += [_insert("live_sentiment_daily", days[i:i + 200]) for i in range(0, len(days), 200)]
        for asset, (_, added, removed, _) in changes.items():
            stmts += [("DELETE FROM live_sentiment_item WHERE asset=? AND ref=?", [asset, ref]) for ref in removed]
            stmts += [_insert("live_sentiment_item", added[i:i + 60]) for i in range(0, len(added), 60)]
        # Rows older than the history are dropped in Turso too, one statement a day.
        stmts.append(("DELETE FROM live_sentiment_daily WHERE date<?", [(dt.date.today() - dt.timedelta(days=s_sentiment.HISTORY_D)).isoformat()]))
    for aid in handled:
        status, done_at = con.execute("SELECT status, done_at FROM live_sentiment_request WHERE asset=?", (aid,)).fetchone()
        stmts.append(("UPDATE live_sentiment_request SET status=?, done_at=? WHERE asset=?", [status, done_at, aid]))
    for i in range(0, len(stmts), 8):
        r.run(stmts[i:i + 8])
    return len(stmts)


def main(log_to_file=True, backfill_days=None):
    log = ROOT / "data" / "daily" / "sentiment.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    out = open(log, "a", encoding="utf-8") if log_to_file else None
    if out:
        sys.stdout = sys.stderr = out
    print(f"\n=== {dt.datetime.now(dt.timezone.utc).isoformat()} ===", flush=True)
    try:
        import request_job
        if request_job.ensure_watcher():
            print("request watcher was not running; started it", flush=True)
    except Exception as e:
        print(f"could not start the request watcher: {type(e).__name__}: {e}", flush=True)
    step = "starting"
    try:
        con = init_db()
        s_sentiment._migrate(con)
        step = "connecting to Turso"
        r = target()
        empty = prepare(con, r)
        step = "scoring"
        result = s_sentiment.run(con, backfill_days)
        if result is None:
            checkin.send("sentiment", True, "skipped: the previous run is still going", 15)
            return
        changes, handled = result
        full = empty or RESYNC.exists()
        step = "sending to Turso"
        try:
            n = send(con, r, changes, handled, full)
            RESYNC.unlink(missing_ok=True)
            print(f"sent to Turso: {'everything' if full else f'{len(changes)} changed assets'}, {n} statements", flush=True)
        except Exception:
            RESYNC.write_text("the last send failed; the next run sends everything")
            raise
        checkin.send("sentiment", True, f"{len(changes)} assets changed, {n} statements sent{' (full resend)' if full else ''}", 15)
    except BaseException as e:
        checkin.send("sentiment", False, f"failed while {step}: {type(e).__name__}: {e}", 15)
        raise


def collector(con):
    """The daily collector's entry point (sources.py): the same run, logged to the collector's own log."""
    main(log_to_file=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--backfill-days", type=int, help="fill this many days of history first, up to 31")
    main(backfill_days=p.parse_args().backfill_days)
