"""Company data from SEC EDGAR: reported financials, the filing index and insider transactions."""
import csv
import datetime as dt
import io
import zipfile

from core import Run, fetch

FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
SUBS = "https://data.sec.gov/submissions/CIK{:010d}.json"
INSIDER = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{}q{}_form345.zip"

# Rehyn concept name and the XBRL tags that report it, in order of preference.
CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_basic": ["EarningsPerShareBasic"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "interest_expense": ["InterestExpense"],
    "tax_expense": ["IncomeTaxExpenseBenefit"],
    "assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "liabilities": ["Liabilities"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "inventory": ["InventoryNet"],
    "receivables": ["AccountsReceivableNetCurrent"],
    "goodwill": ["Goodwill"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "shares_outstanding": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"],
}
TAG_TO_CONCEPT = {tag: (name, rank) for name, tags in CONCEPTS.items() for rank, tag in enumerate(tags)}


def _facts_rows(cik, symbol, payload):
    """Collapse XBRL facts to one row per period, keeping the first and the latest reported value."""
    best = {}
    for taxonomy in ("us-gaap", "dei"):
        for tag, body in (payload.get("facts", {}).get(taxonomy) or {}).items():
            hit = TAG_TO_CONCEPT.get(tag)
            if not hit:
                continue
            concept, rank = hit
            for unit, facts in body.get("units", {}).items():
                for f in facts:
                    end = f.get("end")
                    if not end or f.get("val") is None:
                        continue
                    key = (concept, f.get("start") or "", end)
                    cur = best.get(key)
                    if cur and cur["rank"] < rank:
                        continue
                    filed = f.get("filed") or ""
                    if cur is None or cur["rank"] > rank:
                        cur = best[key] = {"rank": rank, "unit": unit, "first": f["val"], "first_filed": filed, "val": f["val"],
                                           "last_filed": filed, "fy": f.get("fy"), "fp": f.get("fp"), "form": f.get("form")}
                        continue
                    if filed < cur["first_filed"]:
                        cur["first"], cur["first_filed"] = f["val"], filed
                    if filed >= cur["last_filed"]:
                        cur["val"], cur["last_filed"], cur["fy"], cur["fp"], cur["form"] = f["val"], filed, f.get("fy"), f.get("fp"), f.get("form")
    return [(cik, symbol, c, v["unit"], s, e, v["fy"], v["fp"], v["form"], v["val"], v["first"], v["first_filed"], v["last_filed"])
            for (c, s, e), v in best.items()]


def facts(con):
    with Run(con, "sec_facts") as run_:
        cos = con.execute("SELECT cik, min(symbol) symbol FROM ref_asset WHERE cik IS NOT NULL AND asset_class='Equity' GROUP BY cik").fetchall()
        missing = 0
        for i, c in enumerate(cos, 1):
            r = fetch(FACTS.format(c["cik"]), ok_404=True, timeout=90)
            if r is None:
                missing += 1
                continue
            rows = _facts_rows(c["cik"], c["symbol"], r.json())
            con.executemany("INSERT OR REPLACE INTO co_fact VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            run_.rows += len(rows)
            if i % 20 == 0:
                con.commit()
                print(f"  {i}/{len(cos)} companies, {run_.rows:,} facts", flush=True)
        con.commit()
        run_.note(f"{len(cos)} companies, {missing} without XBRL facts")


def _filing_rows(cik, symbol, block):
    keys = ("accessionNumber", "form", "filingDate", "reportDate", "items", "primaryDocument", "primaryDocDescription")
    cols = [block.get(k) or [] for k in keys]
    n = len(cols[0])
    rows = []
    for i in range(n):
        acc, form, filed, report, items, doc, desc = (c[i] if i < len(c) else None for c in cols)
        rows.append((acc, cik, symbol, form, filed, report, items, doc, desc))
    return rows


def filings(con):
    with Run(con, "sec_filings") as run_:
        cos = con.execute("SELECT cik, min(symbol) symbol FROM ref_asset WHERE cik IS NOT NULL AND asset_class='Equity' GROUP BY cik").fetchall()
        for i, c in enumerate(cos, 1):
            r = fetch(SUBS.format(c["cik"]), ok_404=True)
            if r is None:
                continue
            body = r.json()
            con.execute(
                "UPDATE ref_asset SET industry=coalesce(industry, ?) WHERE cik=?", (body.get("sicDescription"), c["cik"])
            )
            rows = _filing_rows(c["cik"], c["symbol"], body.get("filings", {}).get("recent", {}))
            con.executemany("INSERT OR REPLACE INTO co_filing VALUES(?,?,?,?,?,?,?,?,?)", rows)
            run_.rows += len(rows)
            if i % 25 == 0:
                con.commit()
                print(f"  {i}/{len(cos)} companies, {run_.rows:,} filings", flush=True)
        con.commit()


def _tsv(z, name):
    with z.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t"))


def _date(raw):
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except (TypeError, ValueError):
            pass
    return None


def _num(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def insider(con, quarters=12):
    with Run(con, "sec_insider") as run_:
        known = {r[0] for r in con.execute("SELECT symbol FROM ref_asset WHERE asset_class='Equity'")}
        today = dt.date.today()
        year, q = today.year, (today.month - 1) // 3 + 1
        got = 0
        for _ in range(quarters + 2):
            q -= 1
            if q == 0:
                year, q = year - 1, 4
            r = fetch(INSIDER.format(year, q), ok_404=True, timeout=180)
            if r is None:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            subs = {x["ACCESSION_NUMBER"]: x for x in _tsv(z, "SUBMISSION.tsv")}
            owners = {}
            for o in _tsv(z, "REPORTINGOWNER.tsv"):
                owners.setdefault(o["ACCESSION_NUMBER"], o)
            rows = []
            for i, t in enumerate(_tsv(z, "NONDERIV_TRANS.tsv")):
                acc = t["ACCESSION_NUMBER"]
                s = subs.get(acc)
                if not s:
                    continue
                sym = (s.get("ISSUERTRADINGSYMBOL") or "").strip().upper()
                if sym not in known:
                    continue
                o = owners.get(acc, {})
                rows.append((acc, int(t.get("NONDERIV_TRANS_SK") or i), sym, s.get("ISSUERNAME"), o.get("RPTOWNERNAME"),
                             o.get("RPTOWNER_RELATIONSHIP") or o.get("RPTOWNER_TITLE"), _date(s.get("FILING_DATE")), _date(t.get("TRANS_DATE")),
                             t.get("TRANS_CODE"), t.get("TRANS_ACQUIRED_DISP_CD"), _num(t.get("TRANS_SHARES")),
                             _num(t.get("TRANS_PRICEPERSHARE")), _num(t.get("SHRS_OWND_FOLWNG_TRANS"))))
            con.executemany("INSERT OR REPLACE INTO co_insider_tx VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)
            got += 1
            print(f"  {year}Q{q}: {len(rows):,} transactions", flush=True)
            if got >= quarters:
                break
        run_.note(f"{got} quarters")


def run(con):
    for step in (filings, facts, insider):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
