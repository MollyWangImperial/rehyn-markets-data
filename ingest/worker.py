"""Runs the pipeline on the cloud worker (Render), in place of the three Windows scheduled tasks:

  the request watcher (request_job.py --watch)   all the time, restarted if it stops
  the news sentiment run (sentiment_job.py)      every 15 minutes, skipped while the last one is still going
  the daily collector (daily.py)                 at 06:30 London time

  python -I ingest/worker.py

Settings come from the service's environment and are written to data/collector.env and data/turso.env on the disk at
start, so the scripts read them as they do on a PC: REHYN_SEC_CONTACT, SENTIMENT_DB_URL, SENTIMENT_DB_TOKEN, TURSO_ORG
and TURSO_API_TOKEN. Lock files left by the last container are cleared first, since their process ids mean nothing in a
new one. The scripts' own logs are copied to this process's output, so they show in Render's log stream. Nothing runs
until data/ready exists, which the copy of the PC's data onto the disk creates last.
"""
import datetime as dt
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
LOGS = DATA / "daily"
EVERY = int(os.environ.get("REHYN_SENTIMENT_EVERY", "900"))
DAILY_AT = dt.time.fromisoformat(os.environ.get("REHYN_DAILY_AT", "06:30"))
ZONE = ZoneInfo(os.environ.get("REHYN_DAILY_ZONE", "Europe/London"))
SETTINGS = ("REHYN_SEC_CONTACT", "SENTIMENT_DB_URL", "SENTIMENT_DB_TOKEN")
ENV = dict(os.environ, REHYN_SUPERVISED="1", PYTHONIOENCODING="utf-8")

stopping = threading.Event()
children = {}


def say(msg):
    print(f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} worker: {msg}", flush=True)


def read_env(path):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def write_env(path, values):
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    path.chmod(0o600)


def settings():
    """Writes the service's settings over data/collector.env, keeping any other keys a copied file already has."""
    cfg = read_env(DATA / "collector.env")
    cfg.update({k: os.environ[k] for k in SETTINGS if os.environ.get(k)})
    if os.environ.get("TURSO_ORG") and os.environ.get("TURSO_API_TOKEN"):
        write_env(DATA / "turso.env", {k: os.environ[k] for k in ("TURSO_ORG", "TURSO_API_TOKEN")})
        cfg["TURSO_ENV"] = str(DATA / "turso.env")
    elif cfg.get("TURSO_ENV") and not pathlib.Path(cfg["TURSO_ENV"]).exists():
        cfg.pop("TURSO_ENV")   # a path from a PC copy
    write_env(DATA / "collector.env", cfg)
    missing = [k for k in SETTINGS if not cfg.get(k)] + ([] if cfg.get("TURSO_ENV") else ["TURSO_ORG/TURSO_API_TOKEN"])
    if missing:
        say(f"not set: {', '.join(missing)}")


def follow():
    """Copies new lines of the scripts' log files to this process's output."""
    seen = {}
    while not stopping.is_set():
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        for path in (LOGS / "sentiment.log", LOGS / "requests.log", LOGS / f"{today}.log"):
            if not path.exists():
                continue
            size = path.stat().st_size
            if path not in seen:
                seen[path] = size   # history stays in the file; only what follows is copied
                continue
            if size < seen[path]:
                seen[path] = 0
            if size > seen[path]:
                with open(path, "rb") as f:
                    f.seek(seen[path])
                    chunk = f.read(size - seen[path])
                seen[path] = size
                for line in chunk.decode("utf-8", "replace").splitlines():
                    if line.strip():
                        print(f"[{path.stem}] {line}", flush=True)
        stopping.wait(2)


def start(name, script, *args):
    children[name] = subprocess.Popen([sys.executable, "-I", str(HERE / script), *args], cwd=ROOT, env=ENV)
    say(f"started {name} (pid {children[name].pid})")


def busy(name):
    p = children.get(name)
    if p is None:
        return False
    if p.poll() is None:
        return True
    say(f"{name} finished with exit {p.returncode}")
    del children[name]
    return False


def next_daily(now):
    local = now.astimezone(ZONE)
    at = dt.datetime.combine(local.date(), DAILY_AT, ZONE)
    return at if at > local else dt.datetime.combine(local.date() + dt.timedelta(days=1), DAILY_AT, ZONE)


def stop(*_):
    stopping.set()


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    for name in ("sentiment.lock", "request_watch.lock"):
        (DATA / name).unlink(missing_ok=True)
    settings()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=follow, daemon=True).start()
    # Until the copy of the database, headline index and model is fully on the disk, nothing runs: a run on an empty
    # database would send blank readings over the live ones. The copy ends by creating data/ready.
    if not (DATA / "ready").exists():
        say("waiting for the data copy: data/ready appears once rehyn_markets.db, gdelt_titles.db and models/ are copied")
        while not stopping.is_set() and not (DATA / "ready").exists():
            stopping.wait(10)
    last_sentiment, watcher_back = 0.0, 0.0
    daily_at = next_daily(dt.datetime.now(dt.timezone.utc))
    say(f"sentiment every {EVERY // 60} minutes; next daily run {daily_at.isoformat()}")
    while not stopping.is_set():
        now = time.time()
        if not busy("watcher") and now >= watcher_back:
            start("watcher", "request_job.py", "--watch")
            watcher_back = now + 30   # a watcher that keeps failing is retried every 30 seconds, not in a tight loop
        if now - last_sentiment >= EVERY and not busy("sentiment"):
            start("sentiment", "sentiment_job.py")
            last_sentiment = now
        if dt.datetime.now(dt.timezone.utc) >= daily_at:
            if not busy("daily"):
                start("daily", "daily.py")
            daily_at = next_daily(dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1))
        stopping.wait(5)
    say("stopping")
    for p in children.values():
        if p.poll() is None:
            p.terminate()
    for p in children.values():
        try:
            p.wait(20)
        except subprocess.TimeoutExpired:
            p.kill()


if __name__ == "__main__":
    main()
