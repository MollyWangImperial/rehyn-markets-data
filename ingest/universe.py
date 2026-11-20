"""Instruments tracked beyond the index member lists.

Each row is (feed symbol, display symbol, name, asset class, currency, country, wiki title).
The prototype's scenario assets are all in here, so its cards can read real prices.
"""

INDICES = [
    ("^GSPC", "SPX", "S&P 500", "USD", "United States", "S&P 500"),
    ("^DJI", "DJI", "Dow Jones Industrial Average", "USD", "United States", "Dow Jones Industrial Average"),
    ("^IXIC", "IXIC", "Nasdaq Composite", "USD", "United States", "Nasdaq Composite"),
    ("^NDX", "NDX", "Nasdaq 100", "USD", "United States", "Nasdaq-100"),
    ("^RUT", "RUT", "Russell 2000", "USD", "United States", "Russell 2000"),
    ("^VIX", "VIX", "Cboe Volatility Index", "USD", "United States", "VIX"),
    ("^FTSE", "UKX", "FTSE 100", "GBP", "United Kingdom", "FTSE 100 Index"),
    ("^GDAXI", "DAX", "DAX", "EUR", "Germany", "DAX"),
    ("^FCHI", "CAC", "CAC 40", "EUR", "France", "CAC 40"),
    ("^STOXX50E", "SX5E", "Euro Stoxx 50", "EUR", "Eurozone", "EURO STOXX 50"),
    ("^N225", "NKY", "Nikkei 225", "JPY", "Japan", "Nikkei 225"),
    ("^HSI", "HSI", "Hang Seng Index", "HKD", "Hong Kong", "Hang Seng Index"),
    ("000001.SS", "SHCOMP", "Shanghai Composite", "CNY", "China", "SSE Composite Index"),
    ("^BSESN", "SENSEX", "BSE Sensex", "INR", "India", "BSE SENSEX"),
    ("^BVSP", "IBOV", "Bovespa", "BRL", "Brazil", "Índice Bovespa"),
    ("^AXJO", "ASX200", "S&P/ASX 200", "AUD", "Australia", "S&P/ASX 200"),
    ("^KS11", "KOSPI", "KOSPI", "KRW", "South Korea", "KOSPI"),
    ("^TWII", "TAIEX", "Taiwan Weighted Index", "TWD", "Taiwan", "Taiwan Capitalization Weighted Stock Index"),
    ("^GSPTSE", "TSX", "S&P/TSX Composite", "CAD", "Canada", "S&P/TSX Composite Index"),
    ("^MXX", "IPC", "IPC Mexico", "MXN", "Mexico", "Índice de Precios y Cotizaciones"),
]

RATES = [
    ("^IRX", "US3M", "US 13 week T-bill yield", "USD", "United States", None),
    ("^FVX", "US5Y", "US 5 year Treasury yield", "USD", "United States", None),
    ("^TNX", "US10Y", "US 10 year Treasury yield", "USD", "United States", None),
    ("^TYX", "US30Y", "US 30 year Treasury yield", "USD", "United States", None),
]

COMMODITIES = [
    ("BZ=F", "BRENT", "Brent crude", "USD", None, "Brent Crude"),
    ("CL=F", "WTI", "WTI crude", "USD", None, "West Texas Intermediate"),
    ("NG=F", "NATGAS", "Henry Hub natural gas", "USD", None, "Natural gas"),
    ("RB=F", "RBOB", "RBOB gasoline", "USD", None, "Gasoline"),
    ("HO=F", "HEATOIL", "Heating oil", "USD", None, "Heating oil"),
    ("GC=F", "XAU/USD", "Gold", "USD", None, "Gold as an investment"),
    ("SI=F", "XAG/USD", "Silver", "USD", None, "Silver as an investment"),
    ("PL=F", "PLATINUM", "Platinum", "USD", None, "Platinum as an investment"),
    ("PA=F", "PALLADIUM", "Palladium", "USD", None, "Palladium as an investment"),
    ("HG=F", "COPPER", "Copper", "USD", None, "Copper"),
    ("ZC=F", "CORN", "Corn", "USD", None, "Maize"),
    ("ZW=F", "WHEAT", "Wheat", "USD", None, "Wheat"),
    ("ZS=F", "SOY", "Soybeans", "USD", None, "Soybean"),
    ("KC=F", "KC", "Arabica coffee", "USD", None, "Coffee"),
    ("SB=F", "SUGAR", "Sugar", "USD", None, "Sugar"),
    ("CC=F", "COCOA", "Cocoa", "USD", None, "Cocoa bean"),
    ("CT=F", "COTTON", "Cotton", "USD", None, "Cotton"),
    ("LE=F", "CATTLE", "Live cattle", "USD", None, "Cattle"),
]

FX = [
    ("DX-Y.NYB", "DXY", "US Dollar Index", "USD", "United States", "U.S. Dollar Index"),
    ("EURUSD=X", "EUR/USD", "Euro vs US dollar", "USD", "Eurozone", "Euro"),
    ("GBPUSD=X", "GBP/USD", "Pound vs US dollar", "USD", "United Kingdom", "Pound sterling"),
    ("JPY=X", "USD/JPY", "US dollar vs Japanese yen", "JPY", "Japan", "Japanese yen"),
    ("CHF=X", "USD/CHF", "US dollar vs Swiss franc", "CHF", "Switzerland", "Swiss franc"),
    ("AUDUSD=X", "AUD/USD", "Australian dollar vs US dollar", "USD", "Australia", "Australian dollar"),
    ("CAD=X", "USD/CAD", "US dollar vs Canadian dollar", "CAD", "Canada", "Canadian dollar"),
    ("CNY=X", "USD/CNY", "US dollar vs Chinese yuan", "CNY", "China", "Renminbi"),
    ("INR=X", "USD/INR", "US dollar vs Indian rupee", "INR", "India", "Indian rupee"),
    ("BRL=X", "USD/BRL", "US dollar vs Brazilian real", "BRL", "Brazil", "Brazilian real"),
    ("COP=X", "USD/COP", "US dollar vs Colombian peso", "COP", "Colombia", "Colombian peso"),
    ("MXN=X", "USD/MXN", "US dollar vs Mexican peso", "MXN", "Mexico", "Mexican peso"),
    ("ZAR=X", "USD/ZAR", "US dollar vs South African rand", "ZAR", "South Africa", "South African rand"),
    ("TRY=X", "USD/TRY", "US dollar vs Turkish lira", "TRY", "Turkey", "Turkish lira"),
    ("RUB=X", "USD/RUB", "US dollar vs Russian rouble", "RUB", "Russia", "Russian ruble"),
    ("TWD=X", "USD/TWD", "US dollar vs Taiwan dollar", "TWD", "Taiwan", "New Taiwan dollar"),
    ("KRW=X", "USD/KRW", "US dollar vs Korean won", "KRW", "South Korea", "South Korean won"),
]

# Coinbase product, display symbol, name, wiki title
CRYPTO = [
    ("BTC-USD", "BTC/USD", "Bitcoin", "Bitcoin"),
    ("ETH-USD", "ETH/USD", "Ether", "Ethereum"),
    ("SOL-USD", "SOL/USD", "Solana", "Solana (blockchain platform)"),
    ("XRP-USD", "XRP/USD", "XRP", "Ripple Labs"),
    ("LTC-USD", "LTC/USD", "Litecoin", "Litecoin"),
    ("DOGE-USD", "DOGE/USD", "Dogecoin", "Dogecoin"),
    ("ADA-USD", "ADA/USD", "Cardano", "Cardano (blockchain platform)"),
    ("LINK-USD", "LINK/USD", "Chainlink", "Chainlink (blockchain)"),
]

ETFS = [
    ("SPY", "SPDR S&P 500 ETF"), ("QQQ", "Invesco QQQ"), ("IWM", "iShares Russell 2000 ETF"), ("DIA", "SPDR Dow Jones ETF"),
    ("VTI", "Vanguard Total Stock Market ETF"), ("EFA", "iShares MSCI EAFE ETF"), ("EEM", "iShares MSCI Emerging Markets ETF"),
    ("TLT", "iShares 20+ Year Treasury ETF"), ("IEF", "iShares 7-10 Year Treasury ETF"), ("SHY", "iShares 1-3 Year Treasury ETF"),
    ("TIP", "iShares TIPS Bond ETF"), ("LQD", "iShares Investment Grade Corporate ETF"), ("HYG", "iShares High Yield Corporate ETF"),
    ("GLD", "SPDR Gold Shares"), ("SLV", "iShares Silver Trust"), ("USO", "United States Oil Fund"), ("UNG", "United States Natural Gas Fund"),
    ("DBC", "Invesco DB Commodity Index Fund"), ("VNQ", "Vanguard Real Estate ETF"),
    ("XLE", "Energy Select Sector SPDR"), ("XLF", "Financial Select Sector SPDR"), ("XLK", "Technology Select Sector SPDR"),
    ("XLV", "Health Care Select Sector SPDR"), ("XLI", "Industrial Select Sector SPDR"), ("XLP", "Consumer Staples Select Sector SPDR"),
    ("XLY", "Consumer Discretionary Select Sector SPDR"), ("XLU", "Utilities Select Sector SPDR"), ("XLB", "Materials Select Sector SPDR"),
    ("XLRE", "Real Estate Select Sector SPDR"), ("XLC", "Communication Services Select Sector SPDR"),
    ("SMH", "VanEck Semiconductor ETF"), ("SOXX", "iShares Semiconductor ETF"), ("ITA", "iShares US Aerospace & Defense ETF"),
    ("XAR", "SPDR S&P Aerospace & Defense ETF"), ("ARKK", "ARK Innovation ETF"), ("KWEB", "KraneShares China Internet ETF"),
    ("FXI", "iShares China Large-Cap ETF"), ("MCHI", "iShares MSCI China ETF"), ("EWJ", "iShares MSCI Japan ETF"),
    ("EWG", "iShares MSCI Germany ETF"), ("EWU", "iShares MSCI United Kingdom ETF"), ("EWZ", "iShares MSCI Brazil ETF"),
    ("EWT", "iShares MSCI Taiwan ETF"), ("EWY", "iShares MSCI South Korea ETF"), ("INDA", "iShares MSCI India ETF"),
    ("COLO", "Global X MSCI Colombia ETF"), ("EWW", "iShares MSCI Mexico ETF"), ("ICLN", "iShares Global Clean Energy ETF"),
    ("TAN", "Invesco Solar ETF"), ("URA", "Global X Uranium ETF"), ("LIT", "Global X Lithium & Battery Tech ETF"),
    ("COPX", "Global X Copper Miners ETF"), ("GDX", "VanEck Gold Miners ETF"), ("KRE", "SPDR S&P Regional Banking ETF"),
    ("XHB", "SPDR S&P Homebuilders ETF"), ("JETS", "US Global Jets ETF"), ("IBIT", "iShares Bitcoin Trust"),
    ("BOTZ", "Global X Robotics & AI ETF"), ("HACK", "Amplify Cybersecurity ETF"), ("MOO", "VanEck Agribusiness ETF"),
]

# Equities outside the S&P 500 that the prototype or the thematic work needs.
EXTRA_EQUITIES = [
    ("EMBJ", "EMBJ", "Embraer", "USD", "Brazil", "Embraer"),
    ("EC", "EC", "Ecopetrol", "USD", "Colombia", "Ecopetrol"),
    ("CIB", "CIB", "Bancolombia", "USD", "Colombia", "Bancolombia"),
    ("MELI", "MELI", "MercadoLibre", "USD", "Argentina", "Mercado Libre"),
    ("EQNR", "EQNR", "Equinor", "USD", "Norway", "Equinor"),
    ("RYAAY", "RYAAY", "Ryanair", "USD", "Ireland", "Ryanair"),
    ("GFS", "GFS", "GlobalFoundries", "USD", "United States", "GlobalFoundries"),
    ("TSM", "TSM", "TSMC", "USD", "Taiwan", "TSMC"),
    ("BABA", "BABA", "Alibaba", "USD", "China", "Alibaba Group"),
    ("ASML", "ASML", "ASML", "USD", "Netherlands", "ASML Holding"),
    ("SHEL", "SHEL", "Shell", "USD", "United Kingdom", "Shell plc"),
    ("BP", "BP", "BP", "USD", "United Kingdom", "BP"),
    ("TM", "TM", "Toyota", "USD", "Japan", "Toyota"),
    ("SONY", "SONY", "Sony", "USD", "Japan", "Sony"),
    ("NVO", "NVO", "Novo Nordisk", "USD", "Denmark", "Novo Nordisk"),
    ("SAP", "SAP", "SAP", "USD", "Germany", "SAP"),
    ("MSTR", "MSTR", "Strategy", "USD", "United States", "MicroStrategy"),
    ("2330.TW", "2330.TW", "TSMC (Taipei)", "TWD", "Taiwan", "TSMC"),
    ("005930.KS", "005930.KS", "Samsung Electronics", "KRW", "South Korea", "Samsung Electronics"),
    ("7203.T", "7203.T", "Toyota (Tokyo)", "JPY", "Japan", "Toyota"),
    ("0700.HK", "0700.HK", "Tencent", "HKD", "China", "Tencent"),
    ("9988.HK", "9988.HK", "Alibaba (Hong Kong)", "HKD", "China", "Alibaba Group"),
    ("RHM.DE", "RHM.DE", "Rheinmetall", "EUR", "Germany", "Rheinmetall"),
    ("SAF.PA", "SAF.PA", "Safran", "EUR", "France", "Safran"),
    ("MC.PA", "MC.PA", "LVMH", "EUR", "France", "LVMH"),
    ("NESN.SW", "NESN.SW", "Nestlé", "CHF", "Switzerland", "Nestlé"),
]

# Topics whose Wikipedia page views act as a public attention signal.
ATTENTION_TOPICS = [
    "Recession", "Inflation", "Stagflation", "Hyperinflation", "Stock market crash", "Bear market", "Quantitative easing",
    "Federal Reserve", "Interest rate", "Tariff", "Sanctions (law)", "Strait of Hormuz", "Taiwan", "OPEC", "Petroleum",
    "Gold as an investment", "Bitcoin", "Artificial intelligence", "Nvidia", "Semiconductor", "World War III", "Nuclear warfare",
    "Pandemic", "Bank run", "Sovereign default", "Yield curve", "Short squeeze", "NATO", "Russia", "Iran", "Israel",
]
