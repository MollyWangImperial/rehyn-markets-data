# Rehyn Markets data library

A local database of real market, company, news, macro and geopolitical data, with a search page in the Rehyn Markets prototype style.

Nothing in the database is simulated. Every row comes from a named public source, and each dataset carries a licence label.

## Run it

Double-click `start.bat`. It opens http://localhost:3040 and keeps the site running while its window stays open.

Or from a terminal:

```bash
pip install -r requirements.txt
python -I server/app.py 3040
```

## Layout

| Path | What it is |
|---|---|
| `data/rehyn_markets.db` | The SQLite database. Not for version control. |
| `schema/schema.sql` | Tables. Prefixes keep the categories apart. |
| `ingest/` | One file per source group. `run.py` runs named steps. |
| `ingest/catalogue.py` | Every dataset with its source, terms link and licence label. |
| `server/engine.py` | Turns a typed question into read-only SQL. |
| `server/app.py` | API and page server. |
| `web/prototype.css` | Verbatim copy of the prototype's stylesheet. Do not edit. |
| `web/library.css`, `web/library.js` | Additions for this page. |
| `tests/questions.py` | 59 real questions through the engine. |
| `tests/status.py` | Row counts and size on disk. |

## Table prefixes

`cat_` catalogue and labels, `ref_` instruments, `px_` prices, `ts_` time series, `co_` companies, `nw_` news, `doc_` official documents, `ev_` event library, `pos_` positioning, `geo_` geopolitics, `x_` derived.

## Licence labels

Labels describe use on a paid product. They come from reading each source's terms on 5 November 2026. They are a working reading, not legal advice.

| Label | Meaning |
|---|---|
| Free to use | Commercial reuse is allowed, with attribution at most |
| Check terms | Free to read, but commercial display is conditional or unclear |
| Permission needed | The terms bar this use unless the owner agrees in writing |
| Licence fee | A paid licence is needed |

## Restricted sources are on hold

Steps for sources whose terms bar this use are decorated with `@restricted` and skip themselves. This covers Yahoo, Coinbase, FRED, Cboe, FINRA, Polymarket, Kalshi, publisher RSS feeds, the Bank of England and Nasdaq lists.

`REHYN_ALLOW_RESTRICTED=1` lifts the hold. Only the project owner should set it, after deciding how to handle those terms.

Data already collected from those sources stays in the database for local building and testing. It must not reach paying users until it is licensed or replaced.

## Licence fee labels

Each dataset carries `licence_fee` and `licence_route` in `cat_dataset`. `catalogue` also writes `data/licence_register.csv`, with the highest cost items first.

| Label | Meaning for a paid product |
|---|---|
| Required | Money must be paid to use this data, or a paid source must replace it |
| Possible | Written permission comes first, and the owner may or may not charge |
| None | No fee, though attribution or other conditions can still apply |

## Hosted full database

The recommended host is Turso, because it runs SQLite files, keeps the search index and fits the free plan. The hosted copy holds restricted data, so it must stay private and must never back a public service.

```bash
python -I ingest/export_hosted.py
python -I ingest/upload_turso.py rehyn-markets-full
```

The export stops if any table count differs from the source. Upload needs `TURSO_ORG` and `TURSO_API_TOKEN` in the environment. It has not yet run against a live account, and the search server still reads the local file.

## Public edition

The Database tab on the public site uses a hosted copy with Free to use datasets only, plus company names and tickers. `REHYN_EDITION=public` turns off anything that needs daily prices and limits each query to 20 seconds.

To update it, run `python -I ingest/public_edition.py <folder>`. It stops if a row from another tier reaches the output. Then copy `public.db.gz`, `server/` and `web/` into `data-library/` in the website repository and push.

## Databases by purpose

Each purpose on the site has its own database. `cat_dataset.used_for` records what every dataset is used for, set in `ingest/catalogue.py` and shown on the Database page. One dataset can serve several purposes; it is never copied into a second database for that.

| Purpose | Database | Written by | Read by |
|---|---|---|---|
| Scenario runs | Turso `rehyn-markets-public` | `ingest/sync_turso.py`, daily | the AI service (`TURSO_DATABASE_URL`) |
| Sentiment | Turso `rehyn-sentiment-molly`: `live_sentiment_*`, `ml_*` | `ingest/sentiment_job.py` every 15 minutes, `ingest/model_store.py` | the AI service (`SENTIMENT_DB_URL`) |
| News feed | Turso `rehyn-newsfeed`: `live_news` | the AI service (`NEWS_DB_URL`) | the AI service |
| Database page | `public.db`, the public edition | `ingest/public_edition.py` | the data library service |
| Private, never on the site | Turso `rehyn-prices-personal` | scripts on the PC only | the local Backtest |

## Refreshing

```bash
python -I ingest/run.py companies news positioning geo series bls primary derived verify catalogue
python -I tests/primary_check.py
```

Run `derived`, `verify` and `catalogue` last, because they read everything else. Held steps are skipped and logged in `cat_run`.

Set `REHYN_USER_AGENT` before crawling. The SEC asks for a company name and contact address in the user agent, and the default has no address.

## News sentiment

News sentiment from −1 to +1 for about 700 assets: every site asset, every equity in `ref_asset`, the main commodities, currencies, indices and crypto (`ingest/news_assets.py`), and any asset a reader requests on the site.

Each run of `ingest/sentiment_job.py`:

1. Catches up on GDELT's raw 15 minute files (`ingest/s_gdelt_raw.py`), at most three days back. These are plain downloads, about 3 MB a batch, and are not throttled like the DOC search API.
   - Knowledge graph: the headline of every article that names a tracked asset, linked to each asset in `nw_asset_link`. GDELT's own full text tone goes to `nw_gdelt_tone` for comparison.
   - Events: events that match an asset's rule (oil producers in conflict for Brent, US–China friction for chip makers, and so on) go to `geo_gdelt_event`, each with a sentence built from its codes by rule, such as "United States imposes embargo, boycott, or sanctions against Iran in Tehran, Iran."
   - Mentions: later mentions of stored events are counted, so widely reported events weigh up to three times a headline.
2. Runs a live GDELT search for requested assets.
3. Scores each new headline and event sentence once with `mrm8488/deberta-v3-ft-financial-news-sentiment-analysis` (DeBERTa-v3 small fine-tuned on the Financial PhraseBank, MIT licence). Scores are kept in `nw_sentiment`.
4. Recomputes the reading of each asset with new items, and of every asset once an hour: the weighted mean of positive minus negative probability over three days, with a 24 hour half-life. Site assets also read Wikipedia's dated events, Federal Reserve releases and Federal Register documents from the last week.
5. Sends only what changed to Turso: `live_sentiment_latest` and `live_sentiment_item`. Requests come from `live_sentiment_request`.
6. Keeps 30 days of headlines, events and hourly readings; older readings keep one per asset per day.

Prices and positioning are not inputs, because the model reads text only.

The model is stored in news sentiment's own Turso database (`ml_model`, `ml_model_part`, 579 MB) and loaded from there into `data/models/`, with each file's SHA-256 checked. `sync_turso.py` skips the `ml_` and `live_` tables.

```bash
python -I ingest/model_store.py status     # what Turso holds
python -I ingest/sentiment_job.py          # one run, sent to Turso
```

Schedule `sentiment_job.py` every 15 minutes with Windows Task Scheduler. The daily collector also runs it as the `news_sentiment` source and catches up anything missed. The site reads `GET /api/ai/sentiment?asset=BTC` on the AI service. Requests through `POST /api/ai/sentiment/request` need `TURSO_WRITE_TOKEN` on the AI service.

## How the search works

The engine is rule based. It reads a question for assets, series, dates and intent, then runs read-only SQL. It does not use a language model. A question it cannot place falls back to full text search. Anything starting with `SELECT` runs directly, read only, capped at 200 rows.

## Known limits

- Prices cover today's index members, so backtests carry survivorship bias: companies that left the index or delisted are missing.
- 143 equity days look like feed errors. They stay in `px_daily`, are listed in `x_price_flag`, and are excluded from statistics.
- Event families matched by keywords in the Wikipedia record can include loose matches.
- Fed moves use the target series, which dates a change when it takes effect. That can be the day after the announcement, so some event windows start one day late.
- Daily oil and gold history starts later than stocks. Monthly World Bank prices go back to 1960.
