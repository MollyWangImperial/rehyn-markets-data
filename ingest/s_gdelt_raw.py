"""GDELT's raw 15 minute files: headlines from the knowledge graph, and events with their mentions.

Unlike the DOC search API, these are plain file downloads, so GDELT does not throttle them. Each run catches up on the
batches published since the last one, going back at most three days, and keeps only what bears on a tracked asset
(see news_assets.py):

  knowledge graph (gkg)   the headline of every article whose title names a tracked asset, saved to the headline
                          archive and linked to each asset it names, with GDELT's own full text tone in nw_gdelt_tone
  events (export)         events that match an asset's rule, each with a sentence built from its codes by rule,
                          for example "United States imposes embargo, boycott, or sanctions against Iran in Tehran, Iran."
  mentions                later mentions of the stored events, counted, so widely reported events weigh more

About 3 MB is downloaded per batch, roughly 300 MB a day, and nothing is kept on disk but the matched rows.
"""
import datetime as dt
import io
import pathlib
import re
import sqlite3
import zipfile

import core
from core import ROOT, fetch
from textutil import tidy

BASE = "http://data.gdeltproject.org/gdeltv2/"
CATCH_UP_H = 72        # a normal run fills gaps up to three days back; sentiment_job.py --backfill-days goes further
MIN_MENTIONS = 5
core.HOST_GAP["data.gdeltproject.org"] = 0.5

# CAMEO country codes of the main oil producers and transit states.
OIL = {"IRN", "SAU", "IRQ", "RUS", "VEN", "ARE", "KWT", "YEM", "LBY", "QAT", "NGA", "OMN"}
CONFLICT = {"13", "15", "16", "17", "18", "19", "20"}   # threaten, posture, reduce relations, coerce, assault, fight, mass violence
FORCE = {"15", "18", "19", "20"}


def _pair(e, a, b):
    return {e["c1"], e["c2"]} == {a, b} and e.get("states", True)


def _state(c1, c2):
    """Both actors are a country, its government or its armed forces ("USA", "CHNGOV", "RUSMIL"), and at least one is a
    government or armed force, so a ship or a river GDELT has tagged with a country does not count."""
    ok = lambda c: len(c) >= 3 and c[3:6] in ("", "GOV", "MIL")  # noqa: E731
    return ok(c1) and ok(c2) and (c1[3:6] in ("GOV", "MIL") or c2[3:6] in ("GOV", "MIL"))


def _intl(e, mentions=10):
    """Between the states of two different countries and widely reported, so local crime, protests and GDELT's
    misreadings ("Tanker uses force against Mississippi River") are left out."""
    return len(e["c1"]) == 3 and len(e["c2"]) == 3 and e["c1"] != e["c2"] and e["mentions"] >= mentions and e.get("states", True)


# Which events bear on which asset. Each rule reads one event and returns True when it counts.
RULES = {
    "BRENT": lambda e: _intl(e) and (e["c1"] in OIL or e["c2"] in OIL) and e["root"] in CONFLICT,
    "XAU": lambda e: _intl(e, 30) and e["quad"] == 4,
    "LMT": lambda e: _intl(e, 20) and e["root"] in FORCE,
    "BA.": lambda e: _intl(e, 20) and e["root"] in FORCE,
    "NVDA": lambda e: _pair(e, "USA", "CHN") and e["root"] in CONFLICT and e["mentions"] >= 10,
    "INTC": lambda e: _pair(e, "USA", "CHN") and e["root"] in CONFLICT and e["mentions"] >= 10,
    "GFS": lambda e: _pair(e, "USA", "CHN") and e["root"] in CONFLICT and e["mentions"] >= 10,
    "TSM": lambda e: (_pair(e, "CHN", "TWN") or _pair(e, "USA", "CHN")) and e["root"] in CONFLICT and e["mentions"] >= 10,
    "TWD/USD": lambda e: _pair(e, "CHN", "TWN") and e["mentions"] >= 10,
    "HSI": lambda e: _pair(e, "USA", "CHN") and e["mentions"] >= 10,
    "SX5E": lambda e: _pair(e, "RUS", "UKR") and e["quad"] >= 3 and e["mentions"] >= 20,
    "INR/USD": lambda e: _intl(e) and "IND" in (e["c1"], e["c2"]) and e["quad"] >= 3,
    "USD/COP": lambda e: _intl(e) and "COL" in (e["c1"], e["c2"]),
    "GXG": lambda e: _intl(e) and "COL" in (e["c1"], e["c2"]),
    "EC": lambda e: _intl(e) and "COL" in (e["c1"], e["c2"]) and e["quad"] >= 3,
    "EWZ": lambda e: _intl(e) and "BRA" in (e["c1"], e["c2"]),
    "USD/JPY": lambda e: _intl(e) and "JPN" in (e["c1"], e["c2"]) and e["quad"] >= 3,
}

LABELS = {}
for line in (pathlib.Path(__file__).parent / "cameo_eventcodes.txt").read_text(encoding="utf-8").splitlines()[1:]:
    if "\t" in line:
        k, v = line.split("\t", 1)
        LABELS[k.strip()] = v.strip()


def _third(word):
    v, tail = re.match(r"^(.*?)([,;:]*)$", word).groups()   # "arrest," becomes "arrests,"
    if v.lower() in ("be", "have"):
        return {"be": "is", "have": "has"}[v.lower()] + tail
    if v.endswith(("s", "sh", "ch", "x", "z", "o")):
        return v + "es" + tail
    if v.endswith("y") and len(v) > 1 and v[-2] not in "aeiou":
        return v[:-1] + "ies" + tail
    return v + "s" + tail


def phrase(code):
    """The event code's description as a verb phrase in the third person: "Impose embargo" becomes "imposes embargo"."""
    label = LABELS.get(code) or LABELS.get(code[:3]) or LABELS.get(code[:2]) or "act"
    label = re.sub(r",?\s*not specified below", "", label).strip().lower()
    words = label.split()
    if words[0].endswith("ly") and len(words) > 1:   # "physically assault" becomes "physically assaults"
        words[1] = _third(words[1])
        return " ".join(words)
    words[0] = _third(words[0])
    # "criticize or denounce": the second verb changes too, but not a noun as in "embargo, boycott, or sanctions".
    if len(words) >= 3 and words[1] == "or" and "," not in label.split(" or ")[0]:
        words[2] = _third(words[2])
    return " ".join(words)


def _name(raw):
    return " ".join(w.capitalize() if len(w) > 3 or w not in ("US", "UK", "UN", "EU") else w for w in (raw or "").split()).replace("United States", "United States")


# The word that joins the second actor, by event family, with exceptions by code. "" puts the actor straight after
# the verb, as in "criticizes or denounces Iran".
JOIN = {"01": "about", "02": "to", "03": "with", "04": "with", "05": "with", "06": "with", "07": "to", "08": "to", "09": "",
        "10": "from", "11": "", "12": "from", "13": "against", "14": "against", "15": "against", "16": "against", "17": "against",
        "18": "against", "19": "against", "20": "against"}
JOIN_CODE = {"130": "", "042": "to", "043": "from", "051": "", "052": "", "053": "for", "054": "to", "055": "to", "056": "", "160": "with", "161": "with",
             "162": "to", "171": "of", "172": "on", "16": "with", "180": "", "181": "", "182": "", "1821": "", "1822": ""}


def sentence(e):
    """A plain sentence built from the event's codes, by rule."""
    a1, a2 = _name(e["a1"]), _name(e["a2"])
    if not a1:
        return None
    text = f"{a1} {phrase(e['code'])}"
    if a2:
        join = JOIN_CODE.get(e["code"], JOIN_CODE.get(e["code"][:3], JOIN.get(e["root"], "with")))
        text += f" {join} {a2}" if join else f" {a2}"
    if e["place"]:
        parts = [p.strip() for p in e["place"].split(",") if p.strip()]
        text += " in " + (parts[0] if len(parts) == 1 else f"{parts[0]}, {parts[-1]}")
    return text + "."


def _iso(stamp):
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[8:10]}:{stamp[10:12]}:{stamp[12:14]}Z" if len(stamp) >= 14 else None


def _lines(url):
    r = fetch(url, timeout=120, retries=3, ok_404=True)
    if r is None:
        return []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return z.read(z.namelist()[0]).decode("utf-8", errors="replace").splitlines()


TITLES = ROOT / "data" / "gdelt_titles.db"


def titles():
    """Every English headline GDELT has listed in the last 31 days, with a full text index, in its own file so it never
    reaches the Rehyn database or its hosted copy. It lets an asset added later be searched over 30 days in seconds."""
    t = sqlite3.connect(TITLES, timeout=120)
    t.execute("PRAGMA journal_mode=WAL")
    t.execute("CREATE VIRTUAL TABLE IF NOT EXISTS headline USING fts5(title, url UNINDEXED, published UNINDEXED, source UNINDEXED, tokenize='porter unicode61')")
    return t


def gkg(con, stamp, match, touched, tcon=None):
    """Headlines that name a tracked asset, linked to each asset they name, and every headline to the title index.
    Returns the number saved for tracked assets."""
    rows, tones, links, every = [], [], [], []
    for line in _lines(f"{BASE}{stamp}.gkg.csv.zip"):
        f = line.split("\t")
        if len(f) < 27:
            continue
        m = re.search(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", f[26])
        title = tidy(m.group(1)) if m else ""
        url = f[4]
        if len(title) < 20 or not url.startswith("http"):
            continue
        every.append((title[:300], url, _iso(f[1]), f[3]))
        hits = match(title)
        if not hits:
            continue
        rows.append((url, _iso(f[1]), f[3], "gdelt_gkg", title[:300], None, None, "en", "asset"))
        links += [(url, a) for a in hits]
        touched.update(hits)
        t = (f[15].split(",") + [""] * 7)[:7]
        try:
            tones.append((url, float(t[0]), float(t[1]), float(t[2]), float(t[3]), int(float(t[6] or 0))))
        except ValueError:
            pass
    con.executemany("""INSERT INTO nw_article(dataset_id, url, published, source, feed, title, summary, country, lang, theme)
                       VALUES('news_gdelt',?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO NOTHING""", rows)
    con.executemany("INSERT OR IGNORE INTO nw_asset_link(url, asset) VALUES(?,?)", links)
    con.executemany("INSERT OR REPLACE INTO nw_gdelt_tone VALUES(?,?,?,?,?,?)", tones)
    if tcon is not None and every:
        tcon.executemany("INSERT INTO headline(title, url, published, source) VALUES(?,?,?,?)", every)
        tcon.commit()
    return len(rows)


def events(con, stamp, touched):
    rows = []
    for line in _lines(f"{BASE}{stamp}.export.CSV.zip"):
        f = line.split("\t")
        if len(f) < 61 or f[25] != "1":
            continue
        try:
            e = dict(id=int(f[0]), date=f[1], a1=f[6], c1=f[7] or f[5][:3], a2=f[16], c2=f[17] or f[15][:3], code=f[26], root=f[28], quad=int(f[29] or 0),
                     goldstein=float(f[30] or 0), mentions=int(f[31] or 0), sources=int(f[32] or 0), articles=int(f[33] or 0), tone=float(f[34] or 0),
                     place=f[52], gc=f[53], added=_iso(f[59]), url=f[60], states=_state(f[5], f[15]))
        except ValueError:
            continue
        if e["mentions"] < MIN_MENTIONS:
            continue
        hits = [a for a, rule in RULES.items() if rule(e)]
        text = sentence(e) if hits else None
        if not text:
            continue
        rows.append((e["id"], e["added"], e["date"], _name(e["a1"]), e["c1"], _name(e["a2"]), e["c2"], e["code"], e["root"], e["quad"], e["goldstein"],
                     e["mentions"], 0, e["sources"], e["articles"], e["tone"], e["place"], e["gc"], e["url"], text, "," + ",".join(hits) + ","))
        touched.update(hits)
    con.executemany("INSERT OR IGNORE INTO geo_gdelt_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def mentions(con, stamp, known):
    counts = {}
    for line in _lines(f"{BASE}{stamp}.mentions.CSV.zip"):
        f = line.split("\t", 2)
        try:
            eid = int(f[0])
        except (ValueError, IndexError):
            continue
        if eid in known:
            counts[eid] = counts.get(eid, 0) + 1
    con.executemany("UPDATE geo_gdelt_event SET mentions_seen=mentions_seen+? WHERE event_id=?", [(n, eid) for eid, n in counts.items()])
    return sum(counts.values())


def catch_up(con, assets, run_, hours=CATCH_UP_H):
    """Processes every batch published in the last `hours` that has not been processed yet: three days on a normal
    run, up to 31 days to fill the history. Returns the assets touched."""
    import news_assets
    con.execute("CREATE TABLE IF NOT EXISTS cat_gdelt_raw_done(stamp TEXT PRIMARY KEY, done_at TEXT)")
    latest = re.search(r"/(\d{14})\.gkg\.csv\.zip", fetch(BASE + "lastupdate.txt", timeout=60).text).group(1)
    end = dt.datetime.strptime(latest, "%Y%m%d%H%M%S")
    t = end - dt.timedelta(hours=hours)
    done = {r[0] for r in con.execute("SELECT stamp FROM cat_gdelt_raw_done WHERE stamp>=?", (t.strftime("%Y%m%d%H%M%S"),))}
    match = news_assets.Matcher(assets)
    since = (end - dt.timedelta(hours=hours + 24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    known = {r[0] for r in con.execute("SELECT event_id FROM geo_gdelt_event WHERE added>=?", (since,))}
    tcon = titles()
    touched, heads, evs, ments, batches = set(), 0, 0, 0, 0
    while t <= end:
        stamp = t.strftime("%Y%m%d%H%M%S")
        t += dt.timedelta(minutes=15)
        if stamp in done:
            continue
        try:
            heads += gkg(con, stamp, match, touched, tcon)
            n = events(con, stamp, touched)
            evs += n
            if n:
                known |= {r[0] for r in con.execute("SELECT event_id FROM geo_gdelt_event WHERE added>=?", (since,))}
            ments += mentions(con, stamp, known)
        except Exception as e:
            run_.note(f"{stamp}: {type(e).__name__}: {e}")
            continue
        con.execute("INSERT OR REPLACE INTO cat_gdelt_raw_done VALUES(?, datetime('now'))", (stamp,))
        con.commit()
        batches += 1
        if batches % 24 == 0:
            print(f"  through {stamp}: {heads:,} headlines, {evs:,} events, {ments:,} mentions", flush=True)
    # The record of processed batches is kept as long as the data, so it also tells how many days of history there are.
    con.execute("DELETE FROM cat_gdelt_raw_done WHERE stamp<?", ((end - dt.timedelta(days=32)).strftime("%Y%m%d%H%M%S"),))
    con.commit()
    tcon.execute("DELETE FROM headline WHERE published<?", ((end - dt.timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    tcon.commit()
    tcon.close()
    run_.note(f"{batches} GDELT batches: {heads:,} headlines, {evs:,} events, {ments:,} mentions of stored events")
    return touched
