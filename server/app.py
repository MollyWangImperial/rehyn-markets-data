"""Rehyn Markets data library: read-only API plus the search page."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import engine  # noqa: E402

app = FastAPI(title="Rehyn Markets data library")


class Question(BaseModel):
    q: str


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


@app.get("/")
def page():
    return FileResponse(ROOT / "web" / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/prototype.css")
def css():
    return FileResponse(ROOT / "web" / "prototype.css", media_type="text/css", headers={"Cache-Control": "no-store"})


@app.get("/library.css")
def library_css():
    return FileResponse(ROOT / "web" / "library.css", media_type="text/css", headers={"Cache-Control": "no-store"})


@app.get("/library.js")
def library_js():
    return FileResponse(ROOT / "web" / "library.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})


@app.post("/api/ask")
def ask(body: Question):
    q = body.q.strip()[:600]
    if not q:
        raise HTTPException(400, "Empty question")
    return engine.ask(q)


@app.get("/api/overview")
def overview():
    con = engine.connect()
    try:
        cats = rows(con, "SELECT * FROM cat_category ORDER BY sort")
        data = rows(con, "SELECT * FROM cat_dataset ORDER BY name")
        for c in cats:
            c["datasets"] = [d for d in data if d["category_id"] == c["id"]]
            c["rows"] = sum(d["rows"] or 0 for d in c["datasets"])
        tiers = {t: sum(d["rows"] or 0 for d in data if d["tier"] == t) for t in ("OPEN", "TERMS", "PERMISSION", "FEE")}
        size = sum(p.stat().st_size for p in engine.DB_PATH.parent.glob(engine.DB_PATH.name + "*"))
        tape_syms = ["SPX", "UKX", "NKY", "BRENT", "XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "US10Y", "VIX"]
        marks = ",".join("?" * len(tape_syms))
        tape = rows(con, f"""SELECT a.symbol, a.name, a.asset_class, a.currency, m.close, m.r1d, m.as_of FROM x_asset_metric m JOIN ref_asset a USING(asset_id) WHERE a.symbol IN ({marks})""", tape_syms)
        tape.sort(key=lambda r: tape_syms.index(r["symbol"]))
        for t in tape:
            t["text"] = engine.money(t["close"], t["currency"], t["asset_class"])
            spark = rows(con, "SELECT close FROM px_daily WHERE asset_id=(SELECT asset_id FROM ref_asset WHERE symbol=?) ORDER BY date DESC LIMIT 30", (t["symbol"],))
            t["spark"] = [s["close"] for s in reversed(spark)]
        quality = rows(con, "SELECT * FROM cat_quality ORDER BY passed, check_name") if con.execute("SELECT 1 FROM sqlite_master WHERE name='cat_quality'").fetchone() else []
        sources = rows(con, "SELECT * FROM cat_source ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'candidate' THEN 1 WHEN 'held' THEN 2 ELSE 3 END, name") if con.execute("SELECT 1 FROM sqlite_master WHERE name='cat_source'").fetchone() else []
        return {"categories": cats, "tiers": tiers, "rows": sum(d["rows"] or 0 for d in data), "bytes": size, "tape": tape, "quality": quality, "sources": sources, "public": engine.PUBLIC,
                "refreshed": max((d["refreshed_at"] or "" for d in data), default=None),
                "assets": con.execute("SELECT count(*) FROM ref_asset WHERE last_price IS NOT NULL").fetchone()[0]}
    finally:
        con.close()


@app.get("/api/dataset/{dataset_id}")
def dataset(dataset_id: str):
    con = engine.connect()
    try:
        found = rows(con, "SELECT d.*, c.name category FROM cat_dataset d JOIN cat_category c ON c.id=d.category_id WHERE d.id=?", (dataset_id,))
        if not found:
            raise HTTPException(404, "Unknown dataset")
        d = found[0]
        d["columns"], d["sample"], d["series"] = [], [], []
        table = d["table_name"]
        if table and re.fullmatch(r"[a-z_]+", table) and con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            d["columns"] = [{"name": c["name"], "type": c["type"]} for c in rows(con, f"PRAGMA table_info({table})")]
            where = f" WHERE {d['row_filter']}" if d["row_filter"] else ""
            if table == "ts_obs":
                d["series"] = rows(con, "SELECT series_id, title, units, frequency, first_date, last_date, rows FROM ts_series WHERE dataset_id=? ORDER BY title LIMIT 400", (dataset_id,))
            elif table == "px_daily":
                d["series"] = rows(con, """SELECT a.symbol series_id, a.name title, a.currency units, 'Daily' frequency, a.first_price first_date, a.last_price last_date,
                                           NULL rows FROM ref_asset a WHERE a.price_dataset=? ORDER BY a.symbol LIMIT 800""", (dataset_id,))
            else:
                order = f" ORDER BY {d['date_col']} DESC" if d["date_col"] else ""
                d["sample"] = rows(con, f"SELECT * FROM {table}{where}{order} LIMIT 8")
                for r in d["sample"]:
                    for k, v in r.items():
                        if isinstance(v, str) and len(v) > 140:
                            r[k] = v[:140] + "…"
        return d
    finally:
        con.close()


@app.get("/api/suggest")
def suggest(q: str):
    q = q.strip()
    if len(q) < 2:
        return []
    con = engine.connect()
    try:
        like = f"%{q}%"
        out = rows(con, """SELECT symbol label, name detail, 'Asset' kind FROM ref_asset WHERE last_price IS NOT NULL AND (symbol LIKE ? OR name LIKE ?)
                           ORDER BY symbol=? DESC, length(symbol) LIMIT 5""", (q + "%", like, q.upper()))
        out += rows(con, "SELECT title label, units detail, 'Series' kind FROM ts_series WHERE title LIKE ? AND dataset_id NOT IN ('attention_wiki','macro_world') LIMIT 3", (like,))
        return out
    finally:
        con.close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3040
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
