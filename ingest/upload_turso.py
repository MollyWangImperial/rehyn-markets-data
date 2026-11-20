"""Uploads a database made by export_hosted.py to a new private Turso database, then checks it.

Usage:
  set TURSO_ORG=<organisation slug>
  set TURSO_API_TOKEN=<platform API token>
  python -I ingest/upload_turso.py rehyn-markets-full
  python -I ingest/upload_turso.py rehyn-markets-public --folder data/hosted-public/upload --env <path to a git-ignored .env>

--folder picks the export to send (default data/hosted). --env saves the address and a read-only token to that file.
Tokens are read from the environment and are never printed. Only --env writes one to disk.
"""
import argparse
import json
import os
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "https://api.turso.tech/v1/organizations"
TRIES = 3


def check(r, step):
    if r.status_code >= 300:
        sys.exit(f"{step} failed with {r.status_code}: {r.text[:300]}")
    return r


def pipeline(host, token, sql):
    body = {"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}
    return requests.post(f"https://{host}/v2/pipeline", json=body, headers={"Authorization": f"Bearer {token}"}, timeout=120)


def count(host, token, table):
    r = check(pipeline(host, token, f'SELECT count(*) FROM "{table}"'), f"count {table}")
    return int(r.json()["results"][0]["response"]["result"]["rows"][0][0]["value"])


def pick_group(org, auth):
    """Uses TURSO_GROUP if it exists, the only group if there is one, or creates the first group."""
    wanted = os.environ.get("TURSO_GROUP")
    r = requests.get(f"{API}/{org}/groups", headers=auth, timeout=60)
    if r.status_code >= 300:
        sys.exit(f"Could not list groups ({r.status_code}). Create a token for the whole organisation, not limited to groups, then try again.")
    names = [g["name"] for g in r.json().get("groups", [])]
    print(f"groups in {org}: {', '.join(names) or 'none'}", flush=True)
    if wanted and wanted in names:
        return wanted
    if len(names) == 1 and not wanted:
        return names[0]
    if names:
        sys.exit(f"Set TURSO_GROUP to one of: {', '.join(names)}")
    keys = list(requests.get("https://api.turso.tech/v1/locations", headers=auth, timeout=60).json().get("locations", {}))
    place = os.environ.get("TURSO_LOCATION") or next((k for k in keys if "eu-west" in k or k == "lhr"), keys[0] if keys else None)
    if not place:
        sys.exit("Turso returned no locations. Create a group in the dashboard, then set TURSO_GROUP.")
    r = requests.post(f"{API}/{org}/groups", json={"name": "default", "location": place}, headers=auth, timeout=120)
    if r.status_code >= 300:
        sys.exit(f"Could not create a group ({r.status_code}): {r.text[:200]}. Create one in the dashboard or use a whole organisation token.")
    print(f"created group default in {place}", flush=True)
    return "default"


class Sending:
    """Reads the file for requests and prints each 10% sent."""

    def __init__(self, f, size):
        self.f, self.size, self.sent, self.mark = f, size, 0, 0

    def __len__(self):
        return self.size

    def read(self, n=-1):
        data = self.f.read(n)
        self.sent += len(data)
        if self.sent * 10 // self.size > self.mark:
            self.mark = self.sent * 10 // self.size
            print(f"sent {self.mark * 10}%", flush=True)
        return data


def upload(host, token, file, size):
    for attempt in range(1, TRIES + 1):
        try:
            with open(file, "rb") as f:
                return check(requests.post(f"https://{host}/v1/upload", data=Sending(f, size), headers={"Authorization": f"Bearer {token}"}, timeout=7200), "upload")
        except requests.ConnectionError as e:
            print(f"connection lost on attempt {attempt} of {TRIES}: {type(e).__name__}", flush=True)
            if attempt < TRIES:
                time.sleep(20 * attempt)
    sys.exit(f"Upload stopped after {TRIES} attempts. The connection kept dropping, or Turso closed it. Check your plan's storage limit and your network, then run this again.")


def save_env(path, url, token):
    keep = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith(("TURSO_DATABASE_URL=", "TURSO_AUTH_TOKEN="))] if path.exists() else []
    path.write_text("\n".join([*keep, f"TURSO_DATABASE_URL={url}", f"TURSO_AUTH_TOKEN={token}"]) + "\n", encoding="utf-8")


def read_token(org, name, host, auth):
    r = check(requests.post(f"{API}/{org}/databases/{name}/auth/tokens", params={"authorization": "read-only"}, headers=auth, timeout=60), "create read-only token")
    token = r.json()["jwt"]
    assert count(host, token, "cat_dataset") > 0, "read-only token sees no data"
    r = pipeline(host, token, "CREATE TABLE write_test(x)")
    if r.status_code < 300 and r.json()["results"][0]["type"] == "ok":
        sys.exit("The read-only token was able to write. It was not saved.")
    return token


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", default="rehyn-markets-full")
    p.add_argument("--folder", type=pathlib.Path, default=ROOT / "data" / "hosted")
    p.add_argument("--env", type=pathlib.Path)
    args = p.parse_args()
    name, file = args.name, args.folder / "rehyn_markets.db"
    org, api_token = os.environ["TURSO_ORG"], os.environ["TURSO_API_TOKEN"]
    manifest = json.loads((args.folder / "manifest.json").read_text(encoding="utf-8"))
    assert file.stat().st_size == manifest["bytes"], "file changed after export"
    auth = {"Authorization": f"Bearer {api_token}"}
    group = pick_group(org, auth)

    r = requests.post(f"{API}/{org}/databases", json={"name": name, "group": group, "seed": {"type": "database_upload"}}, headers=auth, timeout=60)
    if r.status_code == 409:
        print(f"{name} already exists, so this continues the upload", flush=True)
        r = requests.get(f"{API}/{org}/databases/{name}", headers=auth, timeout=60)
    host = check(r, "create database").json()["database"]["Hostname"]
    r = check(requests.post(f"{API}/{org}/databases/{name}/auth/tokens", headers=auth, timeout=60), "create database token")
    token = r.json()["jwt"]

    print(f"uploading {manifest['bytes'] / 1e9:.2f} GB to {host}", flush=True)
    upload(host, token, file, manifest["bytes"])

    bad = {t: (n, count(host, token, t)) for t, n in manifest["tables"].items() if t in ("px_daily", "ts_obs", "co_fact", "cat_dataset", "fts_doc")}
    wrong = {t: v for t, v in bad.items() if v[0] != v[1]}
    if wrong:
        sys.exit(f"row counts differ: {wrong}")
    if args.env:
        save_env(args.env, f"libsql://{host}", read_token(org, name, host, auth))
        print(f"saved the address and a read-only token to {args.env}", flush=True)
    print(f"done: {host}. Row counts match on {', '.join(bad)}.")


if __name__ == "__main__":
    main()
