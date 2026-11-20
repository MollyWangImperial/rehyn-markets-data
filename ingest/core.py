"""Shared database and network helpers for every ingest step."""
import datetime as dt
import functools
import os
import pathlib
import sqlite3
import threading
import time
from urllib.parse import urlparse

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = pathlib.Path(os.environ.get("REHYN_DB", ROOT / "data" / "rehyn_markets.db"))
SCHEMA = ROOT / "schema" / "schema.sql"

# Identify the crawler honestly. FRED and SEC both accept this and refuse disguised browsers.
BOT_UA = os.environ.get("REHYN_USER_AGENT", "RehynMarketsResearch/0.1 (data catalogue prototype)")

# Seconds between requests per host. Each value stays inside the host's published limit.
HOST_GAP = {
    "api.gdeltproject.org": 6.0,
    "data.sec.gov": 0.15,
    "www.sec.gov": 0.15,
    "query1.finance.yahoo.com": 0.3,
    "en.wikipedia.org": 0.2,
    "wikimedia.org": 0.04,
    "api.worldbank.org": 0.1,
    "api.exchange.coinbase.com": 0.2,
    "fred.stlouisfed.org": 0.5,
    "www.federalreserve.gov": 0.3,
}
DEFAULT_GAP = 0.25

_last = {}
_lock = threading.Lock()
_session = requests.Session()


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=OFF")
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.commit()
    return con


def _wait(host):
    gap = HOST_GAP.get(host, DEFAULT_GAP)
    with _lock:
        ready = _last.get(host, 0) + gap
        now = time.monotonic()
        _last[host] = max(now, ready)
    if ready > now:
        time.sleep(ready - now)


def fetch(url, *, params=None, headers=None, timeout=60, retries=4, ok_404=False):
    """GET with a per-host gap, an honest user agent and backoff on 429 and 5xx."""
    host = urlparse(url).hostname
    h = {"User-Agent": BOT_UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        _wait(host)
        try:
            r = _session.get(url, params=params, headers=h, timeout=timeout)
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code == 404 and ok_404:
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            retry_after = r.headers.get("Retry-After", "")
            delay = int(retry_after) if retry_after.isdigit() else 6 * (attempt + 1)
            last = RuntimeError(f"{r.status_code} from {host}")
            time.sleep(min(delay, 60))
            continue
        raise RuntimeError(f"{r.status_code} from {url}")
    raise RuntimeError(f"gave up on {url}: {last}")


def restricted(reason):
    """Holds a step whose source terms bar this use. Only the project owner should set REHYN_ALLOW_RESTRICTED."""

    def wrap(fn):
        @functools.wraps(fn)
        def inner(con, *a, **k):
            if os.environ.get("REHYN_ALLOW_RESTRICTED") == "1":
                return fn(con, *a, **k)
            print(f"[{fn.__name__}] held: {reason}", flush=True)
            con.execute(
                "INSERT INTO cat_run(step, started_at, finished_at, status, rows_written, message) VALUES(?,?,?,'held',0,?)",
                (fn.__name__, now_iso(), now_iso(), reason),
            )
            con.commit()

        return inner

    return wrap


class Run:
    """Records one ingest step in cat_run, so failures stay visible in the database."""

    def __init__(self, con, step):
        self.con = con
        self.step = step
        self.rows = 0
        self.notes = []

    def __enter__(self):
        cur = self.con.execute(
            "INSERT INTO cat_run(step, started_at, status) VALUES(?, ?, 'running')", (self.step, now_iso())
        )
        self.run_id = cur.lastrowid
        self.con.commit()
        print(f"[{self.step}] start", flush=True)
        return self

    def note(self, msg):
        self.notes.append(msg)
        print(f"[{self.step}] {msg}", flush=True)

    def __exit__(self, kind, exc, tb):
        status = "ok" if kind is None else "failed"
        if exc is not None:
            self.notes.append(f"{kind.__name__}: {exc}")
        self.con.rollback()
        self.con.execute(
            "UPDATE cat_run SET finished_at=?, status=?, rows_written=?, message=? WHERE run_id=?",
            (now_iso(), status, self.rows, "; ".join(self.notes)[-1500:], self.run_id),
        )
        self.con.commit()
        print(f"[{self.step}] {status}, {self.rows:,} rows", flush=True)
        return False


def upsert_series(con, series_id, dataset_id, title, units, frequency, rows, country=None, topic=None):
    """rows is an iterable of (date, value). Empty and non-numeric values are dropped."""
    clean = []
    for d, v in rows:
        if d is None or v is None or v == "":
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:
            continue
        clean.append((series_id, str(d)[:10], f))
    if not clean:
        return 0
    con.execute(
        """INSERT INTO ts_series(series_id, dataset_id, title, units, frequency, country, topic)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(series_id) DO UPDATE SET dataset_id=excluded.dataset_id, title=excluded.title,
             units=excluded.units, frequency=excluded.frequency, country=excluded.country, topic=excluded.topic""",
        (series_id, dataset_id, title, units, frequency, country, topic),
    )
    con.executemany("INSERT OR REPLACE INTO ts_obs(series_id, date, value) VALUES(?,?,?)", clean)
    con.execute(
        """UPDATE ts_series SET first_date=(SELECT min(date) FROM ts_obs WHERE series_id=?1),
             last_date=(SELECT max(date) FROM ts_obs WHERE series_id=?1),
             rows=(SELECT count(*) FROM ts_obs WHERE series_id=?1) WHERE series_id=?1""",
        (series_id,),
    )
    return len(clean)
