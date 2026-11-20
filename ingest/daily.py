"""The daily collector. Works through ingest/sources.py, fetches every active source that is due, then rebuilds the
derived tables, the catalogue and the public edition, and brings the hosted Turso copy up to date.

  python -I ingest/daily.py                 everything that is due
  python -I ingest/daily.py --only eia ofac  just these sources, due or not
  python -I ingest/daily.py --no-sync        skip the Turso step

Settings come from data/collector.env (git-ignored), one KEY=value per line:
  REHYN_SEC_CONTACT   contact address the SEC requires in the crawler's user agent. Sent to sec.gov only.
  TURSO_ENV           path to the .env holding TURSO_ORG and TURSO_API_TOKEN for the sync

Each source runs in its own process with a time limit, so one failure cannot stop the rest.
A summary of every run is appended to data/daily/<date>.log and recorded in cat_run as step 'daily'.
"""
import argparse
import datetime as dt
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core import ROOT, Run, init_db  # noqa: E402
from sources import AFTER, CADENCE_DAYS, SOURCES  # noqa: E402

LIMIT = {"gdelt": 3 * 3600, "sec_facts": 3 * 3600, "sec_filings": 2 * 3600, "wiki_events": 2 * 3600, "news_sentiment": 3 * 3600}
DEFAULT_LIMIT = 3600


def settings():
    out = {}
    path = ROOT / "data" / "collector.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def last_ok(con, run_name):
    r = con.execute("SELECT max(finished_at) FROM cat_run WHERE step=? AND status='ok'", (run_name,)).fetchone()
    return dt.datetime.fromisoformat(r[0].replace("Z", "+00:00")) if r and r[0] else None


def due(con, s, now):
    last = last_ok(con, s["run"])
    return last is None or (now - last).total_seconds() / 86400 >= CADENCE_DAYS[s["cadence"]]


def run_source(s, cfg, log):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("REHYN_USER_AGENT", None)
    if s.get("sec"):
        contact = cfg.get("REHYN_SEC_CONTACT")
        if not contact:
            return "skipped: no SEC contact in data/collector.env"
        env["REHYN_USER_AGENT"] = f"RehynMarketsResearch/0.1 {contact}"
    try:
        p = subprocess.run([sys.executable, "-I", str(HERE / "run_one.py"), s["module"], s["fn"]], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT.get(s["id"], DEFAULT_LIMIT))
        return "ok" if p.returncode == 0 else f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        return "stopped at its time limit, it resumes next run"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*")
    p.add_argument("--no-sync", action="store_true")
    args = p.parse_args()
    cfg = settings()
    folder = ROOT / "data" / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    con = init_db()
    with open(folder / f"{now.date().isoformat()}.log", "a", encoding="utf-8") as log, Run(con, "daily") as run_:
        log.write(f"\n=== daily run {now.isoformat()} ===\n")
        log.flush()
        picked = [s for s in SOURCES if s["status"] == "active" and s["module"] and (s["id"] in args.only if args.only else due(con, s, now))]
        for s in picked:
            log.write(f"--- {s['id']}\n")
            log.flush()
            result = run_source(s, cfg, log)
            run_.note(f"{s['id']}: {result}")
            log.flush()
        for mod, fn in AFTER:
            log.write(f"--- {mod}.{fn}\n")
            log.flush()
            p2 = subprocess.run([sys.executable, "-I", str(HERE / "run_one.py"), mod, fn], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=2 * 3600)
            run_.note(f"{mod}.{fn}: {'ok' if p2.returncode == 0 else 'exit ' + str(p2.returncode)}")
        out = ROOT / "data" / "hosted-public"
        p3 = subprocess.run([sys.executable, "-I", str(HERE / "public_edition.py"), str(out)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
        run_.note(f"public edition: {'ok' if p3.returncode == 0 else 'exit ' + str(p3.returncode)}")
        if p3.returncode == 0 and not args.no_sync:
            turso = cfg.get("TURSO_ENV")
            if turso and pathlib.Path(turso).exists():
                p4 = subprocess.run([sys.executable, "-I", str(HERE / "sync_turso.py"), str(out / "public.db"), "--env", turso], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=3 * 3600)
                run_.note(f"turso sync: {'ok' if p4.returncode == 0 else 'exit ' + str(p4.returncode)}")
            else:
                run_.note("turso sync: skipped, TURSO_ENV is not set")
        log.write("\n".join(run_.notes) + "\n")


if __name__ == "__main__":
    main()
