"""Analyses assets readers ask for on the site, as soon as they ask.

  python -I ingest/request_job.py --watch   keep running and check Turso every 3 seconds, with the model kept loaded
  python -I ingest/request_job.py           one check, then exit (for a scheduled task)

For each request it adds the asset to the tracked set, searches the last 30 days of GDELT headlines in the local title
index, scores them, computes the 24 hour, 7 day and 30 day readings and the daily series, and sends them to Turso. Its
progress is written to the request row, so the site can show a progress bar; the 15 minute runs keep the asset up to
date from then on. Only one watcher runs at a time; a second one exits.
"""
import argparse
import datetime as dt
import os
import pathlib
import subprocess
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core import ROOT, init_db  # noqa: E402
import news_assets  # noqa: E402
import s_sentiment  # noqa: E402
import sentiment_job  # noqa: E402

COLUMNS = (("progress", "INTEGER"), ("stage", "TEXT"))
LOCK = ROOT / "data" / "request_watch.lock"
INTERVAL = 3


def ensure_columns(r):
    """Adds the progress columns to Turso's request table if it predates them. Runs a write only when one is missing."""
    have = {row[1] for row in r.rows("SELECT cid, name FROM pragma_table_info('live_sentiment_request')")}
    for name, kind in COLUMNS:
        if have and name not in have:
            r.run([(f"ALTER TABLE live_sentiment_request ADD COLUMN {name} {kind}", [])])


def pending(r):
    return r.rows("SELECT asset, name, requested_at FROM live_sentiment_request WHERE status='pending' ORDER BY requested_at LIMIT 5")


def send_asset(con, r, aid):
    """Replaces everything Turso holds for one asset with the local rows: its reading, items and daily points. A request
    always sends in full, so a retry after a failed attempt cannot leave the reading missing."""
    stmts = [(f"DELETE FROM {t} WHERE asset=?", [aid]) for t in ("live_sentiment_latest", "live_sentiment_item", "live_sentiment_daily")]
    for table, size in (("live_sentiment_latest", 1), ("live_sentiment_item", 60), ("live_sentiment_daily", 200)):
        rows = con.execute(f"SELECT * FROM {table} WHERE asset=?", (aid,)).fetchall()
        stmts += [sentiment_job._insert(table, rows[i:i + size]) for i in range(0, len(rows), size)]
    for i in range(0, len(stmts), 8):
        r.run(stmts[i:i + 8])


def handle(r, con, scorer, aid, name, at):
    """Analyses one request and sends the result, writing its progress to Turso as it goes."""
    print(f"\n=== {dt.datetime.now(dt.timezone.utc).isoformat()} {aid} ({name}) ===", flush=True)
    last = {"p": -1, "t": 0.0}

    def report(p, stage):
        # At most one write every couple of seconds, and only when the figure moves.
        if p >= 96 or (p - last["p"] >= 5 and time.time() - last["t"] >= 2):
            r.run([("UPDATE live_sentiment_request SET status='running', progress=?, stage=? WHERE asset=?", [p, stage, aid])])
            last.update(p=p, t=time.time())
        print(f"  {p}% {stage}", flush=True)

    con.execute("INSERT OR REPLACE INTO live_sentiment_request(asset, name, requested_at, status) VALUES(?,?,?,'running')", (aid, name, at))
    con.commit()
    try:
        report(5, "Adding the asset to the tracked set")
        tracked = {a.id: a for a in news_assets.build(con)}
        asset = tracked.get(aid) or news_assets.requested(aid, name)
        if not hasattr(asset, "search"):
            asset.search = name or aid
        s_sentiment.analyse_request(con, asset, report, scorer)
        report(96, "Saving the analysis")
        send_asset(con, r, aid)
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        con.execute("UPDATE live_sentiment_request SET status='done', done_at=? WHERE asset=?", (now, aid))
        con.commit()
        r.run([("UPDATE live_sentiment_request SET status='done', done_at=?, progress=100, stage='Done' WHERE asset=?", [now, aid])])
        print("  done", flush=True)
    except Exception as e:
        con.execute("UPDATE live_sentiment_request SET status='failed' WHERE asset=?", (aid,))
        con.commit()
        r.run([("UPDATE live_sentiment_request SET status='failed', stage=? WHERE asset=?", [f"The analysis could not be completed ({type(e).__name__}).", aid])])
        print(f"  failed: {type(e).__name__}: {e}", flush=True)


def once():
    r = sentiment_job.target()
    ensure_columns(r)
    waiting = pending(r)
    if not waiting:
        return
    with open(ROOT / "data" / "daily" / "requests.log", "a", encoding="utf-8") as out:
        sys.stdout = sys.stderr = out
        con = init_db()
        s_sentiment._migrate(con)
        scorer = s_sentiment.Scorer(con)
        for aid, name, at in waiting:
            handle(r, con, scorer, aid, name, at)


def running():
    """Whether a watcher is running, from its lock file."""
    try:
        return LOCK.exists() and s_sentiment._alive(int(LOCK.read_text().strip()))
    except ValueError:
        return False


def ensure_watcher():
    """Starts a watcher, detached from whatever called this, when none is running. The 15 minute job calls it, so a
    watcher that stopped is back within 15 minutes. On the cloud worker, worker.py starts and restarts it instead."""
    if os.environ.get("REHYN_SUPERVISED") == "1" or running():
        return False
    flags = 0x00000008 | 0x00000200 | 0x08000000 if os.name == "nt" else 0   # detached, own process group, no window
    args = dict(cwd=str(ROOT), close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = [sys.executable, "-I", str(HERE / "request_job.py"), "--watch"]
    try:
        # Also outside the caller's job object, so closing a terminal or a scheduled task does not end it.
        subprocess.Popen(cmd, creationflags=flags | (0x01000000 if os.name == "nt" else 0), **args)
    except OSError:
        subprocess.Popen(cmd, creationflags=flags, **args)
    return True


def watch():
    """Checks Turso every few seconds and handles requests as they arrive, with the model loaded once."""
    if running():
        return
    LOCK.write_text(str(os.getpid()))
    out = open(ROOT / "data" / "daily" / "requests.log", "a", encoding="utf-8")
    sys.stdout = sys.stderr = out
    print(f"\n=== watcher started {dt.datetime.now(dt.timezone.utc).isoformat()}, checking every {INTERVAL} s ===", flush=True)
    try:
        r = sentiment_job.target()
        ensure_columns(r)
        con = init_db()
        s_sentiment._migrate(con)
        scorer = s_sentiment.Scorer(con)
        scorer._load()   # loaded once, so a request starts scoring at once
        print("model loaded; watching", flush=True)
        while True:
            try:
                for aid, name, at in pending(r):
                    handle(r, con, scorer, aid, name, at)
            except Exception as e:
                # A network or Turso error waits a little longer, then the watcher carries on.
                print(f"{dt.datetime.now(dt.timezone.utc).isoformat()} check failed: {type(e).__name__}: {e}", flush=True)
                time.sleep(30)
            time.sleep(INTERVAL)
    except BaseException:
        print(f"{dt.datetime.now(dt.timezone.utc).isoformat()} watcher stopped:\n{traceback.format_exc()}", flush=True)
        raise
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--watch", action="store_true", help="keep running and check every 3 seconds")
    watch() if p.parse_args().watch else once()
