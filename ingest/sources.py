"""The systematic list of sources: what the daily collector runs, how often, and what each one feeds.

Status
  active     collected on its cadence by ingest/daily.py
  held       terms bar our use, so the step skips itself (see core.restricted)
  blocked    the source refused automated access, and we do not bypass it
  candidate  found but not yet collected: terms to read, or a collector to write

Cadence is the most often a source needs collecting: daily, weekly, monthly, quarterly or annual.
The daily collector skips a source whose last successful run is more recent than its cadence.

To add a source: write its step, add an entry here, add its datasets to catalogue.py, then run
python -I ingest/daily.py --only <id>. New candidates found by the discovery agent go here first with status candidate.
"""

S = dict  # keeps the table readable

SOURCES = [
    # Rates, FX and money
    S(id="treasury_curve", name="US Treasury yield curve", publisher="US Treasury", module="s_series", fn="treasury", run="treasury", cadence="daily", status="active", datasets=["rates_treasury"],
      url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates", terms="https://www.usa.gov/government-copyright", licence="OPEN"),
    S(id="treasury_real", name="Treasury real yields, bills and spreads", publisher="US Treasury", module="s_primary", fn="treasury_curves", run="treasury_curves", cadence="daily", status="active", datasets=["rates_treasury"],
      url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates", terms="https://www.usa.gov/government-copyright", licence="OPEN"),
    S(id="treasury_spreads", name="Curve spreads and breakevens (computed)", publisher="Rehyn, from US Treasury", module="s_primary", fn="treasury_spreads", run="treasury_spreads", cadence="daily", status="active", datasets=["rates_treasury"],
      url="", terms="https://www.usa.gov/government-copyright", licence="OPEN"),
    S(id="fed_board", name="Fed funds, money supply, balance sheet, dollar indices, output", publisher="Federal Reserve Board", module="s_primary", fn="federal_reserve", run="fed_board", cadence="daily", status="active", datasets=["macro_fed"],
      url="https://www.federalreserve.gov/datadownload/", terms="https://www.federalreserve.gov/disclaimer.htm", licence="OPEN"),
    S(id="fed_fx", name="Dollar exchange rates, H.10", publisher="Federal Reserve Board", module="s_world", fn="fed_fx", run="fed_fx", cadence="daily", status="active", datasets=["fx_fed"],
      url="https://www.federalreserve.gov/releases/h10/", terms="https://www.federalreserve.gov/disclaimer.htm", licence="OPEN"),
    S(id="fed_h15", name="Interest rates, H.15", publisher="Federal Reserve Board", module="s_world", fn="fed_rates", run="fed_h15", cadence="daily", status="active", datasets=["rates_h15"],
      url="https://www.federalreserve.gov/releases/h15/", terms="https://www.federalreserve.gov/disclaimer.htm", licence="OPEN"),
    S(id="ecb_fx", name="Euro reference rates", publisher="European Central Bank", module="s_series", fn="ecb_fx", run="ecb_fx", cadence="daily", status="active", datasets=["fx_ecb"],
      url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/", terms="https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html", licence="TERMS"),
    S(id="fiscal", name="US public debt and deficit", publisher="US Treasury Fiscal Data", module="s_primary", fn="fiscal", run="fiscal_data", cadence="daily", status="active", datasets=["fiscal_us"],
      url="https://fiscaldata.treasury.gov", terms="https://fiscaldata.treasury.gov/about-us/", licence="OPEN"),
    S(id="pmms", name="US mortgage rates", publisher="Freddie Mac", module="s_primary", fn="mortgage", run="freddie_pmms", cadence="weekly", status="active", datasets=["rates_pmms"],
      url="https://www.freddiemac.com/pmms", terms="https://www.freddiemac.com/pmms", licence="TERMS"),
    S(id="tic", name="Foreign holders of US Treasuries", publisher="US Treasury TIC", module="s_world", fn="tic", run="treasury_tic", cadence="monthly", status="active", datasets=["tic_holders"],
      url="https://home.treasury.gov/data/treasury-international-capital-tic-system", terms="https://www.usa.gov/government-copyright", licence="OPEN"),

    # Energy and commodities
    S(id="eia", name="Energy spot prices and weekly US oil and gas stocks", publisher="US Energy Information Administration", module="s_series", fn="eia", run="eia", cadence="daily", status="active", datasets=["commodity_eia"],
      url="https://www.eia.gov/petroleum/data.php", terms="https://www.eia.gov/about/copyrights_reuse.php", licence="OPEN"),
    S(id="worldbank_pink", name="World Bank commodity prices (Pink Sheet)", publisher="World Bank", module="s_series", fn="worldbank_pink", run="worldbank_pink", cadence="monthly", status="active", datasets=["commodity_worldbank"],
      url="https://www.worldbank.org/en/research/commodity-markets", terms="https://data.worldbank.org/summary-terms-of-use", licence="TERMS", note="Some underlying prices belong to Bloomberg and S&P Global, so it stays off the public site until the World Bank confirms."),
    S(id="chokepoints", name="Maritime chokepoint transits", publisher="IMF PortWatch", module="s_world", fn="chokepoints", run="imf_portwatch", cadence="daily", status="held", datasets=["trade_chokepoints"],
      url="https://portwatch.imf.org", terms="https://www.imf.org/external/terms.htm", licence="PERMISSION", note="Commercial reuse needs IMF permission (copyright@imf.org). The collector is written and switches on once permission is granted."),

    S(id="eia_world", name="World energy by country", publisher="US Energy Information Administration", module="s_world", fn="eia_world", run="eia_world", cadence="monthly", status="active", datasets=["energy_world"],
      url="https://www.eia.gov/opendata/bulkfiles.php", terms="https://www.eia.gov/about/copyrights_reuse.php", licence="OPEN"),
    S(id="usda_psd", name="World crop supply and demand", publisher="USDA Foreign Agricultural Service", module="s_world", fn="crops", run="usda_psd", cadence="monthly", status="active", datasets=["crops_usda"],
      url="https://apps.fas.usda.gov/psdonline/", terms="https://www.usda.gov/about-usda/policies-and-links", licence="OPEN"),
    S(id="nyfed_gscpi", name="Global supply chain pressure", publisher="Federal Reserve Bank of New York", module="s_world", fn="supply_chain", run="nyfed_gscpi", cadence="monthly", status="active", datasets=["supply_gscpi"],
      url="https://www.newyorkfed.org/research/policy/gscpi", terms="https://www.newyorkfed.org/privacy/termsofuse", licence="TERMS"),

    # Macro
    S(id="bls", name="US prices and jobs", publisher="US Bureau of Labor Statistics", module="s_open", fn="bls", run="bls", cadence="weekly", status="active", datasets=["macro_bls"],
      url="https://www.bls.gov/developers/", terms="https://www.usa.gov/government-copyright", licence="OPEN"),
    S(id="worldbank", name="World economy, every country", publisher="World Bank", module="s_world", fn="world_bank", run="worldbank_all", cadence="monthly", status="active", datasets=["macro_world"],
      url="https://data.worldbank.org", terms="https://data.worldbank.org/summary-terms-of-use", licence="OPEN"),
    S(id="wgi", name="Governance indicators", publisher="World Bank WGI", module="s_world", fn="governance", run="worldbank_wgi", cadence="annual", status="active", datasets=["gov_wgi"],
      url="https://www.worldbank.org/en/publication/worldwide-governance-indicators", terms="https://data.worldbank.org/summary-terms-of-use", licence="OPEN"),
    S(id="fred", name="FRED series", publisher="St. Louis Fed", module="s_series", fn="fred", run="fred", cadence="daily", status="held", datasets=["macro_us"],
      url="https://fred.stlouisfed.org", terms="https://fred.stlouisfed.org/legal/", licence="PERMISSION", note="Held. Most series are now taken from the primary agencies instead."),

    # Companies
    S(id="sec_tickers", name="SEC company tickers", publisher="SEC EDGAR", module="s_world", fn="sec_tickers", run="sec_tickers", cadence="weekly", status="active", datasets=["ref_sec_tickers"], sec=True,
      url="https://www.sec.gov/files/company_tickers_exchange.json", terms="https://www.sec.gov/about/privacy-information", licence="OPEN"),
    S(id="sec_filings", name="Filing index", publisher="SEC EDGAR", module="s_companies", fn="filings", run="sec_filings", cadence="daily", status="active", datasets=["co_filings"], sec=True,
      url="https://www.sec.gov/edgar", terms="https://www.sec.gov/about/privacy-information", licence="OPEN"),
    S(id="sec_facts", name="Reported financials (XBRL)", publisher="SEC EDGAR", module="s_companies", fn="facts", run="sec_facts", cadence="weekly", status="active", datasets=["co_financials"], sec=True,
      url="https://www.sec.gov/edgar", terms="https://www.sec.gov/about/privacy-information", licence="OPEN"),
    S(id="sec_insider", name="Insider transactions", publisher="SEC EDGAR", module="s_companies", fn="insider", run="sec_insider", cadence="weekly", status="active", datasets=["co_insider"], sec=True,
      url="https://www.sec.gov/edgar", terms="https://www.sec.gov/about/privacy-information", licence="OPEN"),
    S(id="sec_13f", name="Fund holdings (13F)", publisher="SEC EDGAR", module="s_open", fn="holdings", run="sec_13f", cadence="monthly", status="active", datasets=["co_holdings"], sec=True,
      url="https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets", terms="https://www.sec.gov/about/privacy-information", licence="OPEN"),

    # News and documents
    S(id="fed_releases", name="Federal Reserve releases", publisher="Federal Reserve Board", module="s_news", fn="fed", run="fed_releases", cadence="daily", status="active", datasets=["docs_fed"],
      url="https://www.federalreserve.gov/newsevents.htm", terms="https://www.federalreserve.gov/disclaimer.htm", licence="OPEN"),
    S(id="federal_register", name="US policy documents", publisher="Federal Register", module="s_news", fn="federal_register", run="federal_register", cadence="daily", status="active", datasets=["docs_federal_register"],
      url="https://www.federalregister.gov", terms="https://www.federalregister.gov/reader-aids/developer-resources/rest-api", licence="OPEN"),
    S(id="gdelt", name="Headline archive", publisher="GDELT Project", module="s_news", fn="gdelt", run="news_gdelt", cadence="daily", status="active", datasets=["news_gdelt"],
      url="https://www.gdeltproject.org", terms="https://www.gdeltproject.org/about.html", licence="OPEN", note="Rate limited, so one run can take hours. It resumes where it stopped."),
    S(id="news_sentiment", name="News sentiment by asset", publisher="Rehyn, from GDELT, Wikipedia and US government text", module="sentiment_job", fn="collector", run="news_sentiment", cadence="daily", status="active",
      datasets=["live_sentiment", "live_sentiment_items", "geo_gdelt_events"],
      url="https://huggingface.co/mrm8488/deberta-v3-ft-financial-news-sentiment-analysis", terms="https://www.gdeltproject.org/about.html", licence="TERMS",
      note="GDELT's raw 15 minute headline, event and mention files, scored by a DeBERTa-v3 model stored in Turso. Meant to run every 15 minutes through ingest/sentiment_job.py; the daily run catches up if it has not."),
    S(id="wiki_events", name="Dated world events", publisher="Wikipedia", module="s_news", fn="wiki_events", run="wiki_events", cadence="daily", status="active", datasets=["events_wiki"],
      url="https://en.wikipedia.org/wiki/Portal:Current_events", terms="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use", licence="TERMS"),
    S(id="news_rss", name="Publisher headlines", publisher="BBC, Guardian, CNBC and others", module="s_news", fn="rss", run="news_rss", cadence="daily", status="held", datasets=["news_rss"],
      url="", terms="https://www.theguardian.com/help/terms-of-service", licence="FEE"),
    S(id="central_bank_rss", name="Bank of England releases", publisher="Bank of England", module="s_news", fn="central_bank_rss", run="central_bank_rss", cadence="daily", status="held", datasets=["docs_central_banks"],
      url="https://www.bankofengland.co.uk/news", terms="https://www.bankofengland.co.uk/legal", licence="PERMISSION"),

    # Geopolitics and hazards
    S(id="ucdp", name="Conflict events", publisher="Uppsala Conflict Data Program", module="s_geo", fn="ucdp", run="ucdp", cadence="annual", status="active", datasets=["geo_conflict"],
      url="https://ucdp.uu.se/downloads/", terms="https://ucdp.uu.se/downloads/", licence="OPEN"),
    S(id="ofac", name="US sanctions list", publisher="US Treasury OFAC", module="s_geo", fn="ofac", run="ofac", cadence="daily", status="active", datasets=["geo_sanctions"],
      url="https://ofac.treasury.gov/sanctions-list-service", terms="https://www.usa.gov/government-copyright", licence="OPEN"),
    S(id="sanctions_un", name="UN Security Council sanctions list", publisher="United Nations", module="s_world", fn="sanctions_un", run="sanctions_un", cadence="daily", status="held", datasets=["geo_sanctions_un"],
      url="https://scsanctions.un.org", terms="https://www.un.org/en/about-us/terms-of-use", licence="PERMISSION", note="The UN terms allow personal, non-commercial use only."),
    S(id="sanctions_uk", name="UK sanctions list", publisher="UK Foreign, Commonwealth and Development Office", module="s_world", fn="sanctions_uk", run="sanctions_uk", cadence="daily", status="active", datasets=["geo_sanctions_uk"],
      url="https://www.gov.uk/government/publications/the-uk-sanctions-list", terms="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/", licence="TERMS", note="Open Government Licence. Named individuals stay off the public site."),
    S(id="sanctions_eu", name="EU financial sanctions list", publisher="European Commission", module="s_world", fn="sanctions_eu", run="sanctions_eu", cadence="daily", status="active", datasets=["geo_sanctions_eu"],
      url="https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions", terms="https://commission.europa.eu/legal-notice_en", licence="OPEN", note="Named individuals stay off the public site."),
    S(id="gpr", name="Geopolitical Risk index", publisher="Caldara and Iacoviello", module="s_series", fn="gpr", run="gpr", cadence="weekly", status="active", datasets=["risk_gpr"],
      url="https://www.matteoiacoviello.com/gpr.htm", terms="https://www.matteoiacoviello.com/gpr.htm", licence="OPEN"),
    S(id="epu", name="Economic Policy Uncertainty", publisher="Baker, Bloom and Davis", module="s_series", fn="epu", run="epu", cadence="daily", status="active", datasets=["risk_epu"],
      url="https://www.policyuncertainty.com", terms="https://www.policyuncertainty.com", licence="OPEN"),
    S(id="quakes", name="Earthquakes", publisher="US Geological Survey", module="s_world", fn="earthquakes", run="usgs_quakes", cadence="daily", status="active", datasets=["geo_quakes"],
      url="https://earthquake.usgs.gov/fdsnws/event/1/", terms="https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits", licence="OPEN"),
    S(id="enso", name="El Nino and La Nina index", publisher="NOAA Climate Prediction Center", module="s_world", fn="enso", run="noaa_enso", cadence="monthly", status="active", datasets=["climate_enso"],
      url="https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php", terms="https://www.weather.gov/disclaimer", licence="OPEN"),
    S(id="polymarket", name="Prediction market odds", publisher="Polymarket", module="s_geo", fn="polymarket", run="polymarket", cadence="daily", status="held", datasets=["geo_predictions"],
      url="https://polymarket.com", terms="https://polymarket.com/tos", licence="PERMISSION"),
    S(id="kalshi", name="Prediction market odds", publisher="Kalshi", module="s_geo", fn="kalshi", run="kalshi", cadence="daily", status="held", datasets=["geo_predictions"],
      url="https://kalshi.com", terms="https://kalshi.com", licence="PERMISSION"),

    # Positioning and attention
    S(id="cftc", name="Futures positioning", publisher="CFTC", module="s_positioning", fn="cot", run="cftc_cot", cadence="weekly", status="active", datasets=["pos_cot"],
      url="https://www.cftc.gov/MarketReports/CommitmentsofTraders/", terms="https://www.cftc.gov/WebPolicy/index.htm", licence="OPEN"),
    S(id="pageviews", name="Public attention", publisher="Wikimedia", module="s_positioning", fn="pageviews", run="wiki_pageviews", cadence="weekly", status="active", datasets=["attention_wiki"],
      url="https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/", terms="https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html", licence="OPEN"),
    S(id="finra_short", name="Daily short volume", publisher="FINRA", module="s_positioning", fn="short_volume", run="finra_short", cadence="daily", status="held", datasets=["pos_short"],
      url="https://www.finra.org/finra-data/browse-catalog/short-sale-volume", terms="https://www.finra.org/terms-of-use", licence="PERMISSION"),
    S(id="cboe_options", name="Options chains", publisher="Cboe", module="s_positioning", fn="options", run="cboe_options", cadence="daily", status="held", datasets=["px_options"],
      url="https://www.cboe.com/delayed_quotes/", terms="https://www.cboe.com/use-of-content", licence="FEE"),
    S(id="cboe_vix", name="VIX history", publisher="Cboe", module="s_series", fn="cboe_vix", run="cboe_vix", cadence="daily", status="held", datasets=["vol_cboe"],
      url="https://www.cboe.com/tradable_products/vix/vix_historical_data/", terms="https://www.cboe.com/use-of-content", licence="FEE"),

    # Research
    S(id="french", name="Fama-French factors", publisher="Kenneth French data library", module="s_series", fn="french", run="french", cadence="monthly", status="active", datasets=["factors_french"],
      url="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html", terms="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html", licence="TERMS", note="Collected for internal research only. Not on the public site."),
    S(id="shiller", name="Long run valuation", publisher="Robert Shiller", module="s_series", fn="shiller", run="shiller", cadence="monthly", status="active", datasets=["valuation_shiller"],
      url="https://shillerdata.com", terms="https://shillerdata.com", licence="TERMS", note="Collected for internal research only. Not on the public site."),

    # Prices held until licensed
    S(id="yahoo", name="Daily market prices", publisher="Yahoo Finance", module="s_prices", fn="yahoo", run="prices_yahoo", cadence="daily", status="held", datasets=["px_equity_us", "px_equity_global", "px_etf", "px_index", "px_commodity_futures", "px_fx_yahoo", "px_rates_yahoo", "px_actions"],
      url="https://finance.yahoo.com", terms="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html", licence="PERMISSION"),
    S(id="coinbase", name="Crypto prices", publisher="Coinbase Exchange", module="s_prices", fn="coinbase", run="prices_crypto", cadence="daily", status="held", datasets=["px_crypto"],
      url="https://exchange.coinbase.com", terms="https://www.coinbase.com/legal/market_data", licence="PERMISSION"),
    S(id="nasdaq_lists", name="Index members and US listings", publisher="Wikipedia, Nasdaq Trader", module="s_reference", fn="run", run="reference", cadence="weekly", status="held", datasets=["ref_index", "ref_listings"],
      url="https://www.nasdaqtrader.com", terms="https://www.nasdaqtrader.com/Trader.aspx?id=CopyDisclaimMain", licence="PERMISSION"),

    # Candidates: terms read, collector still to write. The discovery agent picks these up first.
    S(id="eurostat", name="Euro area and EU statistics", publisher="Eurostat", module="", fn="", run="", cadence="monthly", status="candidate", datasets=[],
      url="https://ec.europa.eu/eurostat/web/main/data/web-services", terms="https://ec.europa.eu/eurostat/web/main/help/copyright-notice", licence="TERMS",
      note="Commercial reuse allowed with credit, but only for EU, EFTA and candidate country data. Wanted: HICP inflation, unemployment, GDP and industrial production by country."),
    S(id="oecd", name="OECD statistics", publisher="OECD", module="", fn="", run="", cadence="monthly", status="candidate", datasets=[],
      url="https://data-explorer.oecd.org", terms="https://www.oecd.org/en/about/terms-conditions.html", licence="TERMS",
      note="Reuse allowed for any purpose with an OECD citation; check each dataset for third party data. Wanted: composite leading indicators, policy rates, unemployment."),
    S(id="bis", name="Central bank policy rates and credit", publisher="Bank for International Settlements", module="", fn="", run="", cadence="monthly", status="candidate", datasets=[],
      url="https://data.bis.org", terms="https://data.bis.org/help/legal", licence="TERMS",
      note="Commercial use allowed with citation, provided the statistics add no extra charge for users. Confirm this fits a subscription before collecting."),
    S(id="boc_bcpi", name="Bank of Canada commodity price index", publisher="Bank of Canada", module="", fn="", run="", cadence="monthly", status="candidate", datasets=[],
      url="https://www.bankofcanada.ca/valet/docs", terms="https://www.bankofcanada.ca/terms/", licence="TERMS",
      note="Reuse allowed with credit and a statement that the data is free from the Bank. Its FX rates are built from LSEG data, so leave them out."),
    S(id="usgs_minerals", name="Mineral production and reserves by country", publisher="US Geological Survey", module="", fn="", run="", cadence="annual", status="candidate", datasets=[],
      url="https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries", terms="https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits", licence="OPEN",
      note="Public domain. The data release page sits behind a bot check, so find a direct file link that does not need one."),
    S(id="ucdp_candidate", name="Recent conflict events (monthly candidate release)", publisher="Uppsala Conflict Data Program", module="", fn="", run="", cadence="monthly", status="candidate", datasets=["geo_conflict"],
      url="https://ucdp.uu.se/downloads/", terms="https://ucdp.uu.se/downloads/", licence="OPEN",
      note="CC BY 4.0, like the annual release. Would carry conflict events past the end of 2024."),
    S(id="nyfed_sofr", name="SOFR and other New York Fed reference rates", publisher="Federal Reserve Bank of New York", module="", fn="", run="", cadence="daily", status="candidate", datasets=[],
      url="https://markets.newyorkfed.org/static/docs/markets-api.html", terms="https://www.newyorkfed.org/privacy/termsofuse", licence="TERMS",
      note="Business use allowed, but reference rates need the New York Fed's set notice and disclaimer shown with them."),
    S(id="fhfa_hpi", name="US house prices by state and metro", publisher="Federal Housing Finance Agency", module="", fn="", run="", cadence="monthly", status="candidate", datasets=[],
      url="https://www.fhfa.gov/data/hpi", terms="https://www.fhfa.gov/data/hpi", licence="OPEN",
      note="US government work. The index names are registered trademarks, so use them only as a source credit."),
    S(id="sipri", name="Military expenditure and arms transfers", publisher="SIPRI", module="", fn="", run="", cadence="annual", status="held", datasets=["macro_military"],
      url="https://www.sipri.org/databases", terms="https://www.sipri.org/about/terms-and-conditions", licence="FEE",
      note="SIPRI charges for commercial use. Its military spending figures arrive through the World Bank and stay off the public site."),

    # Refused automated access, not bypassed
    S(id="stooq", name="Stooq price files", publisher="Stooq", module="", fn="", run="", cadence="daily", status="blocked", datasets=["blocked_stooq"], url="https://stooq.com", terms="", licence="TERMS"),
    S(id="imf_datamapper", name="IMF World Economic Outlook (DataMapper API)", publisher="International Monetary Fund", module="", fn="", run="", cadence="monthly", status="blocked", datasets=["macro_imf"],
      url="https://www.imf.org/external/datamapper/api/", terms="https://www.imf.org/en/About/copyright-and-terms", licence="PERMISSION", note="The API returned 403 to an honest crawler on 11 November 2026, and commercial reuse needs IMF permission. Not bypassed."),
]

# Steps that rebuild derived tables and the catalogue after collection, in order.
AFTER = [("s_derived", "run"), ("verify", "run"), ("catalogue", "refresh")]
CADENCE_DAYS = {"daily": 0.5, "weekly": 6, "monthly": 27, "quarterly": 85, "annual": 360}
