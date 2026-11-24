"""Keeps the news sentiment model in news sentiment's own Turso database, so the scoring job never depends on a third-party hub.

  python -I ingest/model_store.py upload    one time: download the files from Hugging Face and store them in Turso
  python -I ingest/model_store.py fetch     copy the files from Turso to data/models/, checking each file's SHA-256
  python -I ingest/model_store.py status    what Turso holds

The model is mrm8488/deberta-v3-ft-financial-news-sentiment-analysis: microsoft/deberta-v3-small fine-tuned on the
Financial PhraseBank, MIT licence. Files are stored in 2 MB parts in ml_model_part, listed in ml_model with size, hash,
source and revision. These tables live only in Turso; sync_turso.py skips the ml_ prefix, so the daily sync never
touches them. SENTIMENT_DB_URL and SENTIMENT_DB_TOKEN in data/collector.env say where; without them the Rehyn database
is used, with the same short-lived token as the sync. Tokens are never printed.
"""
import argparse
import base64
import hashlib
import pathlib
import sys
import time
import types

import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core import ROOT  # noqa: E402
import sync_turso  # noqa: E402

REPO = "mrm8488/deberta-v3-ft-financial-news-sentiment-analysis"
NAME = "deberta-v3-fin-sentiment"
FILES = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json", "spm.model", "README.md")
LICENCE = "MIT"
PART = 2 * 1024 * 1024
LOCAL = ROOT / "data" / "models" / NAME

TABLES = [
    """CREATE TABLE IF NOT EXISTS ml_model(model TEXT NOT NULL, file TEXT NOT NULL, bytes INTEGER, sha256 TEXT, parts INTEGER,
       source TEXT, revision TEXT, licence TEXT, saved_at TEXT, PRIMARY KEY(model, file))""",
    "CREATE TABLE IF NOT EXISTS ml_model_part(model TEXT NOT NULL, file TEXT NOT NULL, part INTEGER NOT NULL, data BLOB NOT NULL, PRIMARY KEY(model, file, part))",
]


def remote():
    cfg = {}
    path = ROOT / "data" / "collector.env"
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    if cfg.get("SENTIMENT_DB_URL") and cfg.get("SENTIMENT_DB_TOKEN"):
        return sync_turso.Remote(cfg["SENTIMENT_DB_URL"], cfg["SENTIMENT_DB_TOKEN"])
    if not cfg.get("TURSO_ENV"):
        sys.exit("TURSO_ENV is not set in data/collector.env")
    return sync_turso.connect(types.SimpleNamespace(url=None, token=None, env=cfg["TURSO_ENV"]))


def blob(cell):
    """A blob cell from Turso's HTTP API."""
    if cell.get("type") == "blob":
        s = cell.get("base64") or ""
        return base64.b64decode(s + "=" * (-len(s) % 4))   # Turso leaves out the padding
    raise ValueError(f"expected a blob, got {cell.get('type')}")


def raw(r, sql, args=()):
    """Rows as Turso returns them, so blobs keep their base64 form."""
    body = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [sync_turso.arg(a) for a in args]}}, {"type": "close"}]}
    for attempt in range(5):
        try:
            resp = r.s.post(f"{r.url}/v2/pipeline", json=body, timeout=180)
            resp.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(3 * (attempt + 1))
    res = resp.json()["results"][0]
    if res["type"] != "ok":
        raise RuntimeError(res.get("error", {}).get("message", "statement failed")[:300])
    return res["response"]["result"]["rows"]


def upload():
    r = remote()
    r.run([(t, []) for t in TABLES])
    info = requests.get(f"https://huggingface.co/api/models/{REPO}", timeout=60).json()
    revision = info.get("sha")
    have = {row[0]: row[1] for row in r.rows("SELECT file, sha256 FROM ml_model WHERE model=?", [NAME])}
    for name in FILES:
        url = f"https://huggingface.co/{REPO}/resolve/{revision}/{name}"
        data = requests.get(url, timeout=600).content
        digest = hashlib.sha256(data).hexdigest()
        if have.get(name) == digest:
            print(f"{name}: already stored", flush=True)
            continue
        parts = max(1, -(-len(data) // PART))
        r.run([("DELETE FROM ml_model_part WHERE model=? AND file=?", [NAME, name]), ("DELETE FROM ml_model WHERE model=? AND file=?", [NAME, name])])
        for i in range(parts):
            r.run([("INSERT INTO ml_model_part VALUES (?,?,?,?)", [NAME, name, i, data[i * PART:(i + 1) * PART]])])
            if parts > 10 and i % 25 == 0:
                print(f"{name}: part {i + 1} of {parts}", flush=True)
        # The file is listed only once every part is stored, so a broken upload is never read as complete.
        r.run([("INSERT INTO ml_model VALUES (?,?,?,?,?,?,?,?,datetime('now'))", [NAME, name, len(data), digest, parts, f"https://huggingface.co/{REPO}", revision, LICENCE])])
        print(f"{name}: {len(data):,} bytes in {parts} parts", flush=True)
    status(r)


def fetch(target=LOCAL):
    """Copies the model from Turso into target, skipping files whose hash already matches. Returns the folder."""
    r = remote()
    listed = r.rows("SELECT file, bytes, sha256, parts FROM ml_model WHERE model=?", [NAME])
    if {row[0] for row in listed} != set(FILES):
        sys.exit("Turso does not hold every model file. Run: python -I ingest/model_store.py upload")
    target.mkdir(parents=True, exist_ok=True)
    for name, size, digest, parts in listed:
        path = target / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        chunks = []
        for i in range(parts):
            rows = raw(r, "SELECT data FROM ml_model_part WHERE model=? AND file=? AND part=?", [NAME, name, i])
            chunks.append(blob(rows[0][0]))
        data = b"".join(chunks)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            sys.exit(f"{name}: the copy from Turso does not match its recorded hash")
        path.write_bytes(data)
        print(f"{name}: {size:,} bytes from Turso, hash checked", flush=True)
    return target


def ensure_local():
    """The local model folder, filled from Turso when a file is missing."""
    if not all((LOCAL / f).exists() for f in FILES):
        fetch()
    return LOCAL


def status(r=None):
    r = r or remote()
    rows = r.rows("SELECT file, bytes, parts, substr(sha256,1,12), revision, saved_at FROM ml_model WHERE model=? ORDER BY bytes DESC", [NAME])
    total = sum(x[1] for x in rows)
    print(f"{NAME} in Turso: {len(rows)} files, {total / 1e6:.1f} MB")
    for f, b, p, h, rev, at in rows:
        print(f"  {f}: {b:,} bytes, {p} parts, sha256 {h}..., revision {str(rev)[:10]}, saved {at}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["upload", "fetch", "status"])
    a = p.parse_args()
    {"upload": upload, "fetch": fetch, "status": status}[a.action]()
