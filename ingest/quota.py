"""Turso's monthly write allowance. The sync pauses before it runs out, instead of being blocked half way, and starts again
by itself with the first daily run after the allowance renews.

  python -I ingest/quota.py --env data/turso.env            prints the state
  python -I ingest/quota.py --env data/turso.env --report   and reports it to Rehyn Alerts as the job turso-sync

A sync may start only when at least RESERVE rows are left (about the largest daily sync seen, 2.0M on 24 November 2026),
or when overages are on. TURSO_SYNC_RESERVE changes it. Nothing is written to Turso here, and no token is printed.
"""
import argparse
import datetime as dt
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

import requests

API = "https://api.turso.tech/v1/organizations"
RESERVE = int(os.environ.get("TURSO_SYNC_RESERVE", "2000000"))
DAILY_AT = dt.time.fromisoformat(os.environ.get("REHYN_DAILY_AT", "06:30"))
ZONE = ZoneInfo(os.environ.get("REHYN_DAILY_ZONE", "Europe/London"))
JOB = "turso-sync"


def env_file(path):
    out = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def read(env):
    """Rows written this period, the plan's limit, whether overages are on, and when the allowance renews."""
    e = env_file(env)
    org = e.get("TURSO_ORG") or os.environ.get("TURSO_ORG")
    auth = {"Authorization": f"Bearer {e.get('TURSO_API_TOKEN') or os.environ.get('TURSO_API_TOKEN')}"}

    def get(path):
        r = requests.get(f"{API}/{org}/{path}", headers=auth, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"{r.status_code} from Turso's {path} endpoint")
        return r.json()

    sub = get("subscription")["subscription"]
    plan = next(p for p in get("plans")["plans"] if p["name"] == sub["plan"])
    usage = get("usage")
    used = (usage.get("usage") or usage["organization"]["usage"])["rows_written"]
    return {"plan": sub["plan"], "overages": bool(sub.get("overages")), "used": int(used), "limit": int(plan["quotas"]["rowsWritten"]),
            "renews": dt.datetime.fromisoformat(sub["current_billing_period_end"].replace("Z", "+00:00"))}


def next_sync(after):
    """The first daily run at or after a moment."""
    local = after.astimezone(ZONE)
    at = dt.datetime.combine(local.date(), DAILY_AT, ZONE)
    return at if at >= local else dt.datetime.combine(local.date() + dt.timedelta(days=1), DAILY_AT, ZONE)


def _day(t):
    return f"{t.day} {t:%B %Y}"


def decide(q, need=RESERVE):
    """(may the sync run, a sentence that says why). Pure, so it can be tested without Turso."""
    left = q["limit"] - q["used"]
    share = f"{q['used'] / 1e6:.1f}M of {q['limit'] / 1e6:.0f}M rows written this month"
    if q["overages"]:
        return True, f"{share}, overages are on"
    if left >= need:
        return True, f"{share}, {left / 1e6:.1f}M left"
    back = next_sync(q["renews"])
    return False, (f"Turso sync is paused: {share}, {max(left, 0) / 1e6:.1f}M left and a sync can need {need / 1e6:.1f}M. It restarts by itself on {_day(back)} at {back:%H:%M} London time, "
                   f"after the allowance renews on {_day(q['renews'])} at {q['renews'].astimezone(dt.timezone.utc):%H:%M} UTC. Until then the site shows the data of the last sync; collection goes on.")


def check(env, need=RESERVE):
    """(may the sync run, why). When the usage cannot be read the sync is held for this run, since a block would be worse."""
    try:
        q = read(env)
    except Exception as e:  # noqa: BLE001
        return False, f"Turso sync was held for this run: its usage could not be read ({type(e).__name__}: {e}). The next daily run tries again."
    return decide(q, need)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env", required=True)
    p.add_argument("--report", action="store_true")
    a = p.parse_args()
    ok, why = check(a.env)
    print(("may sync: " if ok else "") + why)
    if a.report:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import checkin
        print("reported to Rehyn Alerts" if checkin.send(JOB, ok, why, 1440) else "not reported: no JOBS_TOKEN, or the AI service did not answer")


if __name__ == "__main__":
    main()
