"""Geopolitics: UCDP conflict events, OFAC sanctions, live prediction market odds."""
import csv
import io
import json
import zipfile

from core import Run, fetch, now_iso, restricted

KINDS = {"1": "State based", "2": "Non-state", "3": "One-sided"}


def ucdp(con, min_deaths=5):
    with Run(con, "ucdp") as run_:
        r = fetch("https://ucdp.uu.se/downloads/ged/ged251-csv.zip", timeout=180)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        with z.open(z.namelist()[0]) as f:
            rows = []
            for x in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace")):
                try:
                    deaths = int(x.get("best") or 0)
                except ValueError:
                    deaths = 0
                if deaths < min_deaths:
                    continue
                rows.append((int(x["id"]), (x.get("date_start") or "")[:10], (x.get("date_end") or "")[:10], x.get("country"), x.get("region"),
                             x.get("conflict_name"), x.get("side_a"), x.get("side_b"), KINDS.get(x.get("type_of_violence"), x.get("type_of_violence")),
                             deaths, x.get("latitude"), x.get("longitude")))
        con.executemany("INSERT OR REPLACE INTO geo_conflict_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        run_.rows = len(rows)
        run_.note(f"events with at least {min_deaths} deaths")


def ofac(con):
    with Run(con, "ofac") as run_:
        r = fetch("https://www.treasury.gov/ofac/downloads/sdn.csv", timeout=120)
        rows = []
        for p in csv.reader(io.StringIO(r.content.decode("latin-1"))):
            if len(p) < 12 or not p[0].strip().isdigit():
                continue
            null = lambda v: None if v.strip() in ("-0-", "") else v.strip()
            rows.append((int(p[0]), null(p[1]), null(p[2]), null(p[3]), null(p[11])))
        con.executemany("INSERT OR REPLACE INTO geo_sanction VALUES(?,?,?,?,?)", rows)
        con.commit()
        run_.rows = len(rows)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@restricted("Polymarket's terms bar data access by financial technology companies without a written agreement")
def polymarket(con, pages=6):
    with Run(con, "polymarket") as run_:
        stamp = now_iso()
        for page in range(pages):
            r = fetch("https://gamma-api.polymarket.com/events", params={
                "limit": 100, "offset": page * 100, "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false"})
            events = r.json()
            if not events:
                break
            rows = []
            for e in events:
                tags = [t.get("label") for t in e.get("tags") or [] if isinstance(t, dict)]
                for m in e.get("markets") or []:
                    if m.get("closed") or not m.get("active", True):
                        continue
                    prices = m.get("outcomePrices")
                    prices = json.loads(prices) if isinstance(prices, str) else prices or []
                    if not prices:
                        continue
                    rows.append(("Polymarket", str(m.get("id")), m.get("question"), e.get("title"), ", ".join(x for x in tags[:3] if x),
                                 _f(prices[0]), _f(m.get("volume")), (m.get("endDate") or "")[:10] or None,
                                 f"https://polymarket.com/event/{e.get('slug')}", stamp))
            con.executemany("INSERT OR REPLACE INTO geo_prediction VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)


@restricted("Kalshi's developer agreement limits API use to a member's own trading")
def kalshi(con, pages=10):
    with Run(con, "kalshi") as run_:
        stamp = now_iso()
        cursor = None
        for _ in range(pages):
            params = {"limit": 200, "status": "open", "with_nested_markets": "true"}
            if cursor:
                params["cursor"] = cursor
            r = fetch("https://api.elections.kalshi.com/trade-api/v2/events", params=params)
            body = r.json()
            rows = []
            for e in body.get("events") or []:
                for m in e.get("markets") or []:
                    bid, ask = _f(m.get("yes_bid_dollars") or m.get("yes_bid")), _f(m.get("yes_ask_dollars") or m.get("yes_ask"))
                    if bid is None or ask is None:
                        continue
                    if bid > 1 or ask > 1:
                        bid, ask = bid / 100, ask / 100
                    rows.append(("Kalshi", m.get("ticker"), m.get("title") or e.get("title"), e.get("title"), e.get("category"), (bid + ask) / 2,
                                 _f(m.get("volume") or m.get("volume_fp")), (m.get("close_time") or "")[:10] or None,
                                 f"https://kalshi.com/markets/{(e.get('series_ticker') or '').lower()}", stamp))
            con.executemany("INSERT OR REPLACE INTO geo_prediction VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)
            cursor = body.get("cursor")
            if not cursor:
                break


def run(con):
    for step in (ucdp, ofac, polymarket, kalshi):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
