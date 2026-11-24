"""Brings the hosted Turso copy in line with a local public edition, sending only what changed.

Usage:
  python -I ingest/sync_turso.py data/hosted-public/public.db --env <.env with TURSO_ORG and TURSO_API_TOKEN>
  python -I ingest/sync_turso.py <db> --url https://<host> --token <database token>     (tests)

It updates the database in place, so its address and the read-only token the scenario AI holds stay valid.
Each table is compared by partitions, coarse to fine (for a series: the whole series, then each year, then each
month), using a row count and a checksum computed on both sides. Inside a partition that differs, the rows are compared
one by one and only those that are new, changed or gone are written, so a row that is already right is never written
again (Turso bills every written row). Tokens are never printed.
"""
import argparse
import base64
import collections
import math
import os
import pathlib
import sqlite3
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

API = "https://api.turso.tech/v1/organizations"
NAME = os.environ.get("TURSO_DATABASE_NAME", "rehyn-markets-public")
# Partition levels per table, coarse to fine. Tables not listed are compared whole.
LEVELS = {
    "ts_obs": ["series_id", "substr(date,1,4)", "substr(date,1,7)"],
    "ts_series": ["dataset_id"],
    "co_fact": ["symbol", "substr(period_end,1,4)"],
    "co_filing": ["symbol", "substr(filed,1,7)"],
    "co_insider_tx": ["symbol", "substr(filed,1,7)"],
    "co_fund_holding": ["period", "manager"],
    "nw_article": ["dataset_id", "substr(published,1,7)", "substr(published,1,10)"],
    "nw_event": ["substr(date,1,4)", "substr(date,1,7)"],
    "geo_gdelt_event": ["substr(added,1,7)", "substr(added,1,10)"],
    "doc_release": ["dataset_id", "substr(date,1,4)", "substr(date,1,7)"],
    "geo_conflict_event": ["substr(date_start,1,4)"],
    "geo_quake": ["substr(time,1,4)"],
    "geo_sanction_list": ["list"],
    "fts_doc": ["dataset", "substr(date,1,4)", "substr(date,1,7)", "substr(date,1,10)"],
    "geo_sanction": ["substr(name,1,1)"],
    "pos_cot": ["market_code", "substr(report_date,1,4)"],
    "ref_sec_ticker": ["substr(ticker,1,1)"],
}
WHOLE_MAX, WHOLE_PARTS = 5000, 4   # a partition of at most this many rows, with this many changed parts, is compared row by row as one
PAGE = 2000   # rows read from Turso at a time
LAST = ("cat_category", "cat_dataset", "cat_source")   # the catalogue goes last, after the data it describes
# ml_ holds the stored sentiment model and live_ the sentiment results. Both live in the news sentiment database, which
# ingest/model_store.py and ingest/sentiment_job.py write; nothing here belongs in the public database.
SKIP_PREFIX = ("sqlite_", "fts_doc_", "ml_", "live_")


def env_file(path):
    out = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, bytes):
        return {"type": "blob", "base64": base64.b64encode(v).decode()}
    return {"type": "text", "value": str(v)}


def val(v):
    t = v.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    return v.get("value")


class Remote:
    def __init__(self, url, token):
        self.url = url.rstrip("/").replace("libsql://", "https://")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"
        self.sent = 0

    def run(self, stmts):
        """Runs statements in order in one request. Returns the rows of each statement."""
        body = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [arg(a) for a in args]}} for sql, args in stmts] + [{"type": "close"}]}
        for attempt in range(5):
            try:
                r = self.s.post(f"{self.url}/v2/pipeline", json=body, timeout=180)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.ConnectionError(str(r.status_code))
                r.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
        out = []
        for res in r.json()["results"][:len(stmts)]:
            if res["type"] != "ok":
                raise RuntimeError(res.get("error", {}).get("message", "statement failed")[:300])
            out.append([[val(c) for c in row] for row in res["response"]["result"]["rows"]])
        return out

    def rows(self, sql, args=()):
        return self.run([(sql, list(args))])[0]


def connect(args):
    if args.url:
        return Remote(args.url, args.token)
    e = env_file(args.env)
    org, api = e.get("TURSO_ORG") or os.environ.get("TURSO_ORG"), e.get("TURSO_API_TOKEN") or os.environ.get("TURSO_API_TOKEN")
    if not org or not api:
        sys.exit("TURSO_ORG and TURSO_API_TOKEN are needed in the .env file")
    auth = {"Authorization": f"Bearer {api}"}
    r = requests.get(f"{API}/{org}/databases/{NAME}", headers=auth, timeout=60)
    if r.status_code >= 300:
        sys.exit(f"could not find database {NAME} ({r.status_code})")
    host = r.json()["database"]["Hostname"]
    r = requests.post(f"{API}/{org}/databases/{NAME}/auth/tokens", params={"expiration": "6h"}, headers=auth, timeout=60)
    if r.status_code >= 300:
        sys.exit(f"could not create a short-lived write token ({r.status_code})")
    return Remote(f"https://{host}", r.json()["jwt"])


def columns(local, table):
    return [r[1] for r in local.execute(f'PRAGMA table_info("{table}")')]


def checksum(cols):
    # A row count plus a whole-number sum over every column: numbers by value, text and blobs by length. It is a sum of
    # integers because a sum of fractions comes out slightly differently in different SQLite versions (the worker's and
    # Turso's), which once made unchanged data look changed on every run.
    parts = [f"""CASE typeof("{c}") WHEN 'integer' THEN "{c}" % 1000000007 WHEN 'null' THEN 0
                 WHEN 'real' THEN CASE WHEN abs("{c}") < 1e9 THEN CAST(round("{c}" * 1e6) AS INTEGER) ELSE CAST(round("{c}") AS INTEGER) END % 1000000007
                 ELSE length("{c}") END""" for c in cols]
    return f"count(*), coalesce(sum({' + '.join(parts)}), 0)"


def where(conds):
    return (" WHERE " + " AND ".join(f"({e}) IS ?" for e, _ in conds), [v for _, v in conds]) if conds else ("", [])


def key_columns(local, table):
    info = local.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]


def remote_rows(remote, table, cols, key, conds):
    """(identity, row) for each row Turso holds under conds. The identity is the table's key, or its rowid."""
    w, a = where(conds)
    names = ",".join(f'"{c}"' for c in cols)
    if not key:
        last = -1 << 62
        while True:
            page = remote.rows(f'SELECT rowid, {names} FROM "{table}"{w + " AND" if w else " WHERE"} rowid > ? ORDER BY rowid LIMIT {PAGE}', [*a, last])
            for r in page:
                yield r[0], tuple(r[1:])
            if len(page) < PAGE:
                return
            last = page[-1][0]
    at = [cols.index(k) for k in key]
    order, skip = ",".join(f'"{k}"' for k in key), 0
    while True:
        page = remote.rows(f'SELECT {names} FROM "{table}"{w} ORDER BY {order} LIMIT {PAGE} OFFSET {skip}', a)
        for r in page:
            yield tuple(r[i] for i in at), tuple(r)
        if len(page) < PAGE:
            return
        skip += PAGE


def same(a, b):
    """Two rows hold the same values. Fractions may differ in their last digit, since Turso keeps 2.0100000000000002 as 2.01."""
    return a == b or all(x == y or (isinstance(x, float) and isinstance(y, (int, float)) and math.isclose(x, y, rel_tol=1e-12)) for x, y in zip(a, b))


def send(remote, local, table, cols, conds, stats, fresh=False):
    """Makes one partition the same on Turso, writing only the rows that differ. fresh: Turso is known to hold none of it."""
    w, a = where(conds)
    names = ",".join(f'"{c}"' for c in cols)
    key = key_columns(local, table)
    mine = [tuple(r) for r in local.execute(f'SELECT {names} FROM "{table}"{w}', a)]
    theirs = [] if fresh else remote_rows(remote, table, cols, key, conds)
    if key:
        at = [cols.index(k) for k in key]
        want = {tuple(r[i] for i in at): r for r in mine}
        gone = []
        for ident, row in theirs:
            if ident not in want:
                gone.append(ident)
            elif want[ident] is not None and same(want[ident], row):
                want[ident] = None   # already right
        add = [r for r in want.values() if r is not None]
    else:
        want, gone = collections.Counter(mine), []
        for ident, row in theirs:
            if want.get(row, 0) > 0:
                want[row] -= 1
            else:
                gone.append(ident)
        add = list(want.elements())
    if not add and not gone:
        return
    stmts = []

    def put(stmt, limit):
        stmts.append(stmt)
        if len(stmts) >= limit:
            remote.run(stmts)
            stmts.clear()

    for i in range(0, len(gone), 200) if not key else ():
        part = gone[i:i + 200]
        put((f'DELETE FROM "{table}" WHERE rowid IN ({",".join("?" * len(part))})', part), 6)
    for g in gone if key else ():
        cond = " AND ".join(f'"{k}" IS NULL' if v is None else f'"{k}" = ?' for k, v in zip(key, g))
        put((f'DELETE FROM "{table}" WHERE {cond}', [v for v in g if v is not None]), 100)
    if stmts:
        remote.run(stmts)
        stmts.clear()
    per = max(1, min(400, 30000 // max(1, len(cols))))
    for i in range(0, len(add), per):
        chunk = add[i:i + per]
        marks = ",".join(["(" + ",".join("?" * len(cols)) + ")"] * len(chunk))
        put((f'INSERT OR REPLACE INTO "{table}"({names}) VALUES {marks}', [v for row in chunk for v in row]), 6)
    if stmts:
        remote.run(stmts)
    stats["rows"] += len(add) + len(gone)
    stats["parts"] += 1


def compare(remote, local, table, cols, levels, conds, stats):
    """Sends every partition under conds that differs, refining one level at a time."""
    sums = checksum(cols)
    if not levels:
        w, a = where(conds)
        here = local.execute(f'SELECT {sums} FROM "{table}"{w}', a).fetchone()
        there = remote.rows(f'SELECT {sums} FROM "{table}"{w}', a)[0]
        if tuple(here) != tuple(there):
            send(remote, local, table, cols, conds, stats)
        return
    expr = levels[0]
    w, a = where(conds)
    here = {r[0]: tuple(r[1:]) for r in local.execute(f'SELECT {expr} p, {sums} FROM "{table}"{w} GROUP BY p', a)}
    there = {r[0]: tuple(r[1:]) for r in remote.rows(f'SELECT {expr} p, {sums} FROM "{table}"{w} GROUP BY p', a)}
    if conds:
        # A source that revises much of its history would otherwise be compared one month at a time. When several parts of
        # a small partition, and at least half of them, changed, its rows are compared in one piece.
        total = sum(v[0] for v in here.values())
        parts = sum(1 for k, v in here.items() if there.get(k) != v)
        if total <= WHOLE_MAX and parts >= WHOLE_PARTS and parts * 2 >= len(here):
            send(remote, local, table, cols, conds, stats)
            return
    for key in sorted(set(here) | set(there), key=lambda k: (k is None, str(k))):
        if here.get(key) == there.get(key):
            continue
        sub = conds + [(expr, key)]
        if key not in here:
            w2, a2 = where(sub)
            remote.run([(f'DELETE FROM "{table}"{w2}', a2)])
            stats["parts"] += 1
        elif key not in there or there[key][0] == 0:
            send(remote, local, table, cols, sub, stats, fresh=True)
        elif len(levels) == 1:
            send(remote, local, table, cols, sub, stats)
        else:
            compare(remote, local, table, cols, levels[1:], sub, stats)


def sync_pass(remote, local, order, rebuild=None):
    """Compares and sends every table once. Returns the number of partitions that changed. Tables in rebuild are dropped,
    made again with their new definition and filled when their turn comes."""
    total = 0
    for _, name, _, _ in order:
        stats = {"rows": 0, "parts": 0}
        cols = columns(local, name)
        levels = LEVELS.get(name, [])
        try:
            for e in levels:
                local.execute(f'SELECT {e} FROM "{name}" LIMIT 1')
        except sqlite3.Error:
            levels = []
        if rebuild and name in rebuild:
            remote.run([(f'DROP TABLE "{name}"', []), (rebuild.pop(name), [])])
            print(f"rebuilt {name}: its definition changed", flush=True)
        compare(remote, local, name, cols, levels, [], stats)
        if stats["parts"]:
            print(f"{name}: {stats['parts']} partitions changed, {stats['rows']:,} rows written", flush=True)
        total += stats["parts"]
    return total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("db")
    p.add_argument("--env")
    p.add_argument("--url")
    p.add_argument("--token")
    args = p.parse_args()
    if args.env:
        # A sync started by hand pauses on the same terms as the daily one.
        import quota
        may, why = quota.check(args.env)
        if not may:
            sys.exit(why)
    local = sqlite3.connect(f"file:{pathlib.Path(args.db).as_posix()}?mode=ro", uri=True)
    remote = connect(args)
    started = time.time()

    there = {r[0]: r[1] for r in remote.rows("SELECT name, sql FROM sqlite_master WHERE type IN ('table','index','view') AND sql IS NOT NULL")}
    objects = local.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    tables = [o for o in objects if o[0] == "table" and not o[1].startswith(SKIP_PREFIX)]
    rebuild = {}
    for kind, name, _, sql in tables:
        if name not in there:
            remote.run([(sql, [])])
            print(f"created {name}", flush=True)
        else:
            mine = columns(local, name)
            cols_there = [r[1] for r in remote.rows(f"SELECT cid, name FROM pragma_table_info('{name}') ORDER BY cid")]
            same_sql = " ".join((there[name] or "").split()) == " ".join((sql or "").split())
            # A changed definition rebuilds the table: always when its columns differ, and for small tables also when only
            # a constraint changed. Large tables keep their rows when the columns still match.
            if "VIRTUAL" not in (sql or "").upper() and (cols_there != mine or (not same_sql and name not in LEVELS)):
                if name in LAST:
                    rebuild[name] = sql   # the catalogue is rebuilt just before it is filled, so readers find it empty for a moment at most
                    continue
                remote.run([(f'DROP TABLE "{name}"', []), (sql, [])])
                print(f"rebuilt {name}: its definition changed", flush=True)

    order = [t for t in tables if t[1] not in LAST] + [t for t in tables if t[1] in LAST]
    # A row whose unique key moved to another partition is replaced on insert, which changes that partition in turn,
    # so the pass repeats until nothing differs.
    for pass_no in range(1, 4):
        changed = sync_pass(remote, local, order, rebuild)
        if not changed:
            break
        print(f"pass {pass_no}: {changed} partitions changed", flush=True)

    for kind, name, table, sql in objects:
        if kind in ("index", "view") and name not in there and not name.startswith(SKIP_PREFIX) and not table.startswith(SKIP_PREFIX):
            remote.run([(sql, [])])
            print(f"created {kind} {name}", flush=True)

    wrong = []
    for _, name, _, _ in tables:
        a = local.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        b = remote.rows(f'SELECT count(*) FROM "{name}"')[0][0]
        if a != b:
            wrong.append(f"{name} {a} vs {b}")
    if wrong:
        sys.exit("row counts differ after the sync: " + "; ".join(wrong))
    print(f"in sync, {len(tables)} tables checked, {time.time() - started:.0f} seconds", flush=True)


if __name__ == "__main__":
    main()
