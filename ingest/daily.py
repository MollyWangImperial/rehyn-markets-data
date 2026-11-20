"""The daily collector. Works through ingest/sources.py, fetches every active source that is due, then rebuilds the
derived tables, the catalogue and the public edition, and brings the hosted Turso copy up to date.

  python -I ingest/daily.py                 everything that is due
  python -I ingest/daily.py --only eia ofac  just these sources, due or not
  python -I ingest/daily.py --no-sync        skip the Turso step

Settings come from data/collector.env (git-ignored), one KEY=value per line:
  REHYN_SEC_CONTACT   contact address the SEC requires in the crawler's user agent. Sent to sec.gov only.
  TURSO_ENV           path to the .env holding TURSO_ORG and TURSO_API_TOKEN for the sync
  JOBS_TOKEN          token for the AI service's job check-ins (checkin.py); the environment is read first

Each source runs in its own process with a time limit, so one failure cannot stop the rest. GDELT's headline archive
runs last with a 20 minute limit. The run ends with a check-in naming any source, step or sync that failed.
A summary of every run is appended to data/daily/<date>.log and recorded in cat_run as step 'daily'.
"""
import argparse
import datetime as dt
import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core import ROOT, Run, init_db  # noqa: E402
from sources import AFTER, CADENCE_DAYS, SOURCES  # noqa: E402

import checkin  # noqa: E402

LIMIT = {"gdelt": 3 * 3600, "sec_facts": 3 * 3600, "sec_filings": 2 * 3600, "wiki_events": 2 * 3600, "news_sentiment": 3 * 3600}
DEFAULT_LIMIT = 3600
# The GDELT headline archive is rate limited (429) and can run for hours, so it runs last with a short limit: the
# rebuild, the public edition and the copy to Turso never wait on it. What it fetches is in the next day's rebuild.
LAST = {"gdelt": 20 * 60}
MIN_FREE_GB = 5


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


def run_source(s, cfg, log, limit=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("REHYN_USER_AGENT", None)
    if s.get("sec"):
        contact = cfg.get("REHYN_SEC_CONTACT")
        if not contact:
            return "skipped: no SEC contact in data/collector.env"
        env["REHYN_USER_AGENT"] = f"RehynMarketsResearch/0.1 {contact}"
    try:
        p = subprocess.run([sys.executable, "-I", str(HERE / "run_one.py"), s["module"], s["fn"]], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=limit or LIMIT.get(s["id"], DEFAULT_LIMIT))
        return "ok" if p.returncode == 0 else f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        return "stopped at its time limit, it resumes next run"


def step(cmd, log, limit):
    """Runs one rebuild step. Returns 'ok' or why it failed, with the last line of its error output."""
    try:
        p = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.PIPE, timeout=limit, text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "stopped at its time limit"
    log.write(p.stderr or "")
    log.flush()
    if p.returncode == 0:
        return "ok"
    last = next((x.strip() for x in reversed((p.stderr or "").splitlines()) if x.strip()), "")
    return f"exit {p.returncode}" + (f": {last[:200]}" if last else "")


def collect(args, cfg, log, run_, con, now):
    """The whole run. Returns the problems found, for the check-in."""
    problems = []

    def note(what, result):
        run_.note(f"{what}: {result}")
        log.flush()
        if result != "ok":
            problems.append(f"{what} ({result})")

    picked = [s for s in SOURCES if s["status"] == "active" and s["module"] and (s["id"] in args.only if args.only else due(con, s, now))]
    for s in [s for s in picked if s["id"] not in LAST]:
        log.write(f"--- {s['id']}\n")
        log.flush()
        note(s["id"], run_source(s, cfg, log))
    for mod, fn in AFTER:
        log.write(f"--- {mod}.{fn}\n")
        log.flush()
        note(f"{mod}.{fn}", step([sys.executable, "-I", str(HERE / "run_one.py"), mod, fn], log, 2 * 3600))
    out = ROOT / "data" / "hosted-public"
    public = step([sys.executable, "-I", str(HERE / "public_edition.py"), str(out)], log, 3600)
    note("public edition", public)
    if public == "ok" and not args.no_sync:
        turso = cfg.get("TURSO_ENV")
        if turso and pathlib.Path(turso).exists():
            note("turso sync", step([sys.executable, "-I", str(HERE / "sync_turso.py"), str(out / "public.db"), "--env", turso], log, 3 * 3600))
        else:
            note("turso sync", "skipped, TURSO_ENV is not set")
    for s in [s for s in picked if s["id"] in LAST]:
        log.write(f"--- {s['id']} (last, {LAST[s['id']] // 60} minute limit)\n")
        log.flush()
        note(s["id"], run_source(s, cfg, log, LAST[s["id"]]))
    free = shutil.disk_usage(ROOT / "data").free / 1e9
    if free < MIN_FREE_GB:
        problems.append(f"only {free:.1f} GB of disk free")
    return picked, problems, free


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*")
    p.add_argument("--no-sync", action="store_true")
    args = p.parse_args()
    cfg = settings()
    folder = ROOT / "data" / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    try:
        con = init_db()
        with open(folder / f"{now.date().isoformat()}.log", "a", encoding="utf-8") as log, Run(con, "daily") as run_:
            log.write(f"\n=== daily run {now.isoformat()} ===\n")
            log.flush()
            picked, problems, free = collect(args, cfg, log, run_, con, now)
            log.write("\n".join(run_.notes) + "\n")
    except BaseException as e:
        checkin.send("daily", False, f"the run stopped: {type(e).__name__}: {e}", 1440)
        raise
    summary = f"{len(picked)} sources, {free:.0f} GB free"
    checkin.send("daily", not problems, f"failed: {'; '.join(problems)}. {summary}" if problems else f"all ok: {summary}", 1440)


if __name__ == "__main__":
    main()
