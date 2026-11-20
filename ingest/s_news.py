"""News and narrative. Publishers are stored as headline, short summary and link only.

Full text is kept only where it is free to reuse: Wikipedia summaries, Fed statements, Federal Register abstracts.
"""
import datetime as dt
import email.utils
import html
import json
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from core import Run, fetch, restricted

# Feed label, publisher, url
FEEDS = [
    ("bbc_business", "BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("bbc_world", "BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("bbc_tech", "BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("guardian_business", "The Guardian", "https://www.theguardian.com/business/rss"),
    ("guardian_world", "The Guardian", "https://www.theguardian.com/world/rss"),
    ("guardian_markets", "The Guardian", "https://www.theguardian.com/business/stock-markets/rss"),
    ("cnbc_top", "CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("cnbc_finance", "CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("cnbc_economy", "CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("cnbc_energy", "CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19836768"),
    ("marketwatch_top", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("marketwatch_pulse", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("aljazeera", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("nyt_business", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("nyt_world", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("ft_home", "Financial Times", "https://www.ft.com/rss/home"),
    ("oilprice", "OilPrice.com", "https://oilprice.com/rss/main"),
    ("coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]

GOOGLE_TOPICS = ["OPEC oil output", "Federal Reserve rates", "Taiwan China", "tariffs trade war", "sanctions Russia", "Iran Strait of Hormuz",
                 "semiconductor export controls", "AI chips Nvidia", "gold price", "bitcoin ETF", "US election markets", "recession risk"]

# Themes for the GDELT archive. Each is one search, split into windows by date.
GDELT_THEMES = {
    "opec": '(opec OR "oil output" OR "oil production cut")',
    "fed": '("federal reserve" OR fomc OR "rate cut" OR "rate hike")',
    "taiwan": '(taiwan AND (china OR strait OR blockade))',
    "tariffs": '(tariffs OR "trade war")',
    "sanctions": '(sanctions AND (russia OR iran OR china))',
    "hormuz": '("strait of hormuz" OR "red sea" OR houthi)',
    "chips": '(semiconductor OR "export controls" OR tsmc OR nvidia)',
    "ukraine": '(ukraine AND (war OR invasion OR offensive))',
    "election": '("presidential election" AND (markets OR stocks))',
    "banks": '("bank failure" OR "bank run" OR "banking crisis")',
    "crypto": '(bitcoin OR "crypto regulation")',
    "recession": '(recession OR "yield curve")',
}


def clean(text, limit=320):
    if not text:
        return None
    t = BeautifulSoup(html.unescape(text), "lxml").get_text(" ", strip=True)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit] or None


def parse_when(raw):
    if not raw:
        return None
    try:
        d = email.utils.parsedate_to_datetime(raw)
        return (d.astimezone(dt.timezone.utc) if d.tzinfo else d).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def rss_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        out = {}
        for c in el:
            name = _local(c.tag)
            if name == "link":
                out["link"] = c.get("href") or (c.text or "").strip() or out.get("link")
            elif name in ("title", "description", "summary", "pubDate", "published", "updated", "date"):
                out.setdefault(name, c.text)
        if out.get("title") and out.get("link"):
            yield out


def _save(con, dataset, rows):
    cur = con.executemany(
        """INSERT INTO nw_article(dataset_id, url, published, source, feed, title, summary, country, lang, theme)
           VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO NOTHING""",
        [(dataset, *r) for r in rows],
    )
    con.commit()
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


@restricted("Publisher terms limit feeds to personal use, or need permission for business use")
def rss(con):
    with Run(con, "news_rss") as run_:
        failed = []
        for feed, source, url in FEEDS:
            try:
                r = fetch(url, retries=2, timeout=30)
                rows = []
                for it in rss_items(r.content):
                    when = parse_when(it.get("pubDate") or it.get("published") or it.get("updated") or it.get("date"))
                    rows.append((it["link"], when, source, feed, clean(it["title"], 300), clean(it.get("description") or it.get("summary")), None, "en", None))
                run_.rows += _save(con, "news_rss", rows)
            except Exception:
                failed.append(feed)
        for topic in GOOGLE_TOPICS:
            try:
                r = fetch("https://news.google.com/rss/search", params={"q": f"{topic} when:7d", "hl": "en-US", "gl": "US", "ceid": "US:en"}, retries=2)
                rows = []
                for it in rss_items(r.content):
                    title = clean(it["title"], 300) or ""
                    source = title.rsplit(" - ", 1)[-1] if " - " in title else "Google News"
                    rows.append((it["link"], parse_when(it.get("pubDate")), source, "google_news", title.rsplit(" - ", 1)[0], None, None, "en", topic))
                run_.rows += _save(con, "news_rss", rows)
            except Exception:
                failed.append(f"google:{topic}")
        if failed:
            run_.note(f"feeds not read: {', '.join(failed)}")


def gdelt(con, start_year=2017, months_per_window=3):
    """Archive headlines at GDELT's limit of one request per 5 seconds. Finished windows are skipped on rerun."""
    with Run(con, "news_gdelt") as run_:
        con.execute("CREATE TABLE IF NOT EXISTS cat_gdelt_done(theme TEXT, start TEXT, PRIMARY KEY(theme, start))")
        today = dt.date.today()
        windows = []
        y, m = today.year, ((today.month - 1) // months_per_window) * months_per_window + 1
        while y >= start_year:
            windows.append(dt.date(y, m, 1))
            m -= months_per_window
            if m < 1:
                y, m = y - 1, m + 12
        for start in windows:
            month = start.month + months_per_window
            end = dt.date(start.year + (month - 1) // 12, (month - 1) % 12 + 1, 1)
            for theme, query in GDELT_THEMES.items():
                if con.execute("SELECT 1 FROM cat_gdelt_done WHERE theme=? AND start=?", (theme, start.isoformat())).fetchone():
                    continue
                try:
                    r = fetch("https://api.gdeltproject.org/api/v2/doc/doc", params={
                        "query": f"{query} sourcelang:english", "mode": "artlist", "format": "json", "maxrecords": 250, "sort": "hybridrel",
                        "startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d000000"),
                    }, timeout=60)
                    body = json.loads(r.text or "{}") if r.text.strip().startswith("{") else {}
                except Exception as e:
                    run_.note(f"{theme} {start}: {e}")
                    continue
                rows = []
                for a in body.get("articles") or []:
                    seen = a.get("seendate") or ""
                    when = f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}T{seen[9:11]}:{seen[11:13]}:{seen[13:15]}Z" if len(seen) >= 15 else None
                    rows.append((a.get("url"), when, a.get("domain"), "gdelt", clean(a.get("title"), 300) or "(untitled)", None, a.get("sourcecountry"), a.get("language"), theme))
                run_.rows += _save(con, "news_gdelt", [x for x in rows if x[0]])
                con.execute("INSERT OR REPLACE INTO cat_gdelt_done VALUES(?,?)", (theme, start.isoformat()))
                con.commit()
            print(f"  gdelt window {start}: {run_.rows:,} articles so far", flush=True)


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
WIKI_API = "https://en.wikipedia.org/w/api.php"


def _strip_wikitext(text):
    links = re.findall(r"\[\[([^\]|#]+)", text)
    sources = re.findall(r"\[(https?://\S+)", text)
    t = re.sub(r"\[https?://\S+\s*([^\]]*)\]", "", text)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"'{2,}", "", t)
    return re.sub(r"\s+", " ", t).strip(), links, sources


def parse_day(wikitext, date):
    """Portal day pages use bold category headers and nested bullets: topic at one level, the event below it."""
    rows, category, stack = [], None, {}
    for line in wikitext.splitlines():
        line = line.strip()
        head = re.fullmatch(r"(?:'''|;)\s*(.+?)\s*(?:''')?:?", line)
        if head and not line.startswith("*"):
            category = re.sub(r"\[\[|\]\]|'''", "", head.group(1)).split("|")[-1].strip(" :")
            stack = {}
            continue
        m = re.match(r"(\*+)\s*(.*)", line)
        if not m:
            continue
        depth, body = len(m.group(1)), m.group(2)
        text, links, sources = _strip_wikitext(body)
        if not text:
            continue
        stack = {k: v for k, v in stack.items() if k < depth}
        stack[depth] = text
        if not sources and len(text) < 90:
            continue
        topic = " / ".join(stack[k] for k in sorted(stack) if k < depth) or None
        rows.append((date, category, topic, text[:900], json.dumps(sources[:4]), json.dumps(links[:12])))
    return rows


def wiki_events(con, first_year=2002):
    with Run(con, "wiki_events") as run_:
        today = dt.date.today()
        days = []
        d = dt.date(first_year, 1, 1)
        while d < today:
            days.append(d)
            d += dt.timedelta(days=1)
        for i in range(0, len(days), 50):
            batch = days[i:i + 50]
            titles = {f"Portal:Current events/{x.year} {MONTHS[x.month - 1]} {x.day}": x for x in batch}
            r = fetch(WIKI_API, params={"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
                                        "formatversion": 2, "titles": "|".join(titles)})
            rows = []
            for page in r.json()["query"].get("pages", []):
                rev = page.get("revisions")
                date = titles.get(page.get("title"))
                if rev and date:
                    rows += parse_day(rev[0]["slots"]["main"]["content"], date.isoformat())
            con.executemany("INSERT OR IGNORE INTO nw_event(date, category, topic, text, sources, links) VALUES(?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)
            if (i // 50) % 20 == 0:
                print(f"  through {batch[-1]}: {run_.rows:,} events", flush=True)


def _release(con, dataset, rows):
    cur = con.executemany(
        """INSERT INTO doc_release(dataset_id, institution, kind, date, title, url, abstract, body)
           VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET body=coalesce(excluded.body, body)""",
        [(dataset, *r) for r in rows],
    )
    con.commit()
    return len(rows)


def fed(con, statements=True):
    with Run(con, "fed_releases") as run_:
        r = fetch("https://www.federalreserve.gov/json/ne-press.json")
        data = json.loads(r.content.decode("utf-8-sig"))
        rows = []
        for x in data:
            if not x.get("t") or not x.get("l"):
                continue
            try:
                d = dt.datetime.strptime(x["d"].split(" ")[0], "%m/%d/%Y").date().isoformat()
            except (KeyError, ValueError):
                continue
            rows.append(("Federal Reserve", x.get("pt"), d, clean(x["t"], 300), "https://www.federalreserve.gov" + x["l"], None, None))
        run_.rows += _release(con, "docs_fed", rows)
        if not statements:
            return
        todo = con.execute(
            "SELECT id, url FROM doc_release WHERE dataset_id='docs_fed' AND kind LIKE 'Monetary%' AND body IS NULL"
        ).fetchall()
        for row in todo:
            try:
                page = fetch(row["url"], retries=2, timeout=30, ok_404=True)
            except Exception:
                continue
            if page is None:
                continue
            soup = BeautifulSoup(page.text, "lxml")
            box = soup.select_one("#article") or soup.select_one("#content") or soup.body
            text = re.sub(r"\s+", " ", box.get_text(" ", strip=True)) if box else None
            con.execute("UPDATE doc_release SET body=? WHERE id=?", (text[:12000] if text else None, row["id"]))
            con.commit()
        run_.note(f"{len(todo)} monetary policy releases read in full")


@restricted("Bank of England site content is for personal or internal non-commercial use")
def central_bank_rss(con):
    with Run(con, "central_bank_rss") as run_:
        for inst, url in (("European Central Bank", "https://www.ecb.europa.eu/rss/press.html"), ("Bank of England", "https://www.bankofengland.co.uk/rss/news")):
            r = fetch(url)
            rows = []
            for it in rss_items(r.content):
                when = parse_when(it.get("pubDate") or it.get("published") or it.get("updated"))
                rows.append((inst, "Press", (when or "")[:10] or None, clean(it["title"], 300), it["link"], clean(it.get("description") or it.get("summary"), 500), None))
            run_.rows += _release(con, "docs_central_banks", rows)


def federal_register(con, first_year=1994):
    """Presidential documents plus any rule or notice on tariffs, export controls or sanctions."""
    with Run(con, "federal_register") as run_:
        searches = [
            ("Executive order", {"conditions[presidential_document_type][]": "executive_order"}),
            ("Proclamation", {"conditions[presidential_document_type][]": "proclamation"}),
            ("Tariffs and trade", {"conditions[term]": '"section 301" OR "section 232" OR tariff'}),
            ("Export controls", {"conditions[agencies][]": "industry-and-security-bureau"}),
            ("Sanctions", {"conditions[agencies][]": "foreign-assets-control-office"}),
        ]
        for kind, params in searches:
            for year in range(first_year, dt.date.today().year + 1):
                page = 1
                while True:
                    q = {"per_page": 1000, "page": page, "order": "oldest",
                         "fields[]": ["title", "abstract", "html_url", "publication_date", "type", "document_number"],
                         "conditions[publication_date][year]": year, **params}
                    r = fetch("https://www.federalregister.gov/api/v1/documents.json", params=q, retries=3)
                    body = r.json()
                    rows = [("Federal Register", kind, x.get("publication_date"), clean(x.get("title"), 300) or "(untitled)", x.get("html_url"), clean(x.get("abstract"), 900), None)
                            for x in body.get("results") or [] if x.get("html_url")]
                    if rows:
                        run_.rows += _release(con, "docs_federal_register", rows)
                    if not body.get("next_page_url") or page >= 9:
                        break
                    page += 1
            print(f"  {kind}: {run_.rows:,} documents so far", flush=True)


def run(con):
    for step in (rss, central_bank_rss, fed, federal_register, wiki_events):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
