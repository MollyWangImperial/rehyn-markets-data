"""The catalogue: every dataset, what it holds, where it came from and what it costs to use.

Labels describe use on Rehyn Markets, which is a paid product. They come from reading each
source's own terms on 5 November 2026. They are a working reading of those terms, not legal advice.
  OPEN        free to reuse commercially, attribution at most
  TERMS       free to read, but commercial display is conditional or unclear
  PERMISSION  the terms bar this use unless the owner agrees in writing
  FEE         a paid licence is needed
"""
import csv

from core import ROOT, Run, now_iso

CATEGORIES = [
    ("markets", "Market prices", "Daily open, high, low, close and volume across equities, ETFs, indices, FX, commodities and crypto.", 1),
    ("companies", "Companies", "Reported financials, the filing record and insider transactions.", 2),
    ("news", "News and narrative", "Headlines, the dated record of world events and official documents.", 3),
    ("macro", "Macro and policy", "Inflation, jobs, growth, rates, money and country indicators.", 4),
    ("geo", "Geopolitics and risk", "Conflict events, sanctions, risk indices and prediction market odds.", 5),
    ("positioning", "Positioning and attention", "Who holds what, short selling, options activity and public attention.", 6),
    ("research", "Research and events", "Factors, long run valuation, the event library and measured reactions.", 7),
    ("reference", "Reference", "Instruments, index members and identifiers.", 8),
    ("licensed", "Not collected", "Paid data we do not hold, and sources that refused access. Listed so the gaps stay visible.", 9),
]

YAHOO_NOTE = "Yahoo's terms bar commercial use and automated collection, and Yahoo sells no licence. Replace with a licensed vendor before any paying user sees this."
YAHOO = dict(source_name="Yahoo Finance", source_url="https://finance.yahoo.com", terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
             tier="PERMISSION", licence="Yahoo terms of service", licence_note=YAHOO_NOTE, cadence="Held")
SEC = dict(source_name="SEC EDGAR", source_url="https://www.sec.gov/edgar", terms_url="https://www.sec.gov/about/privacy-information",
           tier="OPEN", licence="Public information", licence_note="Free to copy and distribute. Limit of 10 requests a second, and the crawler must declare a contact address.",
           attribution="Source: US Securities and Exchange Commission", cadence="Daily")
DERIVED_NOTE = "Computed from Yahoo prices, so it carries the same restriction until the prices are replaced."

D = [
    # Market prices
    dict(id="px_equity_us", category_id="markets", name="US equities, daily", blurb="S&P 500 and Nasdaq-100 members plus US listed ADRs, with dividends and splits.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_equity_us')", date_col="date", **YAHOO),
    dict(id="px_equity_global", category_id="markets", name="Global equities, daily", blurb="FTSE 100 members and major names in Europe and Asia.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_equity_global')", date_col="date", **YAHOO),
    dict(id="px_etf", category_id="markets", name="ETFs, daily", blurb="Broad, sector, country and thematic ETFs.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_etf')", date_col="date", **YAHOO),
    dict(id="px_index", category_id="markets", name="Stock indices, daily", blurb="20 benchmark indices. Index levels also belong to their index providers.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_index')", date_col="date", **YAHOO),
    dict(id="px_commodity_futures", category_id="markets", name="Commodity futures, daily", blurb="Front month energy, metals and agricultural futures.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_commodity_futures')", date_col="date", **YAHOO),
    dict(id="px_fx_yahoo", category_id="markets", name="FX pairs, daily", blurb="Major and emerging market pairs against the dollar.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_fx_yahoo')", date_col="date", **YAHOO),
    dict(id="px_rates_yahoo", category_id="markets", name="Treasury yield indices, daily", blurb="Cboe yield indices, for long history before the Treasury file starts.",
         table_name="px_daily", row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_rates_yahoo')", date_col="date", **YAHOO),
    dict(id="px_crypto", category_id="markets", name="Crypto, daily", blurb="Major coins from Coinbase Exchange public candles.", table_name="px_daily",
         row_filter="asset_id IN (SELECT asset_id FROM ref_asset WHERE price_dataset='px_crypto')", date_col="date",
         source_name="Coinbase Exchange", source_url="https://exchange.coinbase.com", terms_url="https://www.coinbase.com/legal/market_data", tier="PERMISSION", licence="Coinbase Market Data Terms",
         licence_note="Personal or research use only. No end-user apps, and no display of data or derived charts outside your organisation without written consent.", cadence="Held"),
    dict(id="px_actions", category_id="markets", name="Dividends and splits", blurb="Corporate actions behind the adjusted close.", table_name="px_action", date_col="date", **YAHOO),
    dict(id="px_options", category_id="markets", name="Options chains, delayed", blurb="Not collected yet. A daily snapshot would build our own history, starting from the first run.",
         table_name="px_option_chain", date_col="snapshot", source_name="Cboe", source_url="https://www.cboe.com/delayed_quotes/", terms_url="https://www.cboe.com/use-of-content", tier="FEE",
         licence="Signed Cboe licence and an OPRA vendor agreement", licence_note="Both are needed even for delayed data.", price_note="OPRA: $1,500 a month redistribution, plus $1.25 per non-professional user a month.", cadence="Held", status="not_collected"),
    dict(id="fx_ecb", category_id="markets", name="Euro reference rates", blurb="Official daily ECB rates for about 40 currencies since 1999.", table_name="ts_obs",
         row_filter="series_id LIKE 'ecb:%'", date_col="date", source_name="European Central Bank", source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/",
         terms_url="https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html", tier="TERMS", licence="ECB disclaimer and copyright",
         licence_note="Free, but a paid product must tell users, before payment and at each access, that the rates are available free from the ECB.", attribution="Source: European Central Bank. These euro reference rates are available free of charge from the ECB at ecb.europa.eu.", cadence="Daily"),
    dict(id="fx_fed", category_id="markets", name="Dollar exchange rates, daily", blurb="Noon buying rates in New York for 23 currencies against the dollar, from 1971.", table_name="ts_obs",
         row_filter="series_id LIKE 'frbfx:%'", date_col="date", source_name="Federal Reserve Board", source_url="https://www.federalreserve.gov/releases/h10/", terms_url="https://www.federalreserve.gov/disclaimer.htm",
         tier="OPEN", licence="Public domain", licence_note="Board information is public domain unless marked otherwise. Board seals and logos may not be used.", attribution="Source: Federal Reserve Board, H.10 release", cadence="Daily"),
    dict(id="rates_h15", category_id="markets", name="US interest rates, daily", blurb="Treasury constant maturity yields from 1962, the bank prime rate and commercial paper rates.", table_name="ts_obs",
         row_filter="series_id LIKE 'h15:%'", date_col="date", source_name="Federal Reserve Board", source_url="https://www.federalreserve.gov/releases/h15/", terms_url="https://www.federalreserve.gov/disclaimer.htm",
         tier="OPEN", licence="Public domain", licence_note="Board information is public domain unless marked otherwise. Board seals and logos may not be used.", attribution="Source: Federal Reserve Board, H.15 release", cadence="Daily"),
    dict(id="rates_treasury", category_id="markets", name="US Treasury yield curve", blurb="Par yields for every tenor since 1990.", table_name="ts_obs", row_filter="series_id LIKE 'ust:%'", date_col="date",
         source_name="US Treasury", source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates", terms_url="https://www.usa.gov/government-copyright",
         tier="OPEN", licence="US government work", cadence="Daily"),
    dict(id="commodity_eia", category_id="markets", name="Energy spot prices", blurb="Brent, WTI, Henry Hub and refined product spot prices, plus weekly US oil and gas stocks, the Strategic Petroleum Reserve, output, trade and refinery use.", table_name="ts_obs", row_filter="series_id LIKE 'eia:%'", date_col="date",
         source_name="US Energy Information Administration", source_url="https://www.eia.gov/opendata/", terms_url="https://www.eia.gov/about/copyrights_reuse.php", tier="OPEN", licence="Public domain",
         attribution="Source: U.S. Energy Information Administration", cadence="Weekly"),
    dict(id="commodity_worldbank", category_id="markets", name="World Bank commodity prices", blurb="71 monthly commodity series from 1960, the Pink Sheet.", table_name="ts_obs", row_filter="series_id LIKE 'wb:%'", date_col="date",
         source_name="World Bank", source_url="https://www.worldbank.org/en/research/commodity-markets", terms_url="https://data.worldbank.org/summary-terms-of-use", tier="TERMS", licence="CC BY 4.0 by default",
         licence_note="The sources listed include Bloomberg and S&P Global, and third party data may need the provider's consent. Ask commodities@worldbank.org.", attribution="Source: World Bank Commodity Price Data", cadence="Monthly"),

    # Companies
    dict(id="co_financials", category_id="companies", name="Reported financials", blurb="25 line items per company from XBRL. Each figure keeps its first reported value and date, so backtests avoid look-ahead.",
         table_name="co_fact", date_col="period_end", **SEC),
    dict(id="co_filings", category_id="companies", name="Filing index", blurb="Recent filings with form, date, 8-K items and a link to the document.", table_name="co_filing", date_col="filed", **SEC),
    dict(id="co_insider", category_id="companies", name="Insider transactions", blurb="Form 3, 4 and 5 trades by officers and directors, last 12 quarters.", table_name="co_insider_tx", date_col="tx_date", **SEC),

    dict(id="co_holdings", category_id="companies", name="Fund holdings (13F)", blurb="Quarterly long positions of 20 widely followed managers, including Berkshire Hathaway, Bridgewater and Citadel.", table_name="co_fund_holding", date_col="period",
         **{**SEC, "cadence": "Quarterly", "licence_note": "Free to copy and distribute. CUSIP codes are a licensed product, so issuers are stored by name only."}),
    dict(id="ref_sec_tickers", category_id="reference", name="SEC company tickers", blurb="Every SEC registrant with a ticker, its exchange and SEC identifier. Replaces the Nasdaq list.", table_name="ref_sec_ticker", **{**SEC, "cadence": "Daily"}),

    # News
    dict(id="news_rss", category_id="news", name="Publisher headlines", blurb="Headline, short summary and link from publisher feeds, from one collection run.", table_name="nw_article", row_filter="dataset_id='news_rss'", date_col="published",
         source_name="BBC, Guardian, CNBC, MarketWatch and others", source_url="https://www.theguardian.com/help/terms-of-service", terms_url="https://www.theguardian.com/help/terms-of-service", tier="FEE", licence="Publisher copyright",
         licence_note="Guardian needs a paid commercial key. BBC, CNBC, Al Jazeera and Google News need permission. MarketWatch allows linked headlines but bars selling them. NYT, FT, OilPrice and CoinDesk feed terms were not read.",
         price_note="Guardian: price depends on usage. Others not published.", cadence="Held", gap_note="Full article text is not stored."),
    # Headlines the news sentiment step keeps for its own use (theme 'asset', thousands a day for 30 days) stay out of the
    # hosted copy: the site reads their scores from the live_ tables, and copying them would cost Turso writes every day.
    dict(id="news_gdelt", category_id="news", name="Headline archive", blurb="Global headlines by theme from 2017, with source country.", table_name="nw_article", row_filter="dataset_id='news_gdelt' AND coalesce(theme,'')<>'asset'", date_col="published",
         source_name="GDELT Project", source_url="https://www.gdeltproject.org", terms_url="https://www.gdeltproject.org/about.html", tier="OPEN", licence="GDELT terms, unrestricted with citation",
         licence_note="Covers GDELT's records. The headlines themselves remain the publishers' text.", attribution="Source: The GDELT Project, gdeltproject.org", cadence="Daily"),
    dict(id="live_sentiment", category_id="news", name="News sentiment by asset", blurb="Hourly sentiment scores from -1 to +1 for about 650 assets, from the last three days of headlines and event records and the last week of official documents, with counts by label. Thirty days hourly, then daily.", table_name="live_sentiment", date_col="as_of",
         source_name="Rehyn, from GDELT, Wikipedia and US government text", source_url="https://huggingface.co/mrm8488/deberta-v3-ft-financial-news-sentiment-analysis", terms_url="https://www.gdeltproject.org/about.html", tier="OPEN", licence="Derived scores",
         licence_note="Scores computed by Rehyn with an MIT licensed model from hosted datasets only.", cadence="Every 15 minutes"),
    dict(id="live_sentiment_items", category_id="news", name="Scored news items", blurb="Each headline, event sentence or document behind the latest sentiment score, with its probabilities and label.", table_name="live_sentiment_item", date_col="published",
         source_name="GDELT Project, Wikipedia, Federal Reserve Board, Federal Register", source_url="https://www.gdeltproject.org", terms_url="https://www.gdeltproject.org/about.html", tier="TERMS", licence="GDELT terms; Wikipedia text CC BY-SA 4.0; US government works",
         licence_note="Headlines remain the publishers' text and are shown with a link. Wikipedia text needs a link and licence notice.", attribution="Sources: The GDELT Project; Wikipedia, CC BY-SA 4.0; Federal Reserve Board; Federal Register", cadence="Every 15 minutes"),
    dict(id="geo_gdelt_events", category_id="geo", name="GDELT event records", blurb="Events from GDELT's 15 minute files that bear on a tracked asset, with actors, place, conflict and cooperation score, mentions and a sentence built from the codes by rule. Thirty days.", table_name="geo_gdelt_event", date_col="added",
         source_name="GDELT Project", source_url="https://www.gdeltproject.org", terms_url="https://www.gdeltproject.org/about.html", tier="OPEN", licence="GDELT terms, unrestricted with citation",
         attribution="Source: The GDELT Project, gdeltproject.org", cadence="Every 15 minutes"),
    dict(id="events_wiki", category_id="news", name="Dated world events", blurb="Sourced daily summaries of world events, in categories, from 2002.", table_name="nw_event", date_col="date",
         source_name="Wikipedia", source_url="https://en.wikipedia.org/wiki/Portal:Current_events", terms_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use", tier="TERMS", licence="CC BY-SA 4.0",
         licence_note="Commercial use is allowed, but it needs a link and licence notice, and modified text must stay under the same licence.", attribution="Text from Wikipedia, CC BY-SA 4.0", cadence="Daily"),
    dict(id="docs_fed", category_id="news", name="Federal Reserve releases", blurb="Press releases, with monetary policy statements in full.", table_name="doc_release", row_filter="dataset_id='docs_fed'", date_col="date",
         source_name="Federal Reserve Board", source_url="https://www.federalreserve.gov/newsevents.htm", terms_url="https://www.federalreserve.gov/disclaimer.htm", tier="OPEN", licence="Public domain", attribution="Source: Federal Reserve Board", cadence="Daily"),
    dict(id="docs_central_banks", category_id="news", name="ECB and Bank of England releases", blurb="Latest press items from each bank, from one collection run.", table_name="doc_release", row_filter="dataset_id='docs_central_banks'", date_col="date",
         source_name="ECB, Bank of England", source_url="https://www.bankofengland.co.uk/news", terms_url="https://www.bankofengland.co.uk/legal", tier="PERMISSION", licence="Bank of England site terms",
         licence_note="Bank of England site content is for personal or internal non-commercial use. ECB items carry the same notice duty as the euro rates.", cadence="Held"),
    dict(id="docs_federal_register", category_id="news", name="US policy documents", blurb="Executive orders, proclamations, tariff, export control and sanctions notices since 1994.", table_name="doc_release", row_filter="dataset_id='docs_federal_register'", date_col="date",
         source_name="Federal Register", source_url="https://www.federalregister.gov", terms_url="https://www.federalregister.gov/reader-aids/developer-resources/rest-api", tier="OPEN", licence="US government work", licence_note="Official logos and seals may not be used.", cadence="Daily"),

    # Macro
    dict(id="macro_us", category_id="macro", name="US economy", blurb="Inflation, labour, growth, housing, credit, money and policy rates.", table_name="ts_obs", row_filter="series_id LIKE 'fred:%'", date_col="date",
         source_name="FRED, St. Louis Fed", source_url="https://fred.stlouisfed.org", terms_url="https://fred.stlouisfed.org/legal/", tier="PERMISSION", licence="FRED terms",
         licence_note="Commercial use and website display need the Bank's written consent, and replicating FRED is banned. Most series can be taken direct from BLS, BEA and the Fed instead.", cadence="Held",
         gap_note="Now replaced from primary sources: CPI, jobs, rates, spreads, breakevens, money, Fed balance sheet, dollar index, industrial production, debt, deficit and mortgage rates. Not yet replaced: GDP and PCE (free BEA key needed), retail sales and housing starts (free Census key needed), jobless claims, the recession indicator, and third party series from S&P, ICE BofA, the University of Michigan and the Chicago and St. Louis Feds."),
    dict(id="macro_fed", category_id="macro", name="Federal Reserve statistics", blurb="Effective fed funds rate, money supply, the Fed balance sheet, dollar indices and industrial production, direct from the Board.", table_name="ts_obs", row_filter="series_id LIKE 'frb:%'", date_col="date",
         source_name="Federal Reserve Board", source_url="https://www.federalreserve.gov/datadownload/", terms_url="https://www.federalreserve.gov/disclaimer.htm", tier="OPEN", licence="Public domain",
         licence_note="Board information is public domain unless marked otherwise. Board seals and logos may not be used.", attribution="Source: Federal Reserve Board", cadence="Daily to monthly"),
    dict(id="fiscal_us", category_id="macro", name="US public debt and deficit", blurb="Daily public debt since 1993 and the monthly federal deficit since 2015.", table_name="ts_obs", row_filter="series_id LIKE 'fiscal:%'", date_col="date",
         source_name="US Treasury Fiscal Data", source_url="https://fiscaldata.treasury.gov", terms_url="https://fiscaldata.treasury.gov/about-us/", tier="OPEN", licence="Open for commercial use",
         licence_note="The site states the data can be copied, adapted and redistributed for commercial purposes.", attribution="Source: US Treasury Fiscal Data", cadence="Daily"),
    dict(id="tic_holders", category_id="macro", name="Foreign holders of US Treasuries", blurb="Monthly Treasury holdings of the largest foreign holders, including Japan, China and the oil exporters, from 2000.", table_name="ts_obs",
         row_filter="series_id LIKE 'tic:%'", date_col="date", source_name="US Treasury TIC system", source_url="https://home.treasury.gov/data/treasury-international-capital-tic-system", terms_url="https://www.usa.gov/government-copyright",
         tier="OPEN", licence="US government work", attribution="Source: US Treasury, Treasury International Capital System", cadence="Monthly"),
    dict(id="energy_world", category_id="macro", name="World energy by country", blurb="Oil, gas and coal production and consumption by country, monthly crude output, and which countries buy crude from which.", table_name="ts_obs",
         row_filter="series_id LIKE 'eiaw:%'", date_col="date", source_name="US Energy Information Administration", source_url="https://www.eia.gov/international/data/world", terms_url="https://www.eia.gov/about/copyrights_reuse.php",
         tier="OPEN", licence="Public domain", licence_note="Only series whose copyright field is empty are collected.", attribution="Source: U.S. Energy Information Administration, International Energy Statistics", cadence="Monthly"),
    dict(id="crops_usda", category_id="macro", name="World crop supply and demand", blurb="Production, exports, imports, consumption and stocks of coffee, cocoa, wheat, corn, soybeans, rice, sugar, cotton, palm oil and barley by country.", table_name="ts_obs",
         row_filter="series_id LIKE 'psd:%'", date_col="date", source_name="USDA Foreign Agricultural Service", source_url="https://apps.fas.usda.gov/psdonline/", terms_url="https://www.usda.gov/about-usda/policies-and-links",
         tier="OPEN", licence="US government work", attribution="Source: USDA Foreign Agricultural Service, Production, Supply and Distribution database", cadence="Monthly"),
    dict(id="supply_gscpi", category_id="macro", name="Global supply chain pressure", blurb="The New York Fed's index of global supply chain stress, monthly from 1998, built from shipping costs and manufacturing surveys.", table_name="ts_obs",
         row_filter="series_id LIKE 'nyfed:%'", date_col="date", source_name="Federal Reserve Bank of New York", source_url="https://www.newyorkfed.org/research/policy/gscpi", terms_url="https://www.newyorkfed.org/privacy/termsofuse",
         tier="TERMS", licence="New York Fed terms of use", licence_note="Business use is allowed with credit, provided nothing implies the New York Fed endorses the product.",
         attribution="Source: Federal Reserve Bank of New York, Global Supply Chain Pressure Index", cadence="Monthly"),
    dict(id="macro_eurostat", category_id="macro", name="Euro area and EU economies", blurb="Inflation (headline, core, energy and services), unemployment, GDP growth, industrial production and government debt for the euro area, the EU, every member state and nearby countries, from 2000.",
         table_name="ts_obs", row_filter="series_id LIKE 'estat:%'", date_col="date", source_name="Eurostat", source_url="https://ec.europa.eu/eurostat/web/main/data/database",
         terms_url="https://ec.europa.eu/eurostat/web/main/help/copyright-notice", tier="TERMS", licence="Eurostat copyright notice, Commission Decision 2011/833/EU",
         licence_note="Commercial reuse is allowed with the source acknowledged, but only for EU, EFTA and EU candidate countries, so the collector drops every other country. Data identified as belonging to other sources may not be reused commercially, so the sentiment indicator and the convergence bond yields are not collected.",
         attribution="Source: Eurostat (datasets prc_hicp_minr, une_rt_m, namq_10_gdp, sts_inpr_m, gov_10q_ggdebt)", cadence="Monthly"),
    dict(id="macro_oecd", category_id="macro", name="OECD leading indicators and world rates", blurb="OECD composite leading indicators and business and consumer confidence for the G20 and OECD members, and unemployment, consumer price inflation and 3 month and 10 year interest rates for countries outside the EU, from 2000.",
         table_name="ts_obs", row_filter="series_id LIKE 'oecd:%'", date_col="date", source_name="OECD", source_url="https://data-explorer.oecd.org",
         terms_url="https://www.oecd.org/en/about/terms-conditions.html", tier="TERMS", licence="OECD terms and conditions, CC BY 4.0 for content from July 2024",
         licence_note="OECD data may be copied, adapted and shared for any purpose, including commercial use, with credit to the OECD. The OECD asks users to check each dataset's metadata for third party owners; interest rates and prices come from national sources. The owner read the terms and approved this use on 24 November 2026; each dataset's metadata has not been checked.",
         attribution="Source: OECD Data Explorer (composite leading indicators, financial market statistics, labour force statistics, prices)", cadence="Monthly"),
    dict(id="macro_bis", category_id="macro", name="Central bank rates, credit and house prices", blurb="Policy rates of about 40 central banks from 1990, house prices for about 60 countries, credit to households, companies and governments, credit-to-GDP gaps, effective exchange rates and monthly dollar exchange rates for about 130 currencies.",
         table_name="ts_obs", row_filter="series_id LIKE 'bis:%'", date_col="date", source_name="Bank for International Settlements", source_url="https://data.bis.org",
         terms_url="https://data.bis.org/help/legal", tier="TERMS", licence="BIS terms of use for statistics",
         licence_note="Free with the BIS cited as the source and no suggestion of endorsement, provided including the statistics adds no extra charge for subscribers or other users: they must stay inside the general subscription, never a paid add-on.",
         attribution="Source: BIS (Bank for International Settlements) statistics, data.bis.org", cadence="Monthly"),
    dict(id="rates_nyfed", category_id="macro", name="SOFR and New York Fed reference rates", blurb="Daily SOFR, BGCR, TGCR, EFFR and OBFR with their volumes, and the SOFR averages and index.",
         table_name="ts_obs", row_filter="series_id LIKE 'nyfr:%'", date_col="date", source_name="Federal Reserve Bank of New York", source_url="https://www.newyorkfed.org/markets/reference-rates",
         terms_url="https://www.newyorkfed.org/privacy/termsofuse", tier="TERMS", licence="New York Fed terms of use",
         licence_note="Business use is allowed, but the reference rates must be shown with the New York Fed's notice, passed on under the same terms, and never suggest endorsement.",
         attribution="SOFR, BGCR, TGCR, EFFR and OBFR are subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of these rates by Rehyn Markets, does not sanction or endorse any particular republication, and has no liability for your use. The SOFR Data and BGCR Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC (Solutions), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.", cadence="Daily"),
    dict(id="housing_fhfa", category_id="macro", name="US house prices by state and metro", blurb="Purchase-only house price index, seasonally adjusted: monthly for the US and its nine census divisions, quarterly for every state and the 100 largest metro areas, from 1991.",
         table_name="ts_obs", row_filter="series_id LIKE 'fhfa:%'", date_col="date", source_name="Federal Housing Finance Agency", source_url="https://www.fhfa.gov/data/hpi",
         terms_url="https://www.fhfa.gov/data/hpi", tier="OPEN", licence="US government work",
         licence_note="Free to use. FHFA House Price Index and FHFA HPI are registered trademarks, so the names appear only as the source credit.",
         attribution="Source: FHFA House Price Index® (purchase-only, seasonally adjusted, nominal)", cadence="Monthly"),
    dict(id="trade_census", category_id="macro", name="US trade by partner and product", blurb="US goods imports and exports with every partner country monthly from 2015, and by HS chapter with the 25 largest partners and the EU.",
         table_name="ts_obs", row_filter="series_id LIKE 'ustrade:%'", date_col="date", source_name="US Census Bureau", source_url="https://www.census.gov/foreign-trade/data/",
         terms_url="https://www.census.gov/data/developers/about/terms-of-service.html", tier="OPEN", licence="US government work, Census Data API terms",
         licence_note="Free to use through the API, which needs a free key. The credit line below must be shown, and nothing may suggest the Census Bureau endorses the product.",
         attribution="Source: US Census Bureau, international trade data. This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau.", cadence="Monthly"),
    dict(id="trade_comtrade", category_id="macro", name="World trade by country and product", blurb="Not collected. Bilateral trade between any two countries by product, from UN Comtrade.", source_name="UN Comtrade",
         source_url="https://comtradeplus.un.org", terms_url="https://comtrade.un.org/en/license-agreement", tier="PERMISSION", licence="UN Comtrade usage agreement", status="not_collected",
         licence_note="Redistribution, publication and commercial use need the UN's prior written permission, on free and paid plans alike. Read 23 November 2026."),
    dict(id="energy_agsi", category_id="macro", name="EU gas storage", blurb="Not collected. Daily gas storage levels for the EU and each member state, from GIE AGSI+.", source_name="Gas Infrastructure Europe",
         source_url="https://agsi.gie.eu", terms_url="https://www.gie.eu/privacy-policy", tier="PERMISSION", licence="GIE terms of use", status="not_collected",
         licence_note="Republishing the data on another online service needs GIE's express prior written consent. Read 23 November 2026."),
    dict(id="macro_military", category_id="macro", name="Military spending by country", blurb="Military spending in dollars and as a share of GDP. The figures come from SIPRI through the World Bank.", table_name="ts_obs",
         row_filter="series_id LIKE 'wdi:%:MS.MIL%'", date_col="date", source_name="SIPRI, through the World Bank", source_url="https://www.sipri.org/databases/milex", terms_url="https://www.sipri.org/about/terms-and-conditions",
         tier="FEE", licence="SIPRI terms", licence_note="SIPRI charges a fee, normally a royalty, for commercial use of its data, even when the World Bank republishes it.", cadence="Annual"),
    dict(id="trade_chokepoints", category_id="macro", name="Maritime chokepoint transits", blurb="Not collected. Daily ship transits and cargo through Hormuz, Suez, Bab el-Mandeb, Malacca, Panama and 23 other chokepoints.", source_name="IMF PortWatch",
         source_url="https://portwatch.imf.org", terms_url="https://www.imf.org/external/terms.htm", tier="PERMISSION", licence="IMF copyright and usage", status="not_collected",
         licence_note="Free to copy with credit, but commercial reuse and automated bulk download need the IMF's permission. A collector is written and waits on that permission."),
    dict(id="macro_imf", category_id="macro", name="IMF economic outlook and commodity prices", blurb="Not collected. IMF forecasts of growth, inflation and debt by country, and primary commodity prices.", source_name="International Monetary Fund",
         source_url="https://www.imf.org/en/Publications/WEO", terms_url="https://www.imf.org/external/terms.htm", tier="PERMISSION", licence="IMF copyright and usage", status="not_collected",
         licence_note="Commercial reuse needs the IMF's permission, and its data API refused automated access."),
    dict(id="rates_pmms", category_id="macro", name="US mortgage rates", blurb="Weekly 30 and 15 year fixed mortgage rates from 1971.", table_name="ts_obs", row_filter="series_id LIKE 'pmms:%'", date_col="date",
         source_name="Freddie Mac", source_url="https://www.freddiemac.com/pmms", terms_url="https://www.freddiemac.com/pmms", tier="TERMS", licence="Use with attribution",
         licence_note="The survey page says its information may be used with proper attribution. Freddie Mac's wider site terms could not be read.", attribution="Source: Freddie Mac Primary Mortgage Market Survey", cadence="Weekly"),
    dict(id="macro_bls", category_id="macro", name="US prices and jobs", blurb="CPI and its energy, food, shelter and services parts, PPI, import and export prices, unemployment, payrolls, earnings and job openings, direct from the agency. Replaces FRED for these series.", table_name="ts_obs", row_filter="series_id LIKE 'bls:%'", date_col="date",
         source_name="US Bureau of Labor Statistics", source_url="https://www.bls.gov/developers/", terms_url="https://www.usa.gov/government-copyright", tier="OPEN", licence="US government work",
         licence_note="The BLS site refused automated access to its own terms page, so this rests on the general rule for federal government works.", attribution="Source: US Bureau of Labor Statistics", cadence="Monthly"),
    dict(id="macro_world", category_id="macro", name="World economy", blurb="GDP, inflation, debt, trade, energy and commodity dependence, external debt, reserves and military spending for every country.", table_name="ts_obs", row_filter="series_id LIKE 'wdi:%' AND series_id NOT LIKE 'wdi:%:MS.MIL%'", date_col="date",
         source_name="World Bank", source_url="https://data.worldbank.org", terms_url="https://data.worldbank.org/summary-terms-of-use", tier="OPEN", licence="CC BY 4.0", licence_note="Check each indicator's metadata for exceptions.", attribution="Source: The World Bank", cadence="Annual"),

    # Geopolitics
    dict(id="risk_gpr", category_id="geo", name="Geopolitical Risk index", blurb="Daily and country indices built from newspaper text, back to 1900.", table_name="ts_obs", row_filter="series_id LIKE 'gpr:%'", date_col="date",
         source_name="Caldara and Iacoviello", source_url="https://www.matteoiacoviello.com/gpr.htm", terms_url="https://www.matteoiacoviello.com/gpr.htm", tier="OPEN", licence="CC BY",
         attribution="Caldara and Iacoviello (2022), American Economic Review 112(4), matteoiacoviello.com/gpr.htm", cadence="Weekly"),
    dict(id="risk_epu", category_id="geo", name="Economic Policy Uncertainty", blurb="Daily US news based uncertainty index.", table_name="ts_obs", row_filter="series_id LIKE 'epu:%'", date_col="date",
         source_name="Baker, Bloom and Davis", source_url="https://www.policyuncertainty.com", terms_url="https://www.policyuncertainty.com", tier="OPEN", licence="CC BY 4.0", attribution="Baker, Bloom and Davis, policyuncertainty.com", cadence="Daily"),
    dict(id="geo_conflict", category_id="geo", name="Conflict events", blurb="Georeferenced events with at least five deaths since 1989.", table_name="geo_conflict_event", date_col="date_start",
         source_name="Uppsala Conflict Data Program", source_url="https://ucdp.uu.se", terms_url="https://ucdp.uu.se/downloads/", tier="OPEN", licence="CC BY 4.0", attribution="Source: UCDP GED, cite the publications listed with the dataset", cadence="Annual"),
    dict(id="geo_sanctions", category_id="geo", name="US sanctions list", blurb="OFAC Specially Designated Nationals, with programme and remarks.", table_name="geo_sanction",
         source_name="US Treasury OFAC", source_url="https://ofac.treasury.gov/sanctions-list-service", terms_url="https://www.usa.gov/government-copyright", tier="OPEN", licence="US government work", cadence="Daily"),
    dict(id="geo_quakes", category_id="geo", name="Earthquakes", blurb="Every earthquake of magnitude 5.5 or more worldwide since 1970, with place, depth and tsunami flag.", table_name="geo_quake", date_col="time",
         source_name="US Geological Survey", source_url="https://earthquake.usgs.gov/fdsnws/event/1/", terms_url="https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits", tier="OPEN", licence="US government work",
         attribution="Source: U.S. Geological Survey", cadence="Daily"),
    dict(id="climate_enso", category_id="geo", name="El Nino and La Nina index", blurb="The Oceanic Nino Index from 1950. El Nino and La Nina shift harvests, energy demand and shipping.", table_name="ts_obs", row_filter="series_id LIKE 'noaa:%'", date_col="date",
         source_name="NOAA Climate Prediction Center", source_url="https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php", terms_url="https://www.weather.gov/disclaimer", tier="OPEN", licence="US government work",
         attribution="Source: NOAA Climate Prediction Center", cadence="Monthly"),
    dict(id="gov_wgi", category_id="geo", name="Governance indicators", blurb="Political stability, government effectiveness, rule of law, corruption and two more measures for over 200 countries since 1996.", table_name="ts_obs", row_filter="series_id LIKE 'wgi:%'", date_col="date",
         source_name="World Bank Worldwide Governance Indicators", source_url="https://www.worldbank.org/en/publication/worldwide-governance-indicators", terms_url="https://data.worldbank.org/summary-terms-of-use", tier="OPEN", licence="CC BY 4.0",
         attribution="Source: Worldwide Governance Indicators, World Bank", cadence="Annual"),
    dict(id="geo_sanctions_uk", category_id="geo", name="UK sanctions list", blurb="Entities and ships designated under every UK sanctions regime, with regime and date. Named individuals are kept off this site.", table_name="geo_sanction_list",
         row_filter="list='UK' AND kind<>'Individual'", date_col="listed", source_name="UK Foreign, Commonwealth and Development Office", source_url="https://www.gov.uk/government/publications/the-uk-sanctions-list",
         terms_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/", tier="TERMS", licence="Open Government Licence v3.0",
         licence_note="Free for commercial use with the attribution statement. The licence does not cover personal data, so entries for named individuals are not shown publicly.",
         attribution="Contains public sector information licensed under the Open Government Licence v3.0. Source: UK Sanctions List, FCDO.", cadence="Daily"),
    dict(id="geo_sanctions_eu", category_id="geo", name="EU financial sanctions list", blurb="Entities subject to EU financial sanctions, with programme and listing date. Named individuals are kept off this site.", table_name="geo_sanction_list",
         row_filter="list='EU' AND kind<>'Individual'", date_col="listed", source_name="European Commission", source_url="https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions",
         terms_url="https://commission.europa.eu/legal-notice_en", tier="OPEN", licence="Commission reuse notice, Decision 2011/833/EU",
         licence_note="Reuse is allowed with credit and an indication of changes. Entries for identifiable private individuals may need further rights, so they are not shown publicly.",
         attribution="Source: European Commission, consolidated list of persons, groups and entities subject to EU financial sanctions.", cadence="Daily"),
    dict(id="geo_sanctions_un", category_id="geo", name="UN Security Council sanctions list", blurb="Not collected. Individuals and entities under UN Security Council sanctions.", source_name="United Nations", source_url="https://scsanctions.un.org",
         terms_url="https://www.un.org/en/about-us/terms-of-use", tier="PERMISSION", licence="UN terms of use", status="not_collected",
         licence_note="The UN terms allow personal, non-commercial use only. The UK and EU lists carry most UN designations."),
    dict(id="geo_predictions", category_id="geo", name="Prediction market odds", blurb="Not collected. Implied odds on elections, policy and world events.", table_name="geo_prediction", date_col="snapshot_at",
         source_name="Polymarket, Kalshi", source_url="https://polymarket.com", terms_url="https://polymarket.com/tos", tier="PERMISSION", licence="Venue terms",
         licence_note="Polymarket bars data access by financial technology companies without a written agreement. Kalshi limits its API to a member's own trading.", cadence="Held", status="not_collected"),

    # Positioning
    dict(id="pos_cot", category_id="positioning", name="Futures positioning", blurb="Weekly speculator and commercial positions in 26 markets.", table_name="pos_cot", date_col="report_date",
         source_name="CFTC", source_url="https://www.cftc.gov/MarketReports/CommitmentsofTraders/", terms_url="https://www.cftc.gov/WebPolicy/index.htm", tier="OPEN", licence="Public domain", attribution="Source: CFTC Commitments of Traders", cadence="Weekly"),
    dict(id="pos_short", category_id="positioning", name="Daily short volume", blurb="Short sale volume by stock, from one partial run.", table_name="pos_short_volume", date_col="date",
         source_name="FINRA", source_url="https://www.finra.org/finra-data/browse-catalog/short-sale-volume", terms_url="https://www.finra.org/terms-of-use", tier="PERMISSION", licence="FINRA terms of use",
         licence_note="Free for non-commercial use only. The terms ban commercial use, building a database and scraping. FINRA has a permission form.", price_note="Price not published.", cadence="Held"),
    dict(id="attention_wiki", category_id="positioning", name="Public attention", blurb="Daily Wikipedia views for major assets and market topics since 2015.", table_name="ts_obs", row_filter="series_id LIKE 'wiki:%'", date_col="date",
         source_name="Wikimedia", source_url="https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/", terms_url="https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html", tier="OPEN", licence="CC0 1.0", cadence="Daily"),
    dict(id="vol_cboe", category_id="positioning", name="VIX history", blurb="Official daily VIX close since 1990.", table_name="ts_obs", row_filter="series_id LIKE 'cboe:%'", date_col="date",
         source_name="Cboe", source_url="https://www.cboe.com/tradable_products/vix/vix_historical_data/", terms_url="https://www.cboe.com/use-of-content", tier="FEE", licence="Signed Cboe licence",
         licence_note="Any use of Cboe data needs advance approval and a signed licence, even this public file.", price_note="Quote based. Cboe DataShop lists estimates of $1,500 for external distribution, plus per subscriber fees.", cadence="Held"),

    # Research
    dict(id="factors_french", category_id="research", name="Fama-French factors", blurb="Market, size, value, profitability, investment and momentum, daily from 1926.", table_name="ts_obs", row_filter="series_id LIKE 'ff:%'", date_col="date",
         source_name="Kenneth French data library", source_url="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html", terms_url="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html", tier="TERMS",
         licence="Copyright Fama and French", licence_note="No licence is granted, and the factors are built on CRSP data. Ask the authors.", cadence="Monthly"),
    dict(id="valuation_shiller", category_id="research", name="Long run valuation", blurb="S&P price, earnings, dividends and CAPE from 1871.", table_name="ts_obs", row_filter="series_id LIKE 'shiller:%'", date_col="date",
         source_name="Robert Shiller", source_url="https://shillerdata.com", terms_url="https://shillerdata.com", tier="TERMS", licence="No licence stated", licence_note="No commercial grant, and the series use S&P figures.", cadence="Monthly"),
    dict(id="ev_library", category_id="research", name="Event library", blurb="Every Fed move, market shock and event family, each dated and sourced. Computed from the data in this database.", table_name="ev_event", date_col="date",
         source_name="Rehyn, from the sources above", source_url="", terms_url="", tier="TERMS", licence="Derived", licence_note="Some events are computed from Yahoo prices and FRED, and matched text comes from Wikipedia.", cadence="Daily"),
    dict(id="x_event_return", category_id="research", name="Measured event reactions", blurb="What each key asset did 1, 5, 20 and 60 trading days after every event in the library.", table_name="x_event_return",
         source_name="Rehyn, from market prices", source_url="", terms_url="", tier="PERMISSION", licence="Derived", licence_note=DERIVED_NOTE, cadence="Daily"),
    dict(id="x_asset_metric", category_id="research", name="Asset metrics", blurb="Current returns, volatility, drawdown, RSI, beta and best and worst days per asset.", table_name="x_asset_metric", date_col="as_of",
         source_name="Rehyn, from market prices", source_url="", terms_url="", tier="PERMISSION", licence="Derived", licence_note=DERIVED_NOTE, cadence="Daily"),
    dict(id="x_regime", category_id="research", name="Market regimes", blurb="Dated bear markets, hiking and cutting cycles, recessions, oil shocks and election years, for backtests.", table_name="x_regime", date_col="start_date",
         source_name="Rehyn, from market prices and FRED", source_url="", terms_url="", tier="PERMISSION", licence="Derived", licence_note=DERIVED_NOTE, cadence="Daily"),

    # Reference
    dict(id="ref_assets", category_id="reference", name="Instruments", blurb="Every tracked asset with class, currency, sector and SEC identifier.", table_name="ref_asset", source_name="Rehyn, from the sources below", source_url="", terms_url="", tier="TERMS", licence="Derived",
         licence_note="Sector labels are GICS, see index members.", cadence="Held"),
    dict(id="ref_index", category_id="reference", name="Index members", blurb="S&P 500, Nasdaq-100 and FTSE 100 members. Sectors are GICS, as listed on Wikipedia.", table_name="ref_index_member",
         source_name="Wikipedia, Nasdaq", source_url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", terms_url="https://www.msci.com/legal/notice-and-disclaimer", tier="FEE", licence="GICS is owned by MSCI and S&P",
         licence_note="GICS may not be redistributed or used in public materials without permission. The Nasdaq list is personal and non-commercial.", price_note="Price not published.", cadence="Held"),
    dict(id="ref_listings", category_id="reference", name="US listings", blurb="All Nasdaq and NYSE listed symbols, with SEC identifiers where known.", table_name="ref_listing",
         source_name="Nasdaq Trader, SEC", source_url="https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs", terms_url="https://www.nasdaqtrader.com/Trader.aspx?id=CopyDisclaimMain", tier="PERMISSION", licence="Nasdaq site notice",
         licence_note="Personal non-commercial copies only, other use needs consent. SEC ticker files are an open substitute.", cadence="Held"),

    # Paid data we do not hold
    dict(id="lic_prices", category_id="licensed", name="Licensed end of day prices", blurb="The route to replace Yahoo. Needed before paying users see prices.", source_name="Nasdaq, or a licensed vendor", source_url="https://data.nasdaq.com/price-list", tier="FEE", licence="Paid", status="not_collected",
         price_note="Nasdaq Basic: $2,140 a month external distributor, plus $1 per non-professional user. Vendor quotes not yet gathered.", gap_note="From 1 April 2027 delayed and end of day data are planned to carry no fee under the CT Plan, but must still be licensed."),
    dict(id="lic_opra", category_id="licensed", name="Options history and real time", blurb="Full OPRA options feed and historical chains.", source_name="OPRA, via a licensed vendor", source_url="https://www.opraplan.com", tier="FEE", licence="Vendor agreement", status="not_collected",
         price_note="$1,500 a month redistribution, plus $1.25 per non-professional user a month.", gap_note="Only historical data, after the next trading day's open, escapes the redistribution fee."),
    dict(id="lic_tape", category_id="licensed", name="Real time and tick data", blurb="Consolidated US tape, depth of book and tick history.", source_name="CT Plan, from 1 April 2027", source_url="https://consolidatedtape.com/fees", tier="FEE", licence="CT Plan agreements", status="not_collected",
         price_note="Per user: professional $23 to $26 per tape, non-professional $0.90 down to $0.25. Redistributor fee not listed."),
    dict(id="lic_coingecko", category_id="licensed", name="Crypto prices for commercial use", blurb="A licensed replacement for the Coinbase data.", source_name="CoinGecko", source_url="https://www.coingecko.com/en/api/pricing", tier="FEE", licence="Paid plan", status="not_collected",
         price_note="From $35 a month, or $29 billed yearly. Redistribution licence on Enterprise, custom price."),
    dict(id="lic_index", category_id="licensed", name="Official index data", blurb="Constituent weights and index levels for redistribution.", source_name="S&P DJI, MSCI, FTSE Russell", source_url="https://www.spglobal.com/spdji/", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published. S&P terms could not be read."),
    dict(id="lic_gold", category_id="licensed", name="LBMA gold and silver prices", blurb="The official London benchmark. Gold in this database is the COMEX future instead.", source_name="ICE Benchmark Administration", source_url="https://www.ice.com/iba/lbma-gold-silver-price", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published."),
    dict(id="lic_bdi", category_id="licensed", name="Baltic Dry Index", blurb="Shipping rates, relevant to Hormuz and Red Sea scenarios.", source_name="Baltic Exchange", source_url="https://www.balticexchange.com/en/site-services/data-policy.html", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published."),
    dict(id="lic_platts", category_id="licensed", name="Physical commodity assessments", blurb="Dated Brent, LNG and refined product benchmarks.", source_name="S&P Global Platts, Argus", source_url="https://www.argusmedia.com/en/terms-and-conditions", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published. Platts terms could not be read."),
    dict(id="lic_consensus", category_id="licensed", name="Analyst consensus estimates", blurb="Forward earnings estimates and revisions.", source_name="LSEG, FactSet, Visible Alpha", source_url="https://www.lseg.com/en/policies/website-disclaimer", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published.", gap_note="Actual results are covered free by SEC filings."),
    dict(id="lic_ratings", category_id="licensed", name="Credit ratings", blurb="Issuer ratings and rating actions.", source_name="Moody's, S&P, Fitch", source_url="https://www.moodys.com/web/en/us/legal/terms-of-use.html", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published.", gap_note="SEC Rule 17g-7 rating histories are free, delayed 12 to 24 months."),
    dict(id="lic_news", category_id="licensed", name="Full text news", blurb="Article text from wire services and newspapers.", source_name="Reuters, Dow Jones, Bloomberg", source_url="https://www.bloomberg.com/notices/tos/", tier="FEE", licence="Paid", status="not_collected", price_note="Price not published.", gap_note="Headlines and links are collected, full text is not."),
    dict(id="lic_acled", category_id="licensed", name="ACLED conflict data", blurb="Near real time political violence data.", source_name="ACLED", source_url="https://acleddata.com/eula/", tier="FEE", licence="Corporate licence", status="not_collected", price_note="Pricing is confidential.", gap_note="UCDP and GDELT are the open alternatives."),

    dict(id="lic_energy_institute", category_id="licensed", name="Statistical Review of World Energy", blurb="Long run energy production, reserves and consumption by country.", source_name="Energy Institute", source_url="https://www.energyinst.org/statistical-review",
         terms_url="https://www.energyinst.org/terms", tier="PERMISSION", licence="Site terms", status="not_collected", licence_note="The site terms allow private use only. EIA's international data covers much of the same ground for free."),
    dict(id="lic_jodi", category_id="licensed", name="JODI oil and gas data", blurb="Monthly oil and gas production, stocks and demand reported by governments.", source_name="Joint Organisations Data Initiative", source_url="https://www.jodidata.org",
         terms_url="https://www.jodidata.org/terms-of-use.aspx", tier="PERMISSION", licence="JODI terms of use", status="not_collected", licence_note="Downloads are free, but no reuse licence is granted. All rights are reserved."),

    # Tried, then stopped
    dict(id="blocked_stooq", category_id="licensed", name="Stooq price files", blurb="Would have been a second free price source.", source_name="Stooq", source_url="https://stooq.com", tier="TERMS", licence="Terms could not be read", status="blocked", gap_note="Downloads now sit behind a browser check. It was not bypassed."),
    dict(id="blocked_bls", category_id="licensed", name="BLS calendar, Baker Hughes rigs, USDA WASDE", blurb="Three public sources that refuse automated requests.", source_name="BLS, Baker Hughes, USDA", source_url="https://www.bls.gov", tier="TERMS", licence="Access refused", status="blocked", gap_note="Each returned 403. It was not bypassed."),
]

FIELDS = ("id", "category_id", "name", "blurb", "table_name", "row_filter", "date_col", "source_name", "source_url", "terms_url",
          "tier", "licence", "licence_note", "price_note", "attribution", "status", "cadence", "gap_note", "licence_fee", "licence_route", "price_short", "fee_kind", "used_for")

# What the site uses each dataset for. Only data that is hosted is used at all, and one dataset can serve several purposes:
#   scenario   the scenario AI reads it from the Turso database rehyn-markets-public (ai-service tools.py and prompts.py)
#   sentiment  the news sentiment run reads or writes it (s_sentiment.py); its results live in rehyn-sentiment-molly
#   newsfeed   the live news feed, which collects its own headlines and keeps them in rehyn-newsfeed, so no dataset has it yet
#   database   the Database page shows it, from the public edition
SCENARIO_TABLES = {"ts_obs", "co_fact", "co_filing", "co_insider_tx", "co_fund_holding", "pos_cot", "doc_release", "nw_article", "nw_event",
                   "geo_conflict_event", "geo_sanction", "geo_sanction_list", "geo_quake", "ref_sec_ticker"}
SENTIMENT_SETS = {"live_sentiment", "live_sentiment_items", "geo_gdelt_events", "events_wiki", "docs_fed", "docs_federal_register"}


def used_for(d, rows):
    """The purposes of a dataset that is hosted, as public_edition.py decides it. Anything else is not used on the site."""
    fee, route = fee_for(d)
    if fee != "None" or route or d["tier"] not in ("OPEN", "TERMS") or not d.get("table_name") or not rows:
        return None
    uses = [name for name, yes in (("scenario", d["table_name"] in SCENARIO_TABLES), ("sentiment", d["id"] in SENTIMENT_SETS), ("database", True)) if yes]
    return ",".join(uses)

# Licence fee label for use on a paid product. Read with price_note, which holds any published price.
#   Required  money must be paid to use this data, or a paid source must replace it
#   None      no fee is published. Written permission may still be needed (the tier says so), and such data is not hosted
VENDOR = "Replace with end of day prices from a licensed vendor. Yahoo sells no licence, so this data cannot be bought from Yahoo. See Licensed end of day prices."
REBUILD = "Computed from Yahoo prices. Rebuild from licensed prices, which then carries that fee."
ASK = "Ask the owner for written permission and a price."
FEE = {
    **{k: ("Required", VENDOR) for k in ("px_equity_us", "px_equity_global", "px_etf", "px_commodity_futures", "px_fx_yahoo", "px_actions")},
    **{k: ("Required", REBUILD) for k in ("x_event_return", "x_asset_metric", "x_regime")},
    "px_index": ("Required", "Licence levels from the index owners. See Official index data."),
    "px_rates_yahoo": ("Required", "Use the free US Treasury curve and the Fed's H.15 yields from 1962 instead, which removes the fee."),
    "px_fx_yahoo": ("Required", "Use the free Federal Reserve dollar rates for 23 currencies instead, which removes the fee for those pairs."),
    "px_crypto": ("Required", "Replace with a paid crypto data plan. See Crypto prices for commercial use."),
    "ref_assets": ("Required", "Sector labels are GICS. Remove them or license GICS to avoid the fee."),
    "macro_us": ("None", "Ask the St. Louis Fed for written consent, or finish replacing these series from primary sources, which are free."),
    "pos_short": ("Required", "Use FINRA's permission form to ask for terms and a price."),
    "geo_predictions": ("Required", "A written agreement with Polymarket or Kalshi is needed. Prices are not published."),
    "docs_central_banks": ("None", "Ask the Bank of England. ECB items carry no fee."),
    "ref_listings": ("None", "Use the free SEC ticker files instead, or ask Nasdaq."),
    "factors_french": ("None", ASK),
    "valuation_shiller": ("None", ASK),
    "commodity_worldbank": ("None", "Ask commodities@worldbank.org, since some source data belongs to Bloomberg and S&P Global."),
    "ev_library": ("Required", "Depends on Yahoo prices and FRED. Rebuild from licensed or primary data."),
    "blocked_stooq": ("None", "Access is refused and the terms could not be read."),
    "macro_military": ("Required", "Ask SIPRI for a commercial licence, which normally carries a royalty."),
    "trade_chokepoints": ("None", "Email copyright@imf.org to ask permission for commercial reuse of PortWatch data."),
    "macro_imf": ("None", "Email copyright@imf.org to ask permission for commercial reuse."),
    "geo_sanctions_un": ("None", "Ask UN Publications Rights and Permissions."),
    "lic_energy_institute": ("None", "Email statisticalreview@energyinst.org to ask for written permission."),
    "lic_jodi": ("None", "Email jodiinfo@ief.org to ask for reuse terms."),
    "trade_comtrade": ("None", "Ask the Director of the UN Statistics Division for written permission to show Comtrade data in a paid product."),
    "energy_agsi": ("None", "Email gie@gie.eu to ask for written consent to show AGSI+ data on Rehyn Markets."),
}


PRICE_DATE = "Prices read 11 November 2026."
VENDOR_PRICES = ("Display licences: Tiingo Redistribution $250 a month for start-ups or $500 for enterprise; Intrinio Startup from $333 a month, rising to $999; "
                 "Twelve Data Venture $499 a month; Databento Plus $1,500 a month; Massive Stocks Business $2,499 a month. Nasdaq Basic: $2,140 a month as an external distributor, plus $1 per non-professional user.")
# Published prices for licensed data, from each vendor's own pricing page or fee schedule.
PRICE = {
    **{k: VENDOR_PRICES for k in ("lic_prices", "px_equity_us", "px_etf", "px_actions")},
    "px_equity_global": "Global end of day display: Twelve Data Venture $499 a month, with extra approval for non-US prices; EODHD Enterprise £2,499 a month, display terms to confirm. Other vendors quote on request.",
    "px_fx_yahoo": "No fee needed for the main pairs: the Federal Reserve's daily dollar rates are public domain and now in this library.",
    "px_commodity_futures": "CME, per exchange: delayed distribution $21,840 a year, historical $35,220 a year; its $487 a month public website fee only covers sites without registration, so it does not fit a paid site. ICE Brent: redistribution $30,000 a year, with no user fee for delayed data; its $3,000 public display licence excludes paid sites.",
    "px_index": "STOXX distribution €1,560 a month, DAX €568 a month delayed, with no per-user fee for delayed data. S&P Dow Jones, MSCI and FTSE Russell do not publish prices.",
    "lic_index": "STOXX distribution €1,560 a month, DAX €568 a month delayed, with no per-user fee for delayed data. S&P Dow Jones, MSCI and FTSE Russell do not publish prices.",
    "px_crypto": "CoinGecko from $35 a month, display allowed with a Powered by CoinGecko credit. CoinMarketCap commercial plans from $29 to $699 a month, one product, up to 100,000 users.",
    "lic_coingecko": "CoinGecko from $35 a month, display allowed with a Powered by CoinGecko credit. CoinMarketCap commercial plans from $29 to $699 a month, one product, up to 100,000 users.",
    "px_options": "OPRA: $1,500 a month redistribution, waived when only historical data is shown after the next trading day opens; no per-user fee for delayed data. Massive Options Business $1,999 a month.",
    "lic_opra": "OPRA: $1,500 a month redistribution, waived when only historical data is shown after the next trading day opens; no per-user fee for delayed data. Massive Options Business $1,999 a month.",
    "vol_cboe": "Cboe's index fee schedule (January 2021, possibly superseded): delayed display on an open website $300 a month under 1 million views, plus a $1,900 yearly administration fee. Current pages quote custom prices.",
    "lic_gold": "LBMA Gold Price redistribution: $9,000 a year for prices delayed by 4 hours, or $33,000 a year plus $34 per user a month in real time. Silver: same yearly fees, $29 per user.",
    "macro_us": "No fee. The St. Louis Fed gives written consent free of charge; series owned by third parties need their owners' permission.",
    "pos_short": "Firm access to FINRA's data API is $1,650 a month, and commercial use needs FINRA's permission.",
    "ref_index": "GICS: not published, quote from MSCI or S&P Global.",
    "ref_assets": "GICS: not published, quote from MSCI or S&P Global.",
    "news_rss": "Guardian commercial key priced on usage. NewsAPI Business $449 a month. Benzinga by quote.",
    "lic_news": "Reuters and Dow Jones by quote. NewsAPI Business $449 a month, Advanced $1,749 a month.",
    "lic_bdi": "Not published. A £250 onboarding fee applies.",
    "lic_consensus": "Not published by FactSet, LSEG or Zacks. Estimize sells personal API access at $249 a month; display needs a redistribution licence.",
    "lic_ratings": "Not published. Fitch allows excerpts of up to 50 ratings in a report without an agreement.",
    "macro_military": "Not published. SIPRI assesses each commercial request and normally charges a royalty.",
    "geo_predictions": "No fee published. Both venues need a written agreement first.",
}
FEE_KIND = {"pos_short": "access"}
# The cost in a few words, shown in the fee label on the site. The full detail stays in PRICE.
PRICE_SHORT = {
    **{k: "From $250 a month" for k in ("lic_prices", "px_equity_us", "px_etf", "px_actions", "x_event_return", "x_asset_metric", "x_regime")},
    "px_equity_global": "From $499 a month",
    "px_commodity_futures": "From $21,840 a year",
    "px_index": "From €568 a month", "lic_index": "From €568 a month",
    "px_crypto": "From $29 a month", "lic_coingecko": "From $29 a month",
    "px_options": "$1,500 a month", "lic_opra": "$1,500 a month",
    "vol_cboe": "From $300 a month",
    "lic_gold": "From $9,000 a year",
    "lic_tape": "From $0.25 per user a month",
    "news_rss": "From $449 a month", "lic_news": "From $449 a month",
    "px_fx_yahoo": "Free alternative in library", "px_rates_yahoo": "Free alternative in library",
    "pos_short": "$1,650 a month", "geo_predictions": "On request", "ev_library": "From $250 a month",
}


def fee_for(d):
    if d["id"] in FEE:
        return FEE[d["id"]]
    if d["tier"] == "FEE":
        return "Required", "A paid licence from the source or a licensed vendor."
    return "None", ""


def write_register(con):
    cols = ("licence_fee", "name", "category", "status", "rows", "source_name", "tier", "price_note", "licence_route", "licence_note", "gap_note", "terms_url")
    rank = "CASE d.licence_fee WHEN 'Required' THEN 0 ELSE 1 END"
    rows = con.execute(f"""SELECT d.licence_fee, d.name, c.name category, d.status, d.rows, d.source_name, d.tier, d.price_note, d.licence_route, d.licence_note, d.gap_note, d.terms_url
                           FROM cat_dataset d JOIN cat_category c ON c.id=d.category_id ORDER BY {rank}, d.rows DESC, d.name""").fetchall()
    with open(ROOT / "data" / "licence_register.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows([tuple(r) for r in rows])


def write_sources(con):
    """The systematic source list in ingest/sources.py, with each source's latest run, so the site can show what is collected and when."""
    from sources import SOURCES
    con.execute("""CREATE TABLE IF NOT EXISTS cat_source(
        id TEXT PRIMARY KEY, name TEXT, publisher TEXT, cadence TEXT, status TEXT, tier TEXT, datasets TEXT,
        url TEXT, terms_url TEXT, note TEXT, last_run TEXT, last_status TEXT, last_rows INTEGER)""")
    con.execute("DELETE FROM cat_source")
    for s in SOURCES:
        last = con.execute("SELECT finished_at, status, rows_written FROM cat_run WHERE step=? AND status IN ('ok','failed') ORDER BY run_id DESC LIMIT 1", (s["run"],)).fetchone() if s["run"] else None
        con.execute("INSERT INTO cat_source VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (s["id"], s["name"], s["publisher"], s["cadence"], s["status"], s.get("licence") or None, ",".join(s["datasets"]), s["url"] or None, s["terms"] or None,
                     s.get("note"), last[0] if last else None, last[1] if last else None, last[2] if last else None))


def refresh(con):
    with Run(con, "catalogue") as run_:
        write_sources(con)
        have = {r[1] for r in con.execute("PRAGMA table_info(cat_dataset)")}
        for col in ("licence_fee", "licence_route", "price_short", "fee_kind", "used_for"):
            if col not in have:
                con.execute(f"ALTER TABLE cat_dataset ADD COLUMN {col} TEXT")
        con.executemany("INSERT OR REPLACE INTO cat_category VALUES(?,?,?,?)", CATEGORIES)
        known = {d["id"] for d in D}
        con.execute(f"DELETE FROM cat_dataset WHERE id NOT IN ({','.join('?' * len(known))})", list(known))
        stamp = now_iso()
        for d in D:
            row = {k: d.get(k) for k in FIELDS}
            row["status"] = row["status"] or "live"
            row["licence_fee"], row["licence_route"] = fee_for(d)
            row["price_short"] = PRICE_SHORT.get(d["id"]) or ("On request" if row["licence_fee"] == "Required" else None)
            # A licence fee pays for the right to use or show the data. An access fee pays for a service, such as an API, without a licence.
            row["fee_kind"] = (FEE_KIND.get(d["id"], "licence") if row["licence_fee"] == "Required" else None)
            if d["id"] in PRICE:
                row["price_note"] = f"{PRICE[d['id']]} {PRICE_DATE}"
            rows, first, last = 0, None, None
            table = row["table_name"]
            if table and con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                where = f" WHERE {row['row_filter']}" if row["row_filter"] else ""
                col = row["date_col"]
                pick = f"count(*), min({col}), max({col})" if col else "count(*), NULL, NULL"
                rows, first, last = con.execute(f"SELECT {pick} FROM {table}{where}").fetchone()
            row["used_for"] = used_for(d, rows)
            if not rows and row["status"] == "live":
                row["status"] = "partial"
            con.execute(
                f"""INSERT OR REPLACE INTO cat_dataset({','.join(FIELDS)}, rows, first_date, last_date, refreshed_at)
                    VALUES({','.join('?' * len(FIELDS))},?,?,?,?)""",
                [row[k] for k in FIELDS] + [rows, (first or "")[:10] or None, (last or "")[:10] or None, stamp if rows else None],
            )
            run_.rows += 1
        con.commit()
        write_register(con)
