"""Tells the AI service's watchdog how a job went, so the team is alerted when a run fails or a job goes quiet.

  checkin.send("sentiment", ok, "what ran, or the failing step and its error", every_minutes=15)

The token is JOBS_TOKEN, from the environment (the cloud worker) or data/collector.env (a PC). Without one nothing is
sent. A check-in never fails the job: it waits at most 10 seconds and ignores any error, so a sleeping or unreachable
AI service changes nothing.
"""
import os
import re

import requests

from core import ROOT

URL = "https://rehyn-markets-ai.onrender.com/api/ai/jobs/heartbeat"
# Anything that looks like a token or key is blanked before a detail leaves the machine.
SECRET = re.compile(r"eyJ[\w-]{10,}\.[\w-]+\.[\w-]+|\b(?:sk|phc|ghp|re)_[\w-]{16,}|(?i:(?:token|key|secret|password)=)\S+")


def _settings():
    out = {}
    path = ROOT / "data" / "collector.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def send(job, ok, detail, every_minutes):
    try:
        cfg = _settings()
        token = os.environ.get("JOBS_TOKEN") or cfg.get("JOBS_TOKEN")
        if not token:
            return False
        url = os.environ.get("JOBS_URL") or cfg.get("JOBS_URL") or URL
        text = SECRET.sub("[hidden]", " ".join(str(detail).split()))[:1000]
        r = requests.post(url, json={"job": job, "ok": bool(ok), "detail": text, "every_minutes": every_minutes},
                          headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.ok
    except Exception:  # noqa: BLE001 - a check-in must never stop the job
        return False
