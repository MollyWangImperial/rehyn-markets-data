"""News sentiment for each tracked asset (see news_assets.py), scored by a DeBERTa-v3 financial sentiment model.

Each run:
  1. catches up on GDELT's raw 15 minute files (s_gdelt_raw.py): headlines that name a tracked asset, and events
     turned into sentences by rule. A normal run fills gaps up to three days back; a backfill goes up to 31 days;
  2. runs a live GDELT search for assets readers asked for that were not tracked yet;
  3. scores every new headline and event sentence once with the model, loaded from the copy stored in Turso;
  4. recomputes each asset with new items, and every asset once an hour, from the last 30 days of items:
       - the score over the last 24 hours, 7 days and 30 days: the weighted mean of positive minus negative
         probability, from -1 to +1, with each item counted once and widely reported events up to three times;
       - one point per UTC day for the 30 day chart, and the current day so far;
       - the change: the 24 hour score less the 30 day score;
       - the news volume: items in the last 24 hours over the 30 day daily average.
     Site assets also read Wikipedia's dated events, Federal Reserve releases and Federal Register documents;
  5. keeps 31 days of headlines and events, hourly readings for 30 days and then one per day, and daily points.

Prices and positioning are not inputs: the model reads text only.

  python -I ingest/sentiment_job.py                     a run, sent to Turso (every 15 minutes, and in the daily collector)
  python -I ingest/sentiment_job.py --backfill-days 30  fill the history first
"""
import datetime as dt
import json
import math
import os
import re
import time

import core
import news_assets
import s_gdelt_raw
from core import ROOT, Run, fetch
from s_news import clean
from textutil import norm, tidy

MODEL = "DeBERTa-v3 small, financial news sentiment (mrm8488)"
HISTORY_D = 30
KEEP_DAYS = 31
ITEMS_KEPT = 60
MAX_EVENTS = 25        # the most reported event records per asset per day, so events support the headlines rather than outnumber them
SEARCH_H = 72          # the live search for a requested asset
DOC_SETS = ("events_wiki", "docs_fed", "docs_federal_register")
HOSTED = "licence_fee='None' AND coalesce(licence_route,'')='' AND tier IN ('OPEN','TERMS')"
LOCK = ROOT / "data" / "sentiment.lock"

# GDELT's DOC search asks for one request every 5 seconds per address, and throttles bursts.
core.HOST_GAP["api.gdeltproject.org"] = 10.0


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _when(text):
    if not text:
        return None
    t = text.strip().replace(" ", "T")
    if len(t) == 10:
        t += "T12:00:00"
    try:
        d = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


class Scorer:
    """The DeBERTa-v3 model, loaded from the copy stored in Turso on first use. Scores are kept in nw_sentiment."""

    def __init__(self, con):
        self.con, self.model = con, None

    def _load(self):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        import model_store
        path = model_store.ensure_local()
        # In a container os.cpu_count() is the host's cores, not the service's share, so the worker sets the count.
        torch.set_num_threads(int(os.environ.get("REHYN_TORCH_THREADS") or 0) or max(1, (os.cpu_count() or 2) - 1))
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForSequenceClassification.from_pretrained(path).eval()
        labels = {i: str(n).lower() for i, n in self.model.config.id2label.items()}
        self.idx = [next(i for i, n in labels.items() if n.startswith(k)) for k in ("neg", "neu", "pos")]

    def score(self, pairs):
        """pairs: (ref, text). Scores the refs not scored before and saves them. Returns {ref: (neg, neu, pos)}."""
        out, todo = {}, []
        for ref, text in pairs:
            row = self.con.execute("SELECT p_neg, p_neu, p_pos FROM nw_sentiment WHERE ref=?", (ref,)).fetchone()
            if row:
                out[ref] = tuple(row)
            elif text:
                todo.append((ref, text))
        if todo and self.model is None:
            self._load()
        now = _iso(dt.datetime.now(dt.timezone.utc))
        for i in range(0, len(todo), 32):
            batch = todo[i:i + 32]
            enc = self.tok([t for _, t in batch], truncation=True, max_length=256, padding=True, return_tensors="pt")
            with self.torch.no_grad():
                probs = self.torch.softmax(self.model(**enc).logits, dim=-1).tolist()
            rows = []
            for (ref, _), p in zip(batch, probs):
                trio = tuple(round(p[j], 4) for j in self.idx)
                out[ref] = trio
                rows.append((ref, *trio, ("negative", "neutral", "positive")[max(range(3), key=trio.__getitem__)], MODEL, now))
            self.con.executemany("INSERT OR REPLACE INTO nw_sentiment VALUES(?,?,?,?,?,?,?)", rows)
            self.con.commit()
            if len(todo) > 2000 and (i // 32) % 100 == 0:
                print(f"  scored {i + len(batch):,} of {len(todo):,}", flush=True)
        return out


def score_new(con, scorer, now):
    """Scores every stored headline and event sentence the model has not read yet."""
    cutoff = _iso(now - dt.timedelta(days=KEEP_DAYS))
    heads = con.execute("""SELECT DISTINCT a.url, a.title FROM nw_asset_link l JOIN nw_article a ON a.url=l.url
                           LEFT JOIN nw_sentiment s ON s.ref=a.url WHERE s.ref IS NULL AND a.published>=?""", (cutoff,)).fetchall()
    evs = con.execute("""SELECT 'gdelt-event:'||e.event_id, e.sentence FROM geo_gdelt_event e
                         LEFT JOIN nw_sentiment s ON s.ref='gdelt-event:'||e.event_id WHERE s.ref IS NULL AND e.added>=?""", (cutoff,)).fetchall()
    scorer.score(heads + evs)
    return len(heads) + len(evs)


def documents(con, asset, ok, now):
    """Wikipedia's dated events, Federal Reserve releases and Federal Register documents that name a site asset."""
    doc_since = (now - dt.timedelta(days=HISTORY_D)).date().isoformat()
    out = []
    if "events_wiki" in ok:
        for eid, date, text in con.execute("SELECT id, date, text FROM nw_event WHERE date>=? ORDER BY date DESC", (doc_since,)):
            if asset.matches(text or ""):
                out.append(dict(ref=f"wiki-event:{eid}", published=date, origin="document", source="Wikipedia", text=text[:900], weight=1.0))
    for ds in ("docs_fed", "docs_federal_register"):
        if ds not in ok:
            continue
        for url, date, inst, kind, title, abstract, body in con.execute(
                "SELECT url, date, institution, kind, title, abstract, body FROM doc_release WHERE dataset_id=? AND date>=? ORDER BY date DESC", (ds, doc_since)):
            text = " ".join(x for x in (title, abstract) if x)
            policy = asset.fed and ds == "docs_fed" and (kind or "").lower().startswith("monetary")
            if policy and body:
                text = clean(body, 900)   # a policy statement opens with the decision and the assessment
            if policy or asset.matches(text):
                out.append(dict(ref=url, published=date, origin="document", source=inst, text=text[:900], weight=1.0))
    return out


def live_search(con, asset, attempts=6):
    """The last three days of English news from the GDELT DOC API for one asset, saved and linked like the raw files."""
    params = {"query": f"{asset.query} sourcelang:english", "mode": "artlist", "format": "json", "maxrecords": 250, "sort": "datedesc", "timespan": f"{SEARCH_H}h"}
    # GDELT refuses many search requests at random even when they are well spaced, so a refusal waits longer each time.
    for attempt in range(attempts):
        try:
            r = fetch("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=30, retries=1)
            break
        except RuntimeError as e:
            if "429" not in str(e) or attempt == attempts - 1:
                raise
            time.sleep(min(15 * (attempt + 1), 8 if attempts <= 2 else 90))
    body = json.loads(r.text) if r.text.strip().startswith("{") else {}
    rows, links = [], []
    for a in body.get("articles") or []:
        seen, title, url = a.get("seendate") or "", tidy(clean(a.get("title"), 300)), a.get("url")
        if not url or not title or not asset.matches(title):
            continue
        when = f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}T{seen[9:11]}:{seen[11:13]}:{seen[13:15]}Z" if len(seen) >= 15 else None
        rows.append((url, when, a.get("domain"), "gdelt", title, None, a.get("sourcecountry"), a.get("language"), "asset"))
        links.append((url, asset.id))
    con.executemany("""INSERT INTO nw_article(dataset_id, url, published, source, feed, title, summary, country, lang, theme)
                       VALUES('news_gdelt',?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO NOTHING""", rows)
    con.executemany("INSERT OR IGNORE INTO nw_asset_link(url, asset) VALUES(?,?)", links)
    con.commit()
    return len(rows)


def gather(con, asset, scorer, ok, now):
    """Every scored item of the last 30 days behind an asset, newest first, one per distinct text."""
    cutoff = _iso(now - dt.timedelta(days=HISTORY_D))
    items = []
    for url, published, source, feed, title, pn, pu, pp in con.execute(
            """SELECT a.url, a.published, a.source, a.feed, a.title, s.p_neg, s.p_neu, s.p_pos FROM nw_asset_link l
               JOIN nw_article a ON a.url=l.url JOIN nw_sentiment s ON s.ref=a.url WHERE l.asset=? AND a.published>=?""", (asset.id, cutoff)):
        items.append(dict(ref=url, published=published, origin="web" if feed == "gdelt" else "news", source=source, text=title, weight=1.0, p=(pn, pu, pp)))
    for eid, added, url, sentence, mentions, seen, pn, pu, pp in con.execute(
            """SELECT event_id, added, url, sentence, mentions, mentions_seen, p_neg, p_neu, p_pos FROM (
                 SELECT e.*, s.p_neg, s.p_neu, s.p_pos,
                        row_number() OVER (PARTITION BY substr(e.added,1,10) ORDER BY e.mentions+e.mentions_seen DESC) AS rank
                 FROM geo_gdelt_event e JOIN nw_sentiment s ON s.ref='gdelt-event:'||e.event_id WHERE e.assets LIKE ? AND e.added>=?)
               WHERE rank<=?""", (f"%,{asset.id},%", cutoff, MAX_EVENTS)):
        weight = 1 + min(2.0, math.log1p((mentions or 0) + (seen or 0)) / 2)
        items.append(dict(ref=f"{url}#gdelt-event-{eid}" if url else f"gdelt-event:{eid}", published=added, origin="event", source="GDELT event record",
                          text=sentence, weight=round(weight, 3), p=(pn, pu, pp)))
    if asset.id in news_assets.SITE_IDS:
        docs = documents(con, asset, ok, now)
        scores = scorer.score([(d["ref"], d["text"]) for d in docs])
        for d in docs:
            d["p"] = scores.get(d["ref"])
        items += [d for d in docs if d["p"]]
    seen, out = set(), []
    for x in sorted(items, key=lambda x: x["published"] or "", reverse=True):
        key = norm(x["text"])
        if key and key not in seen:
            seen.add(key)
            out.append(x)
    return out


def _mean(items):
    """Weighted mean of positive minus negative probability, and the number of items."""
    den = sum(x["weight"] for x in items)
    return (round(sum(x["weight"] * (x["p"][2] - x["p"][0]) for x in items) / den, 4) if den else None), len(items)


def reading(items, now, days):
    """The 24 hour, 7 day and 30 day scores, the change and the news volume, the current day, and one point per
    completed UTC day. `days` is how many days of history there are, so a short history is not read as a quiet one."""
    for x in items:
        x["age"] = max(0.0, (now - (_when(x["published"]) or now)).total_seconds() / 3600)
        x["day"] = (_when(x["published"]) or now).date().isoformat()
    s1, n1 = _mean([x for x in items if x["age"] < 24])
    s7, n7 = _mean([x for x in items if x["age"] < 168])
    s30, n30 = _mean(items)
    today = now.date().isoformat()
    t, tn = _mean([x for x in items if x["day"] == today])
    by_day = {}
    for x in items:
        if x["day"] < today:
            by_day.setdefault(x["day"], []).append(x)
    daily = {d: _mean(xs) for d, xs in by_day.items()}
    week = [x for x in items if x["age"] < 168]
    label = lambda x: max(range(3), key=x["p"].__getitem__)  # noqa: E731
    count = lambda f: sum(1 for x in week if f(x))  # noqa: E731
    avg = n30 / max(1, min(days, HISTORY_D))
    return dict(days=min(days, HISTORY_D), s1=s1, n1=n1, s7=s7, n7=n7, s30=s30, n30=n30,
                change=round(s1 - s30, 4) if s1 is not None and s30 is not None and days >= 7 else None,
                heat=round(n1 / avg, 2) if avg and days >= 7 else None, today=t, today_n=tn,
                n_pos=count(lambda x: label(x) == 2), n_neu=count(lambda x: label(x) == 1), n_neg=count(lambda x: label(x) == 0),
                n_news=count(lambda x: x["origin"] == "news"), n_events=count(lambda x: x["origin"] == "event"),
                n_docs=count(lambda x: x["origin"] == "document"), n_web=count(lambda x: x["origin"] == "web"), daily=daily)


def _key(row, start):
    return tuple(round(v, 3) if isinstance(v, float) else v for v in row[start:])


def aggregate(con, assets, scorer, ok, now, days):
    """Recomputes each asset. Returns the changes to send: {asset: (latest row or None, items added, item refs removed,
    daily rows)}. A row whose figures, to three decimals, are unchanged is not sent again."""
    hour = now.strftime("%Y-%m-%dT%H:00:00Z")
    changes = {}
    for asset in assets:
        items = gather(con, asset, scorer, ok, now)
        r = reading(items, now, days)
        latest = (asset.id, hour, r["days"], r["s1"], r["n1"], r["s7"], r["n7"], r["s30"], r["n30"], r["change"], r["heat"], r["today"], r["today_n"],
                  r["n_pos"], r["n_neu"], r["n_neg"], r["n_news"], r["n_events"], r["n_docs"], r["n_web"], MODEL)
        old = con.execute("SELECT * FROM live_sentiment_latest WHERE asset=?", (asset.id,)).fetchone()
        con.execute("INSERT OR REPLACE INTO live_sentiment VALUES(?,?,?,?,?,?,?,?)", (asset.id, hour, r["s1"], r["n1"], r["s7"], r["n7"], r["s30"], r["n30"]))
        con.execute(f"INSERT OR REPLACE INTO live_sentiment_latest VALUES({','.join('?' * len(latest))})", latest)
        daily = []
        for d, (s, n) in sorted(r["daily"].items()):
            row = (asset.id, d, s, n)
            have = con.execute("SELECT * FROM live_sentiment_daily WHERE asset=? AND date=?", (asset.id, d)).fetchone()
            if not have or _key(have, 2) != _key(row, 2):
                daily.append(row)
        con.executemany("INSERT OR REPLACE INTO live_sentiment_daily VALUES(?,?,?,?)", daily)
        keep = [(asset.id, x["ref"], x["published"], x["origin"], x["source"], x["text"], *x["p"],
                 ("negative", "neutral", "positive")[max(range(3), key=x["p"].__getitem__)], x["weight"]) for x in items[:ITEMS_KEPT]]
        have = {row[1]: tuple(row) for row in con.execute("SELECT * FROM live_sentiment_item WHERE asset=?", (asset.id,))}
        want = {row[1] for row in keep}
        added = [row for row in keep if have.get(row[1]) != tuple(row)]   # new, or the same item with new text or scores
        removed = sorted(set(have) - want)
        con.executemany("DELETE FROM live_sentiment_item WHERE asset=? AND ref=?", [(asset.id, ref) for ref in removed])
        con.executemany("INSERT OR REPLACE INTO live_sentiment_item VALUES(?,?,?,?,?,?,?,?,?,?,?)", added)
        con.commit()
        # Sent when the figures move, and once an hour regardless, so the reading time the site shows stays current.
        moved = not old or _key(old, 2) != _key(latest, 2) or old[1] != latest[1]
        if moved or added or removed or daily:
            changes[asset.id] = (latest if moved else None, added, removed, daily)
    return changes


def prune(con, now):
    """Keeps 31 days of headlines and events; hourly readings for 30 days, then one per asset per day; daily points for 30 days."""
    cut = _iso(now - dt.timedelta(days=KEEP_DAYS))
    old = "SELECT url FROM nw_article WHERE dataset_id='news_gdelt' AND theme='asset' AND published<?"
    con.execute(f"DELETE FROM nw_asset_link WHERE url IN ({old})", (cut,))
    con.execute(f"DELETE FROM nw_sentiment WHERE ref IN ({old})", (cut,))
    con.execute(f"DELETE FROM nw_gdelt_tone WHERE url IN ({old})", (cut,))
    con.execute("DELETE FROM nw_article WHERE dataset_id='news_gdelt' AND theme='asset' AND published<?", (cut,))
    con.execute("DELETE FROM nw_sentiment WHERE ref IN (SELECT 'gdelt-event:'||event_id FROM geo_gdelt_event WHERE added<?)", (cut,))
    con.execute("DELETE FROM geo_gdelt_event WHERE added<?", (cut,))
    con.execute("""DELETE FROM live_sentiment WHERE as_of<? AND (asset, as_of) NOT IN
                   (SELECT asset, max(as_of) FROM live_sentiment WHERE as_of<? GROUP BY asset, substr(as_of,1,10))""", (cut, cut))
    con.execute("DELETE FROM live_sentiment_daily WHERE date<?", ((now - dt.timedelta(days=HISTORY_D)).date().isoformat(),))
    con.commit()


def history_days(con, now):
    """Whole days of GDELT batches processed, up to 30, from the record of processed batches."""
    first = con.execute("SELECT min(stamp) FROM cat_gdelt_raw_done").fetchone()[0]
    if not first:
        return 0
    start = dt.datetime.strptime(first, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    return min(HISTORY_D, int((now - start).total_seconds() // 86400))


def _fts(text):
    """A full text query for a name: the words as one phrase."""
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    return '"' + " ".join(words) + '"' if words else None


def analyse_request(con, asset, report, scorer=None):
    """Adds an asset a reader asked for: finds its headlines of the last 30 days in the title index, links and scores
    them, and computes its reading. report(percent, stage) is called as the work moves on. A scorer passed in keeps the
    model loaded between requests. Returns the changes to send."""
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    report(10, "Searching 30 days of news")
    tcon = s_gdelt_raw.titles()
    cutoff = _iso(now - dt.timedelta(days=HISTORY_D))
    queries = [q for q in {_fts(asset.search), _fts(asset.name)} if q]
    tick = asset.id.split("/")[0].split(".")[0]
    if re.fullmatch(r"[A-Z]{3,6}", tick):
        queries.append(f'"{tick}"')
    found = {}
    for q in queries:
        for title, url, published, source in tcon.execute("SELECT title, url, published, source FROM headline WHERE headline MATCH ? AND published>=?", (q, cutoff)):
            if url not in found and asset.matches(title):
                found[url] = (url, published, source, "gdelt_gkg", title, None, None, "en", "asset")
    tcon.close()
    rows = list(found.values())
    con.executemany("""INSERT INTO nw_article(dataset_id, url, published, source, feed, title, summary, country, lang, theme)
                       VALUES('news_gdelt',?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO NOTHING""", rows)
    con.executemany("INSERT OR IGNORE INTO nw_asset_link(url, asset) VALUES(?,?)", [(r[0], asset.id) for r in rows])
    con.commit()
    # The title index holds every English headline GDELT has listed in the last 31 days, updated every 15 minutes, so
    # GDELT's own search would find nothing more; it is not called, and a reader never waits on its throttling.
    todo = con.execute("""SELECT a.url, a.title FROM nw_asset_link l JOIN nw_article a ON a.url=l.url LEFT JOIN nw_sentiment s ON s.ref=a.url
                          WHERE l.asset=? AND a.published>=? AND s.ref IS NULL""", (asset.id, cutoff)).fetchall()
    total = con.execute("SELECT count(*) FROM nw_asset_link l JOIN nw_article a ON a.url=l.url WHERE l.asset=? AND a.published>=?", (asset.id, cutoff)).fetchone()[0]
    report(30, f"Found {total:,} headlines; scoring them")
    scorer = scorer or Scorer(con)
    for i in range(0, len(todo), 256):
        scorer.score(todo[i:i + 256])
        report(30 + int(55 * min(1, (i + 256) / max(1, len(todo)))), f"Scoring {min(i + 256, len(todo)):,} of {len(todo):,} headlines")
    report(90, "Computing the 24 hour, 7 day and 30 day readings")
    ok = {r[0] for r in con.execute(f"SELECT id FROM cat_dataset WHERE {HOSTED} AND id IN ({','.join('?' * len(DOC_SETS))})", DOC_SETS)}
    return aggregate(con, [asset], scorer, ok, now, history_days(con, now))


def _alive(pid):
    """Whether a process is running. On Windows os.kill(pid, 0) would send Ctrl+C, so the process is queried instead."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259   # STILL_ACTIVE


def _locked():
    """True while another run holds the lock. A lock left by a run that died is cleared, so a long backfill is never
    run twice and a crash never blocks later runs."""
    if not LOCK.exists():
        return False
    try:
        if _alive(int(LOCK.read_text().strip())):
            return True
    except ValueError:
        pass
    LOCK.unlink(missing_ok=True)
    return False


def _migrate(con):
    """Rebuilds the live_ tables from an earlier layout. Their contents are recomputed by the run."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(live_sentiment_latest)")]
    if cols and "s30" not in cols:
        con.execute("DROP TABLE IF EXISTS live_sentiment_latest")
        con.execute("DROP TABLE IF EXISTS live_sentiment")
        con.execute("DELETE FROM live_sentiment_item")
        con.commit()
        core.init_db()
    have = {r[1] for r in con.execute("PRAGMA table_info(live_sentiment_request)")}
    for name, kind in (("progress", "INTEGER"), ("stage", "TEXT")):
        if have and name not in have:
            con.execute(f"ALTER TABLE live_sentiment_request ADD COLUMN {name} {kind}")
    con.commit()


def run(con, backfill_days=None):
    """One pass. Returns (changes to send, request ids handled), or None when another pass is already running."""
    if _locked():
        print("another sentiment run is in progress; skipped", flush=True)
        return None
    LOCK.write_text(str(os.getpid()))
    try:
        with Run(con, "news_sentiment") as run_:
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            _migrate(con)
            con.execute("DROP TABLE IF EXISTS x_sentiment")
            con.execute("DROP TABLE IF EXISTS x_sentiment_item")
            ok = {r[0] for r in con.execute(f"SELECT id FROM cat_dataset WHERE {HOSTED} AND id IN ({','.join('?' * len(DOC_SETS))})", DOC_SETS)}
            assets = news_assets.build(con)
            by_id = {a.id: a for a in assets}
            hours = 24 * min(KEEP_DAYS, backfill_days) if backfill_days else s_gdelt_raw.CATCH_UP_H
            touched = s_gdelt_raw.catch_up(con, assets, run_, hours)

            handled = []   # requests are analysed by request_job.py as soon as they arrive

            scorer = Scorer(con)
            run_.note(f"{score_new(con, scorer, now)} new items scored")
            # Assets with new items every run; every asset with anything in the last 30 days once an hour, as windows move.
            last_hour = con.execute("SELECT max(as_of) FROM live_sentiment").fetchone()[0]
            if last_hour != now.strftime("%Y-%m-%dT%H:00:00Z") or backfill_days:
                cutoff = _iso(now - dt.timedelta(days=HISTORY_D))
                touched |= {r[0] for r in con.execute("SELECT DISTINCT l.asset FROM nw_asset_link l JOIN nw_article a ON a.url=l.url WHERE a.published>=?", (cutoff,))}
                touched |= {r[0] for r in con.execute("SELECT asset FROM live_sentiment_latest WHERE n30>0")}
                touched |= news_assets.SITE_IDS
            days = history_days(con, now)
            changes = aggregate(con, [by_id[a] for a in sorted(touched) if a in by_id], scorer, ok, now, days)
            prune(con, now)
            run_.rows = len(changes)
            run_.note(f"{len(touched)} assets recomputed, {len(changes)} changed, {days} days of history")
            return changes, handled
    finally:
        LOCK.unlink(missing_ok=True)
