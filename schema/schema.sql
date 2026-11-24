-- Rehyn Markets database.
-- Table prefixes keep the categories apart:
--   cat_  catalogue and licence labels     ref_  instruments and identifiers
--   px_   market prices                    ts_   time series (macro, rates, risk, factors)
--   co_   companies                        nw_   news and narrative
--   doc_  official documents               ev_   historical event library
--   pos_  positioning and attention        geo_  geopolitics
--   x_    derived tables computed from the rest

-- Catalogue ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cat_category(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  blurb TEXT,
  sort INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cat_dataset(
  id TEXT PRIMARY KEY,
  category_id TEXT NOT NULL REFERENCES cat_category(id),
  name TEXT NOT NULL,
  blurb TEXT,
  table_name TEXT,
  row_filter TEXT,            -- SQL predicate selecting this dataset's rows in table_name
  date_col TEXT,
  source_name TEXT,
  source_url TEXT,
  terms_url TEXT,
  tier TEXT NOT NULL CHECK(tier IN ('OPEN','TERMS','PERMISSION','FEE')),
  licence TEXT,
  licence_note TEXT,
  price_note TEXT,
  attribution TEXT,
  status TEXT NOT NULL CHECK(status IN ('live','partial','not_collected','blocked','held')),
  cadence TEXT,
  gap_note TEXT,
  rows INTEGER DEFAULT 0,
  first_date TEXT,
  last_date TEXT,
  refreshed_at TEXT,
  licence_fee TEXT,           -- Required, Possible or None, for use on a paid product
  licence_route TEXT,         -- What has to happen before a paid product can use this data
  used_for TEXT               -- What the site uses it for: scenario, sentiment, newsfeed, database. Empty when the site does not use it
);

CREATE TABLE IF NOT EXISTS cat_run(
  run_id INTEGER PRIMARY KEY,
  step TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT,
  rows_written INTEGER,
  message TEXT
);

-- Instruments --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ref_asset(
  asset_id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL UNIQUE,
  feed_symbol TEXT,
  price_dataset TEXT,
  name TEXT,
  asset_class TEXT,           -- Equity, ETF, Index, FX, Commodity, Crypto, Rates
  exchange TEXT,
  currency TEXT,
  country TEXT,
  sector TEXT,
  industry TEXT,
  cik INTEGER,
  wiki_title TEXT,
  first_price TEXT,
  last_price TEXT
);
CREATE INDEX IF NOT EXISTS ix_asset_cik ON ref_asset(cik);
CREATE INDEX IF NOT EXISTS ix_asset_class ON ref_asset(asset_class);

CREATE TABLE IF NOT EXISTS ref_index_member(
  index_code TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT,
  sector TEXT,
  sub_industry TEXT,
  headquarters TEXT,
  date_added TEXT,
  cik INTEGER,
  PRIMARY KEY(index_code, symbol)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ref_listing(
  symbol TEXT PRIMARY KEY,
  name TEXT,
  exchange TEXT,
  is_etf INTEGER,
  cik INTEGER
) WITHOUT ROWID;

-- Prices -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS px_daily(
  asset_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
  PRIMARY KEY(asset_id, date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_px_date ON px_daily(date);

CREATE TABLE IF NOT EXISTS px_action(
  asset_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  kind TEXT NOT NULL,         -- dividend, split
  value REAL,
  PRIMARY KEY(asset_id, date, kind)
) WITHOUT ROWID;

-- Time series --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ts_series(
  series_id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  title TEXT NOT NULL,
  units TEXT,
  frequency TEXT,
  country TEXT,
  topic TEXT,
  first_date TEXT,
  last_date TEXT,
  rows INTEGER
);
CREATE INDEX IF NOT EXISTS ix_series_dataset ON ts_series(dataset_id);

CREATE TABLE IF NOT EXISTS ts_obs(
  series_id TEXT NOT NULL,
  date TEXT NOT NULL,
  value REAL,
  PRIMARY KEY(series_id, date)
) WITHOUT ROWID;

-- Companies ----------------------------------------------------------------
-- value is the latest reported figure, first_value and first_filed are the
-- figure as originally reported, which keeps backtests free of look-ahead.
CREATE TABLE IF NOT EXISTS co_fact(
  cik INTEGER NOT NULL,
  symbol TEXT,
  concept TEXT NOT NULL,
  unit TEXT,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  fy INTEGER,
  fp TEXT,
  form TEXT,
  value REAL,
  first_value REAL,
  first_filed TEXT,
  last_filed TEXT,
  PRIMARY KEY(cik, concept, period_start, period_end)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_fact_symbol ON co_fact(symbol, concept, period_end);

CREATE TABLE IF NOT EXISTS co_filing(
  accession TEXT PRIMARY KEY,
  cik INTEGER NOT NULL,
  symbol TEXT,
  form TEXT,
  filed TEXT,
  report_date TEXT,
  items TEXT,
  doc TEXT,
  doc_desc TEXT
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_filing_symbol ON co_filing(symbol, filed);
CREATE INDEX IF NOT EXISTS ix_filing_form ON co_filing(form, filed);

CREATE TABLE IF NOT EXISTS co_insider_tx(
  accession TEXT NOT NULL,
  seq INTEGER NOT NULL,
  symbol TEXT,
  issuer TEXT,
  owner TEXT,
  role TEXT,
  filed TEXT,
  tx_date TEXT,
  code TEXT,
  side TEXT,                  -- A acquired, D disposed
  shares REAL,
  price REAL,
  shares_after REAL,
  PRIMARY KEY(accession, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_insider_symbol ON co_insider_tx(symbol, tx_date);

-- News and narrative -------------------------------------------------------
CREATE TABLE IF NOT EXISTS nw_article(
  id INTEGER PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  published TEXT,
  source TEXT,
  feed TEXT,
  title TEXT NOT NULL,
  summary TEXT,
  country TEXT,
  lang TEXT,
  theme TEXT
);
CREATE INDEX IF NOT EXISTS ix_article_date ON nw_article(published);

CREATE TABLE IF NOT EXISTS nw_event(
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  category TEXT,
  topic TEXT,
  text TEXT NOT NULL,
  sources TEXT,               -- JSON list of cited URLs
  links TEXT,                 -- JSON list of linked Wikipedia titles
  UNIQUE(date, text)
);
CREATE INDEX IF NOT EXISTS ix_event_date ON nw_event(date);
CREATE INDEX IF NOT EXISTS ix_event_cat ON nw_event(category);

-- Official documents -------------------------------------------------------
CREATE TABLE IF NOT EXISTS doc_release(
  id INTEGER PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  institution TEXT,
  kind TEXT,
  date TEXT,
  title TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  abstract TEXT,
  body TEXT
);
CREATE INDEX IF NOT EXISTS ix_release_date ON doc_release(date);

-- Historical event library -------------------------------------------------
CREATE TABLE IF NOT EXISTS ev_event(
  event_id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  end_date TEXT,
  family TEXT NOT NULL,
  title TEXT NOT NULL,
  country TEXT,
  magnitude REAL,
  source_url TEXT,
  origin TEXT,
  UNIQUE(family, date, title)
);
CREATE INDEX IF NOT EXISTS ix_ev_family ON ev_event(family, date);

-- Positioning --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pos_cot(
  market_code TEXT NOT NULL,
  market TEXT,
  report_date TEXT NOT NULL,
  open_interest REAL,
  noncomm_long REAL,
  noncomm_short REAL,
  comm_long REAL,
  comm_short REAL,
  nonrept_long REAL,
  nonrept_short REAL,
  PRIMARY KEY(market_code, report_date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS pos_short_volume(
  date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  short_volume REAL,
  short_exempt REAL,
  total_volume REAL,
  PRIMARY KEY(symbol, date)
) WITHOUT ROWID;

-- Geopolitics --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_conflict_event(
  id INTEGER PRIMARY KEY,
  date_start TEXT,
  date_end TEXT,
  country TEXT,
  region TEXT,
  conflict TEXT,
  side_a TEXT,
  side_b TEXT,
  kind TEXT,
  deaths INTEGER,
  latitude REAL,
  longitude REAL
);
CREATE INDEX IF NOT EXISTS ix_conflict_date ON geo_conflict_event(date_start);
CREATE INDEX IF NOT EXISTS ix_conflict_country ON geo_conflict_event(country, date_start);

-- GDELT events that bear on a site asset, from the 15 minute raw event files, with a sentence built from the event
-- codes by rule (no model writes it) and the mentions counted from the raw mention files.
CREATE TABLE IF NOT EXISTS geo_gdelt_event(
  event_id INTEGER PRIMARY KEY,
  added TEXT NOT NULL,        -- UTC time GDELT first saw it
  event_date TEXT,
  actor1 TEXT, actor1_country TEXT,
  actor2 TEXT, actor2_country TEXT,
  event_code TEXT, root_code TEXT,
  quad_class INTEGER,         -- 1 verbal cooperation, 2 material cooperation, 3 verbal conflict, 4 material conflict
  goldstein REAL,             -- -10 conflict to +10 cooperation
  mentions INTEGER,           -- mentions when first seen
  mentions_seen INTEGER DEFAULT 0,   -- further mentions counted from the mention files
  sources INTEGER, articles INTEGER,
  avg_tone REAL,
  place TEXT, place_country TEXT,
  url TEXT,
  sentence TEXT NOT NULL,
  assets TEXT                 -- site asset ids it bears on, comma separated with leading and trailing commas
);
CREATE INDEX IF NOT EXISTS ix_gdelt_event_added ON geo_gdelt_event(added);

-- GDELT's own full text tone for each stored headline, kept for comparison with the model's score.
CREATE TABLE IF NOT EXISTS nw_gdelt_tone(
  url TEXT PRIMARY KEY,
  tone REAL, positive REAL, negative REAL, polarity REAL, words INTEGER
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS geo_sanction(
  uid INTEGER PRIMARY KEY,
  name TEXT,
  kind TEXT,
  program TEXT,
  remarks TEXT
);

CREATE TABLE IF NOT EXISTS geo_prediction(
  venue TEXT NOT NULL,
  market_id TEXT NOT NULL,
  question TEXT,
  event TEXT,
  category TEXT,
  prob_yes REAL,
  volume REAL,
  closes TEXT,
  url TEXT,
  snapshot_at TEXT NOT NULL,
  PRIMARY KEY(venue, market_id, snapshot_at)
) WITHOUT ROWID;

-- Derived ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS x_asset_metric(
  asset_id INTEGER PRIMARY KEY,
  as_of TEXT,
  close REAL,
  r1d REAL, r5d REAL, r20d REAL, r60d REAL, r1y REAL, ytd REAL,
  med20 REAL,                 -- median 20 trading day return, whole history
  vol20 REAL,                 -- annualised realised volatility
  vol1y REAL,
  hi52 REAL, lo52 REAL,
  dd_now REAL,                -- drawdown from all time high
  max_dd REAL,
  max_dd_date TEXT,
  rsi14 REAL,
  avg_vol20 REAL,
  beta_spx REAL,
  best_day REAL, best_day_date TEXT,
  worst_day REAL, worst_day_date TEXT,
  history_years REAL,
  ma200 REAL,
  vol_vs_avg20 REAL           -- latest volume divided by its 20 day average
);

CREATE TABLE IF NOT EXISTS x_regime(
  kind TEXT NOT NULL,         -- Bear market, Hiking cycle, Cutting cycle, Recession, Oil shock, Election year
  start_date TEXT NOT NULL,
  end_date TEXT,
  label TEXT,
  magnitude REAL,
  PRIMARY KEY(kind, start_date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS x_event_return(
  event_id INTEGER NOT NULL,
  asset_id INTEGER NOT NULL,
  base_date TEXT,
  r1 REAL, r5 REAL, r20 REAL, r60 REAL,
  worst20 REAL,
  best20 REAL,
  PRIMARY KEY(event_id, asset_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_xer_asset ON x_event_return(asset_id);

-- News sentiment per asset, scored by a DeBERTa-v3 financial sentiment model from text only: headlines and event
-- records from GDELT's 15 minute files, official documents, and a live search for requested assets. Prices and
-- positioning are not inputs. The live_ tables are sent to Turso by ingest/sentiment_job.py; the daily sync skips them.

-- Which tracked asset each stored headline names.
CREATE TABLE IF NOT EXISTS nw_asset_link(
  url TEXT NOT NULL,
  asset TEXT NOT NULL,
  PRIMARY KEY(asset, url)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_asset_link_url ON nw_asset_link(url);

-- The model's score for each text it has read, so nothing is scored twice. ref is a link or a database reference.
CREATE TABLE IF NOT EXISTS nw_sentiment(
  ref TEXT PRIMARY KEY,
  p_neg REAL, p_neu REAL, p_pos REAL,
  label TEXT,
  model TEXT,
  scored_at TEXT
) WITHOUT ROWID;

-- Hourly readings per asset, kept for 30 days, then one per day. Local only.
CREATE TABLE IF NOT EXISTS live_sentiment(
  asset TEXT NOT NULL,
  as_of TEXT NOT NULL,        -- UTC hour of the reading
  s1 REAL, n1 INTEGER,        -- last 24 hours: weighted mean of positive minus negative probability, -1 to +1, and items
  s7 REAL, n7 INTEGER,        -- last 7 days
  s30 REAL, n30 INTEGER,      -- last 30 days
  PRIMARY KEY(asset, as_of)
) WITHOUT ROWID;

-- The latest reading per asset. This is what the site reads.
CREATE TABLE IF NOT EXISTS live_sentiment_latest(
  asset TEXT PRIMARY KEY,
  as_of TEXT,
  days INTEGER,               -- days of history the readings rest on, up to 30
  s1 REAL, n1 INTEGER, s7 REAL, n7 INTEGER, s30 REAL, n30 INTEGER,
  change REAL,                -- the 24 hour score less the 30 day score
  heat REAL,                  -- items in the last 24 hours over the daily average of the last 30 days
  today REAL, today_n INTEGER,  -- the current UTC day so far, the last point of the daily series
  n_pos INTEGER, n_neu INTEGER, n_neg INTEGER,             -- last 7 days, by label
  n_news INTEGER, n_events INTEGER, n_docs INTEGER, n_web INTEGER,  -- last 7 days, by kind
  model TEXT
) WITHOUT ROWID;

-- One point per asset per completed UTC day: the day's score and items, for the 30 day chart.
CREATE TABLE IF NOT EXISTS live_sentiment_daily(
  asset TEXT NOT NULL,
  date TEXT NOT NULL,
  score REAL,
  n INTEGER,
  PRIMARY KEY(asset, date)
) WITHOUT ROWID;

-- The items behind each asset's latest reading.
CREATE TABLE IF NOT EXISTS live_sentiment_item(
  asset TEXT NOT NULL,
  ref TEXT NOT NULL,          -- link, or a database reference for text without one
  published TEXT,
  origin TEXT,                -- news, event, document or web
  source TEXT,
  text TEXT NOT NULL,         -- the text the model read
  p_neg REAL, p_neu REAL, p_pos REAL,
  label TEXT,
  weight REAL,
  PRIMARY KEY(asset, ref)
) WITHOUT ROWID;   -- no extra index: Turso counts each index entry as a write, and an asset has at most 60 items to sort
DROP INDEX IF EXISTS ix_live_item_date;

-- Assets readers asked for that are not tracked yet. Written by the AI service, read by the job.
CREATE TABLE IF NOT EXISTS live_sentiment_request(
  asset TEXT PRIMARY KEY,
  name TEXT,
  requested_at TEXT,
  status TEXT,                -- pending, running, done or failed
  done_at TEXT,
  progress INTEGER,           -- 0 to 100, shown on the site while the analysis runs
  stage TEXT                  -- what the analysis is doing, shown under the progress bar
) WITHOUT ROWID;

-- One full text index across every text table ------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS fts_doc USING fts5(
  title, body,
  kind UNINDEXED, ref UNINDEXED, date UNINDEXED, dataset UNINDEXED,
  tokenize = 'porter unicode61'
);
