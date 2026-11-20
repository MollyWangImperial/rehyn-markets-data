"""Derived tables. Everything here is computed from collected data, nothing is typed in by hand."""
import re

import numpy as np
import pandas as pd

from core import SCHEMA, Run

# Assets every event is measured against: broad markets, safe havens, energy, FX and sector ETFs.
STUDY_SYMBOLS = [
    "SPX", "NDX", "RUT", "DJI", "UKX", "DAX", "SX5E", "NKY", "HSI", "SHCOMP", "IBOV", "KOSPI", "TAIEX", "VIX",
    "BRENT", "WTI", "NATGAS", "XAU/USD", "XAG/USD", "COPPER", "WHEAT", "CORN", "KC",
    "DXY", "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CNY", "USD/BRL", "USD/COP", "USD/TRY", "USD/RUB", "USD/TWD",
    "BTC/USD", "ETH/USD", "US10Y", "US3M",
    "SPY", "QQQ", "IWM", "EEM", "TLT", "HYG", "LQD", "GLD", "USO", "XLE", "XLF", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB",
    "SMH", "ITA", "KRE", "XHB", "JETS", "GDX", "EWZ", "EWT", "FXI", "COLO", "KWEB",
    "XOM", "CVX", "OXY", "LMT", "RTX", "NOC", "GD", "BA", "DAL", "UAL", "CCL", "TSM", "NVDA", "AAPL", "MSFT", "INTC", "JPM", "BAC", "EQNR", "EC", "CIB", "EMBJ",
]

# Family, category filter or None, FTS query. Each search runs over the dated Wikipedia event record.
TEXT_FAMILIES = [
    ("OPEC output decision", None, 'opec AND (cut OR cuts OR reduce OR reduces OR output OR production)'),
    ("Invasion or interstate attack", "Armed conflicts and attacks", '(invades OR invasion OR "declares war" OR "launches strikes" OR airstrikes) AND (troops OR forces OR military)'),
    ("Coup", None, '"coup" AND (military OR president OR government)'),
    ("Sanctions imposed", None, '(imposes OR impose OR announces) AND sanctions'),
    ("Tariff action", None, 'tariff OR tariffs'),
    ("Bank failure or rescue", "Business and economy", 'bank AND (collapse OR collapses OR bailout OR bankruptcy OR rescue OR failure)'),
    ("Sovereign default or debt crisis", None, '(default OR defaults OR "debt crisis") AND (government OR sovereign OR bonds)'),
    ("Taiwan Strait tension", None, 'taiwan AND (china OR chinese OR pla) AND (drills OR exercises OR strait OR missile OR military)'),
    ("Gulf shipping or Hormuz attack", None, '(hormuz OR "red sea" OR "persian gulf") AND (tanker OR ship OR attack OR seized)'),
    ("Pipeline or energy infrastructure attack", None, '(pipeline OR refinery OR "oil facility") AND (attack OR explosion OR sabotage OR drone)'),
    ("Pandemic or outbreak declaration", None, '(pandemic OR "public health emergency") AND (who OR "world health organization" OR declares)'),
    ("Major earthquake or disaster", "Disasters and accidents", '(earthquake OR tsunami OR hurricane OR typhoon) AND (dead OR killed OR deaths)'),
    ("National election result", "Politics and elections", '(wins OR elected OR victory OR defeats) AND (presidential OR "general election" OR "prime minister")'),
    ("Export controls on chips", None, 'semiconductor AND ("export controls" OR restrictions OR ban OR sanctions)'),
]


def prices(con, asset_id):
    df = pd.read_sql_query(
        "SELECT date, coalesce(adj_close, close) px, close, high, low, volume FROM px_daily WHERE asset_id=? ORDER BY date",
        con, params=(asset_id,), parse_dates=["date"],
    )
    return df.dropna(subset=["px"]).set_index("date")


def _rsi(px, n=14):
    delta = px.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return float(100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1])) if loss.iloc[-1] else 100.0


def _ret(px, n):
    return float(px.iloc[-1] / px.iloc[-1 - n] - 1) if len(px) > n and px.iloc[-1 - n] else None


def flags(con):
    """Mark implausible one day equity moves. Rows stay in px_daily, flagged days are only kept out of statistics."""
    with Run(con, "price_flags") as run_:
        con.execute("""CREATE TABLE IF NOT EXISTS x_price_flag(
            asset_id INTEGER, date TEXT, ret REAL, reason TEXT, PRIMARY KEY(asset_id, date)) WITHOUT ROWID""")
        con.execute("DELETE FROM x_price_flag")
        rows = []
        for a in con.execute("SELECT asset_id FROM ref_asset WHERE asset_class IN ('Equity','ETF')").fetchall():
            px = prices(con, a["asset_id"])["px"]
            r = px.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
            hit = r[(r > 1.5) | (r < -0.75)]
            rows += [(a["asset_id"], d.date().isoformat(), float(v), "One day move over +150% or under -75%, needs review") for d, v in hit.items()]
        con.executemany("INSERT OR REPLACE INTO x_price_flag VALUES(?,?,?,?)", rows)
        con.commit()
        run_.rows = len(rows)


def metrics(con):
    with Run(con, "metrics") as run_:
        spx = con.execute("SELECT asset_id FROM ref_asset WHERE symbol='SPX'").fetchone()
        bench = prices(con, spx[0])["px"].pct_change() if spx else None
        flagged = {}
        for f in con.execute("SELECT asset_id, date FROM x_price_flag"):
            flagged.setdefault(f[0], set()).add(pd.Timestamp(f[1]))
        rows = []
        for a in con.execute("SELECT asset_id, asset_class FROM ref_asset").fetchall():
            df = prices(con, a["asset_id"])
            if len(df) < 30:
                continue
            px = df["px"]
            # Yields and the VIX are levels, and can touch zero, so day-on-day ratios need a guard.
            rets = px.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
            rets = rets[~rets.index.isin(flagged.get(a["asset_id"], set()))]
            r20 = (px / px.shift(20) - 1).replace([np.inf, -np.inf], np.nan).dropna()
            year = px.iloc[-252:]
            peak = px.cummax()
            dd = px / peak - 1
            ytd_base = px[px.index.year < px.index[-1].year]
            beta = None
            if bench is not None and a["asset_class"] != "Index":
                joined = pd.concat([rets.iloc[-252:], bench], axis=1, join="inner").dropna()
                if len(joined) > 60 and joined.iloc[:, 1].var():
                    beta = float(joined.cov().iloc[0, 1] / joined.iloc[:, 1].var())
            rows.append((
                a["asset_id"], df.index[-1].date().isoformat(), float(df["close"].iloc[-1]),
                _ret(px, 1), _ret(px, 5), _ret(px, 20), _ret(px, 60), _ret(px, 252),
                float(px.iloc[-1] / ytd_base.iloc[-1] - 1) if len(ytd_base) else None,
                float(r20.median()) if len(r20) else None,
                float(rets.iloc[-20:].std() * np.sqrt(252)), float(rets.iloc[-252:].std() * np.sqrt(252)),
                float(year.max()), float(year.min()),
                float(dd.iloc[-1]), float(dd.min()), dd.idxmin().date().isoformat(),
                _rsi(px), float(df["volume"].iloc[-20:].mean()) if df["volume"].notna().any() else None, beta,
                float(rets.max()), rets.idxmax().date().isoformat(), float(rets.min()), rets.idxmin().date().isoformat(),
                round((df.index[-1] - df.index[0]).days / 365.25, 1),
                float(df["close"].iloc[-200:].mean()) if len(df) >= 200 else None,
                float(df["volume"].iloc[-1] / df["volume"].iloc[-20:].mean()) if df["volume"].iloc[-20:].mean() else None,
            ))
        con.execute("DROP TABLE IF EXISTS x_asset_metric")
        con.executescript(re.search(r"CREATE TABLE IF NOT EXISTS x_asset_metric\(.*?\n\);", SCHEMA.read_text(encoding="utf-8"), re.S).group(0))
        con.executemany(f"INSERT INTO x_asset_metric VALUES({','.join('?' * 27)})", rows)
        con.commit()
        run_.rows = len(rows)


def regimes(con):
    """Dated market regimes for backtests. All computed, using a 20% peak to trough rule for bear markets."""
    with Run(con, "regimes") as run_:
        con.execute("DELETE FROM x_regime")
        out = []
        spx = con.execute("SELECT asset_id FROM ref_asset WHERE symbol='SPX'").fetchone()
        px = prices(con, spx[0])["close"]
        peak_date, peak, trough_date, trough, bear = px.index[0], px.iloc[0], None, None, False
        for d, v in px.items():
            if not bear:
                if v > peak:
                    peak_date, peak = d, v
                elif v <= peak * 0.8:
                    bear, trough_date, trough = True, d, v
            else:
                if v < trough:
                    trough_date, trough = d, v
                elif v >= trough * 1.2:
                    out.append(("Bear market", peak_date.date().isoformat(), trough_date.date().isoformat(), f"S&P 500 fell {trough / peak - 1:.0%}", round(float(trough / peak - 1) * 100, 1)))
                    bear, peak_date, peak = False, d, v
        target = pd.concat([_series(con, "fred:DFEDTAR"), _series(con, "fred:DFEDTARU")]).sort_index()
        target = target[~target.index.duplicated(keep="last")]
        moves = target.diff().dropna()
        moves = moves[moves.abs() >= 0.05]
        start, sign, last, total = None, 0, None, 0.0
        for d, v in moves.items():
            s = 1 if v > 0 else -1
            if s != sign:
                if start is not None:
                    out.append(("Hiking cycle" if sign > 0 else "Cutting cycle", start.date().isoformat(), last.date().isoformat(), f"Fed moved {total * 100:+.0f}bp", round(total * 100)))
                start, sign, total = d, s, 0.0
            last, total = d, total + v
        if start is not None:
            out.append(("Hiking cycle" if sign > 0 else "Cutting cycle", start.date().isoformat(), last.date().isoformat(), f"Fed moved {total * 100:+.0f}bp", round(total * 100)))
        rec = _series(con, "fred:USREC")
        on = None
        for d, v in rec.items():
            if v == 1 and on is None:
                on = d
            elif v == 0 and on is not None:
                out.append(("Recession", on.date().isoformat(), d.date().isoformat(), "NBER dated US recession", None))
                on = None
        brent = _series(con, "eia:RBRTEd")
        six = brent / brent.shift(126) - 1
        for d in _spread(list(six[six >= 0.5].index), 180):
            out.append(("Oil shock", d.date().isoformat(), None, f"Brent up {six[d]:.0%} in six months", round(float(six[d]) * 100, 1)))
        for year in range(1928, pd.Timestamp.today().year + 1, 4):
            out.append(("Election year", f"{year}-01-01", f"{year}-12-31", f"US presidential election, {year}", None))
        con.executemany("INSERT OR REPLACE INTO x_regime VALUES(?,?,?,?,?)", out)
        con.commit()
        run_.rows = len(out)


def _spread(dates, gap_days):
    """Keep the first date of each cluster, so one crisis does not count as many separate events."""
    out, last = [], None
    for d in sorted(dates):
        if last is None or (d - last).days >= gap_days:
            out.append(d)
            last = d
    return out


def _series(con, sid):
    df = pd.read_sql_query("SELECT date, value FROM ts_obs WHERE series_id=? ORDER BY date", con, params=(sid,), parse_dates=["date"])
    return df.set_index("date")["value"]


def _add(con, date, family, title, country=None, magnitude=None, url=None, origin=None):
    con.execute(
        "INSERT OR IGNORE INTO ev_event(date, family, title, country, magnitude, source_url, origin) VALUES(?,?,?,?,?,?,?)",
        (date, family, title, country, magnitude, url, origin),
    )


def _fed_moves(con):
    upper = pd.concat([_series(con, "fred:DFEDTAR"), _series(con, "fred:DFEDTARU")]).sort_index()
    upper = upper[~upper.index.duplicated(keep="last")]
    change = upper.diff().dropna()
    for d, v in change[change != 0].items():
        bp = round(v * 100)
        if abs(bp) < 5:
            continue
        family = "Fed rate cut" if bp < 0 else "Fed rate hike"
        _add(con, d.date().isoformat(), family, f"Fed {'cuts' if bp < 0 else 'raises'} target rate by {abs(bp)}bp, to {upper[d]:.2f}%",
             "United States", bp, "https://fred.stlouisfed.org/series/DFEDTARU", "Computed from the Fed funds target series")


def _market_shocks(con):
    rules = [
        ("SPX", "S&P 500 one day fall of 4% or more", lambda r: r <= -0.04, 30),
        ("BRENT", "Brent one day rise of 8% or more", lambda r: r >= 0.08, 20),
        ("BRENT", "Brent one day fall of 8% or more", lambda r: r <= -0.08, 20),
        ("XAU/USD", "Gold one day rise of 3.5% or more", lambda r: r >= 0.035, 20),
    ]
    for sym, family, test, gap in rules:
        a = con.execute("SELECT asset_id, name FROM ref_asset WHERE symbol=?", (sym,)).fetchone()
        if not a:
            continue
        px = prices(con, a["asset_id"])["px"]
        r = px.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        for d in _spread(list(r[test(r)].index), gap):
            _add(con, d.date().isoformat(), family, f"{a['name']} moved {r[d]:+.1%} in one day", None, round(float(r[d]) * 100, 2), None, "Computed from daily prices")
    vix = _series(con, "cboe:VIX")
    if len(vix):
        above = vix[(vix >= 40) & (vix.shift(1) < 40)]
        for d in _spread(list(above.index), 60):
            _add(con, d.date().isoformat(), "VIX closes above 40", f"VIX closed at {vix[d]:.1f}", "United States", float(vix[d]), None, "Computed from the Cboe VIX history")


def _from_text(con):
    for family, category, query in TEXT_FAMILIES:
        sql = """SELECT e.date, e.text, e.sources FROM fts_doc f JOIN nw_event e ON e.id=f.ref
                 WHERE fts_doc MATCH ? AND f.kind='event'"""
        args = [query]
        if category:
            sql += " AND e.category=?"
            args.append(category)
        hits = con.execute(sql + " ORDER BY e.date", args).fetchall()
        kept = set(_spread([pd.Timestamp(h["date"]) for h in hits], 14))
        for h in hits:
            d = pd.Timestamp(h["date"])
            if d in kept:
                kept.discard(d)
                url = f"https://en.wikipedia.org/wiki/Portal:Current_events/{d.year}_{d.strftime('%B')}_{d.day}"
                _add(con, h["date"], family, h["text"][:220], None, None, url, "Matched in the Wikipedia dated event record")


def events(con):
    with Run(con, "event_library") as run_:
        con.execute("DELETE FROM ev_event")
        for step in (_fed_moves, _market_shocks, _from_text):
            try:
                step(con)
            except Exception as e:
                run_.note(f"{step.__name__}: {e}")
        con.commit()
        run_.rows = con.execute("SELECT count(*) FROM ev_event").fetchone()[0]


def _window(px, base):
    """Returns after the first trading day on or after the event, so news after the close is not missed."""
    i = px.index.searchsorted(base)
    if i >= len(px) or i < 1:
        return None
    p0 = px.iloc[i - 1]
    if not p0:
        return None
    pick = lambda n: float(px.iloc[i - 1 + n] / p0 - 1) if i - 1 + n < len(px) else None
    span = px.iloc[i: i + 20]
    return (px.index[i - 1].date().isoformat(), pick(1), pick(5), pick(20), pick(60),
            float(span.min() / p0 - 1) if len(span) else None, float(span.max() / p0 - 1) if len(span) else None)


def event_returns(con):
    with Run(con, "event_returns") as run_:
        evs = pd.read_sql_query("SELECT event_id, date FROM ev_event", con, parse_dates=["date"])
        con.execute("DELETE FROM x_event_return")
        marks = ",".join("?" * len(STUDY_SYMBOLS))
        for a in con.execute(f"SELECT asset_id FROM ref_asset WHERE symbol IN ({marks})", STUDY_SYMBOLS).fetchall():
            px = prices(con, a["asset_id"])["px"]
            if len(px) < 30:
                continue
            rows = []
            for e in evs.itertuples():
                out = _window(px, e.date)
                if out:
                    rows.append((e.event_id, a["asset_id"], *out))
            con.executemany("INSERT OR REPLACE INTO x_event_return VALUES(?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
            run_.rows += len(rows)


def clean_names(con):
    """Nasdaq's list names carry share class wording, such as Tesla, Inc. Common Stock."""
    tail = re.compile(r"\s+(class [a-c] )?(common stock|common shares|ordinary shares|capital stock|american depositary shares|depositary shares).*$", re.I)
    rows = [(tail.sub("", r["name"]).strip(), r["asset_id"]) for r in con.execute("SELECT asset_id, name FROM ref_asset WHERE name IS NOT NULL") if tail.search(r["name"])]
    con.executemany("UPDATE ref_asset SET name=? WHERE asset_id=?", rows)
    # The S&P table uses plain company names that match Wikipedia titles, so it wins over Nasdaq's wording.
    con.execute("""UPDATE ref_asset SET
        name=(SELECT m.name FROM ref_index_member m WHERE m.index_code='SP500' AND m.symbol=ref_asset.symbol),
        wiki_title=(SELECT m.name FROM ref_index_member m WHERE m.index_code='SP500' AND m.symbol=ref_asset.symbol)
        WHERE symbol IN (SELECT symbol FROM ref_index_member WHERE index_code='SP500')""")
    con.commit()


def views(con):
    con.executescript("""
    CREATE VIEW IF NOT EXISTS v_latest_price AS
      SELECT a.symbol, a.name, a.asset_class, a.currency, m.as_of, m.close, m.r1d, m.r20d, m.ytd, m.vol20
      FROM x_asset_metric m JOIN ref_asset a USING(asset_id);
    CREATE VIEW IF NOT EXISTS v_earnings_date AS
      SELECT symbol, filed AS date, accession FROM co_filing WHERE form='8-K' AND items LIKE '%2.02%';
    CREATE VIEW IF NOT EXISTS v_cot_net AS
      SELECT market_code, market, report_date, noncomm_long-noncomm_short AS speculator_net, comm_long-comm_short AS commercial_net, open_interest
      FROM pos_cot;
    CREATE VIEW IF NOT EXISTS v_event_study AS
      SELECT e.family, e.date, e.title, a.symbol, r.r1, r.r5, r.r20, r.r60, r.worst20, r.best20
      FROM x_event_return r JOIN ev_event e USING(event_id) JOIN ref_asset a USING(asset_id);
    """)
    con.commit()


def fts(con):
    with Run(con, "search_index") as run_:
        con.execute("DELETE FROM fts_doc")
        steps = [
            "INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT coalesce(topic, category, ''), text, 'event', id, date, 'events_wiki' FROM nw_event",
            "INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT title, coalesce(summary, ''), 'article', id, substr(published, 1, 10), dataset_id FROM nw_article",
            "INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT title, coalesce(abstract, '') || ' ' || coalesce(body, ''), 'document', id, date, dataset_id FROM doc_release",
            "INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT name, coalesce(remarks, '') || ' ' || coalesce(program, ''), 'sanction', uid, NULL, 'geo_sanctions' FROM geo_sanction",
            "INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT question, coalesce(event, '') || ' ' || coalesce(category, ''), 'prediction', market_id, snapshot_at, 'geo_predictions' FROM geo_prediction",
            # UK and EU lists: entities and ships only. Named individuals stay out of the index, so they cannot reach the public copy.
            "INSERT INTO fts_doc(title, body, kind, ref, date, dataset) SELECT name, coalesce(regime, '') || ' ' || coalesce(country, ''), 'sanction', ref, listed, CASE list WHEN 'UK' THEN 'geo_sanctions_uk' ELSE 'geo_sanctions_eu' END FROM geo_sanction_list WHERE list IN ('UK','EU') AND kind<>'Individual'",
        ]
        for sql in steps:
            try:
                run_.rows += con.execute(sql).rowcount
            except Exception as e:
                run_.note(str(e))
        con.commit()
        con.execute("INSERT INTO fts_doc(fts_doc) VALUES('optimize')")
        con.commit()


def run(con):
    views(con)
    clean_names(con)
    for step in (flags, metrics, regimes, fts, events, event_returns):
        try:
            step(con)
        except Exception as e:
            print(f"[{step.__name__}] FAILED: {type(e).__name__}: {e}", flush=True)
