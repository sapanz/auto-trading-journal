"""Static NSE tradingsymbol -> sector mapping for the open-positions
sector-allocation pie chart. There's no live instrument-master/sector
feed wired into this app, so this covers the commonly traded F&O and
large/mid-cap names by hand; anything not listed falls under
"Uncategorized" rather than breaking the chart.
"""

SECTOR_MAP = {
    # Banking & Financial Services
    "HDFCBANK": "Banking & Financial Services", "ICICIBANK": "Banking & Financial Services",
    "SBIN": "Banking & Financial Services", "KOTAKBANK": "Banking & Financial Services",
    "AXISBANK": "Banking & Financial Services", "INDUSINDBK": "Banking & Financial Services",
    "BANKBARODA": "Banking & Financial Services", "PNB": "Banking & Financial Services",
    "IDFCFIRSTB": "Banking & Financial Services", "FEDERALBNK": "Banking & Financial Services",
    "AUBANK": "Banking & Financial Services", "BANDHANBNK": "Banking & Financial Services",
    "RBLBANK": "Banking & Financial Services", "YESBANK": "Banking & Financial Services",
    "CANBK": "Banking & Financial Services", "UNIONBANK": "Banking & Financial Services",
    "BAJFINANCE": "Banking & Financial Services", "BAJAJFINSV": "Banking & Financial Services",
    "HDFCLIFE": "Banking & Financial Services", "SBILIFE": "Banking & Financial Services",
    "ICICIPRULI": "Banking & Financial Services", "ICICIGI": "Banking & Financial Services",
    "HDFCAMC": "Banking & Financial Services", "CHOLAFIN": "Banking & Financial Services",
    "MUTHOOTFIN": "Banking & Financial Services", "PFC": "Banking & Financial Services",
    "RECLTD": "Banking & Financial Services", "LICHSGFIN": "Banking & Financial Services",
    "SHRIRAMFIN": "Banking & Financial Services", "LICI": "Banking & Financial Services",
    "SBICARD": "Banking & Financial Services", "PAYTM": "Banking & Financial Services",
    "BSE": "Capital Markets", "MCX": "Capital Markets", "CDSL": "Capital Markets",
    "ANGELONE": "Capital Markets", "IEX": "Capital Markets", "CAMS": "Capital Markets",
    "NUVAMA": "Capital Markets", "360ONE": "Capital Markets",

    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
    "LTIM": "IT", "LTTS": "IT", "MPHASIS": "IT", "PERSISTENT": "IT", "COFORGE": "IT",
    "OFSS": "IT", "KPITTECH": "IT", "TATAELXSI": "IT", "SONATSOFTW": "IT",
    "ZENSARTECH": "IT", "CYIENT": "IT", "BIRLASOFT": "IT",

    # Pharma & Healthcare
    "SUNPHARMA": "Pharma & Healthcare", "DRREDDY": "Pharma & Healthcare",
    "CIPLA": "Pharma & Healthcare", "DIVISLAB": "Pharma & Healthcare",
    "LUPIN": "Pharma & Healthcare", "AUROPHARMA": "Pharma & Healthcare",
    "BIOCON": "Pharma & Healthcare", "ALKEM": "Pharma & Healthcare",
    "TORNTPHARM": "Pharma & Healthcare", "ZYDUSLIFE": "Pharma & Healthcare",
    "GLENMARK": "Pharma & Healthcare", "LAURUSLABS": "Pharma & Healthcare",
    "IPCALAB": "Pharma & Healthcare", "ABBOTINDIA": "Pharma & Healthcare",
    "PFIZER": "Pharma & Healthcare", "GLAXO": "Pharma & Healthcare", "SANOFI": "Pharma & Healthcare",
    "APOLLOHOSP": "Pharma & Healthcare", "FORTIS": "Pharma & Healthcare",
    "MAXHEALTH": "Pharma & Healthcare", "NARAYANA": "Pharma & Healthcare",
    "METROPOLIS": "Pharma & Healthcare", "LALPATHLAB": "Pharma & Healthcare",
    "SYNGENE": "Pharma & Healthcare",

    # Auto & Auto Ancillaries
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto", "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto", "HEROMOTOCO": "Auto", "TVSMOTOR": "Auto", "ASHOKLEY": "Auto",
    "ESCORTS": "Auto", "BHARATFORG": "Auto", "MOTHERSON": "Auto", "BOSCHLTD": "Auto",
    "MRF": "Auto", "APOLLOTYRE": "Auto", "CEATLTD": "Auto", "BALKRISIND": "Auto",
    "EXIDEIND": "Auto", "AMARAJABAT": "Auto",

    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "DABUR": "FMCG", "GODREJCP": "FMCG", "MARICO": "FMCG", "COLPAL": "FMCG",
    "TATACONSUM": "FMCG", "UBL": "FMCG", "VBL": "FMCG", "EMAMILTD": "FMCG",
    "PGHH": "FMCG", "GILLETTE": "FMCG", "JYOTHYLAB": "FMCG", "RADICO": "FMCG",

    # Oil, Gas & Energy / Power
    "RELIANCE": "Oil & Gas", "ONGC": "Oil & Gas", "IOC": "Oil & Gas", "BPCL": "Oil & Gas",
    "HPCL": "Oil & Gas", "GAIL": "Oil & Gas", "PETRONET": "Oil & Gas", "OIL": "Oil & Gas",
    "MGL": "Oil & Gas", "IGL": "Oil & Gas", "ATGL": "Oil & Gas",
    "NTPC": "Power & Utilities", "POWERGRID": "Power & Utilities", "TATAPOWER": "Power & Utilities",
    "TORNTPOWER": "Power & Utilities", "NHPC": "Power & Utilities", "SJVN": "Power & Utilities",
    "CESC": "Power & Utilities", "JSWENERGY": "Power & Utilities", "ADANIGREEN": "Power & Utilities",
    "ADANIENSOL": "Power & Utilities", "ADANIPOWER": "Power & Utilities",

    # Metals & Mining
    "TATASTEEL": "Metals & Mining", "JSWSTEEL": "Metals & Mining", "HINDALCO": "Metals & Mining",
    "VEDANTA": "Metals & Mining", "JINDALSTEL": "Metals & Mining", "SAIL": "Metals & Mining",
    "NMDC": "Metals & Mining", "NATIONALUM": "Metals & Mining", "HINDZINC": "Metals & Mining",
    "MOIL": "Metals & Mining", "APLAPOLLO": "Metals & Mining", "RATNAMANI": "Metals & Mining",
    "WELCORP": "Metals & Mining",

    # Infrastructure, Construction & Defense
    "LT": "Infrastructure & Construction", "ADANIPORTS": "Infrastructure & Construction",
    "GMRINFRA": "Infrastructure & Construction", "IRB": "Infrastructure & Construction",
    "NBCC": "Infrastructure & Construction", "NCC": "Infrastructure & Construction",
    "RVNL": "Infrastructure & Construction", "IRCON": "Infrastructure & Construction",
    "CONCOR": "Infrastructure & Construction", "GRINFRA": "Infrastructure & Construction",
    "KNRCON": "Infrastructure & Construction", "PNC": "Infrastructure & Construction",
    "HFCL": "Telecom", "HAL": "Defense", "BEL": "Defense", "BEML": "Defense",
    "MAZDOCK": "Defense", "COCHINSHIP": "Defense", "GRSE": "Defense", "BDL": "Defense",

    # Cement
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "AMBUJACEM": "Cement", "ACC": "Cement",
    "DALBHARAT": "Cement", "RAMCOCEM": "Cement", "JKCEMENT": "Cement",
    "INDIACEM": "Cement", "HEIDELBERG": "Cement",

    # Telecom
    "BHARTIARTL": "Telecom", "IDEA": "Telecom", "INDUSTOWER": "Telecom",
    "TATACOMM": "Telecom", "RAILTEL": "Telecom",

    # Consumer Durables & Retail
    "TITAN": "Consumer Durables & Retail", "DMART": "Consumer Durables & Retail",
    "TRENT": "Consumer Durables & Retail", "PAGEIND": "Consumer Durables & Retail",
    "BATAINDIA": "Consumer Durables & Retail", "VOLTAS": "Consumer Durables & Retail",
    "HAVELLS": "Consumer Durables & Retail", "CROMPTON": "Consumer Durables & Retail",
    "WHIRLPOOL": "Consumer Durables & Retail", "BLUESTARCO": "Consumer Durables & Retail",
    "DIXON": "Consumer Durables & Retail", "AMBER": "Consumer Durables & Retail",
    "VGUARD": "Consumer Durables & Retail", "RELAXO": "Consumer Durables & Retail",

    # Capital Goods / Industrials
    "SIEMENS": "Capital Goods", "ABB": "Capital Goods", "CUMMINSIND": "Capital Goods",
    "THERMAX": "Capital Goods", "BHEL": "Capital Goods", "SKFINDIA": "Capital Goods",
    "SCHAEFFLER": "Capital Goods", "POLYCAB": "Capital Goods", "KEI": "Capital Goods",
    "FINEORG": "Capital Goods", "CGPOWER": "Capital Goods",

    # Chemicals & Fertilizers
    "PIDILITIND": "Chemicals", "SRF": "Chemicals", "UPL": "Chemicals", "AARTIIND": "Chemicals",
    "DEEPAKNTR": "Chemicals", "NAVINFLUOR": "Chemicals", "TATACHEM": "Chemicals",
    "GNFC": "Chemicals", "GSFC": "Chemicals", "CHAMBLFERT": "Chemicals",
    "COROMANDEL": "Chemicals", "PIIND": "Chemicals", "VINATIORGA": "Chemicals",
    "ATUL": "Chemicals", "BALRAMCHIN": "Chemicals",

    # Realty
    "DLF": "Realty", "GODREJPROP": "Realty", "OBEROIRLTY": "Realty", "PRESTIGE": "Realty",
    "PHOENIXLTD": "Realty", "BRIGADE": "Realty", "SOBHA": "Realty", "SUNTECK": "Realty",
    "MAHLIFE": "Realty",

    # Media & Entertainment
    "ZEEL": "Media & Entertainment", "SUNTV": "Media & Entertainment",
    "PVRINOX": "Media & Entertainment", "NAZARA": "Media & Entertainment",
    "SAREGAMA": "Media & Entertainment", "NETWORK18": "Media & Entertainment",

    # Diversified / New-age internet
    "ADANIENT": "Diversified", "GRASIM": "Diversified",
    "ZOMATO": "New-age / Internet", "NYKAA": "New-age / Internet",
    "POLICYBZR": "New-age / Internet", "DELHIVERY": "New-age / Internet",
    "IRCTC": "New-age / Internet",
}


def sector_for(tradingsymbol: str) -> str:
    return SECTOR_MAP.get((tradingsymbol or "").upper(), "Uncategorized")


def portfolio_breakdown(open_positions):
    """Investment allocation across sectors for currently OPEN positions.
    Groups by invested value (entry_value -- capital currently deployed),
    not P&L: this is about where your open capital sits, not how those
    positions are performing. Returns (sector_rows, total_invested), rows
    sorted by invested value descending with their stocks also sorted
    descending."""
    total_invested = sum(p.entry_value for p in open_positions)
    agg: dict[str, dict] = {}
    for p in open_positions:
        sector = sector_for(p.tradingsymbol)
        d = agg.setdefault(sector, {"invested": 0.0, "stocks": {}})
        d["invested"] += p.entry_value
        d["stocks"][p.tradingsymbol] = d["stocks"].get(p.tradingsymbol, 0.0) + p.entry_value

    rows = []
    for sector, d in agg.items():
        stocks = [
            {
                "symbol": sym,
                "invested": round(val, 2),
                "percent_of_sector": round(val / d["invested"] * 100.0, 1) if d["invested"] else 0.0,
            }
            for sym, val in d["stocks"].items()
        ]
        stocks.sort(key=lambda s: s["invested"], reverse=True)
        rows.append({
            "sector": sector,
            "invested": round(d["invested"], 2),
            "percent": round(d["invested"] / total_invested * 100.0, 1) if total_invested else 0.0,
            "stocks": stocks,
        })
    rows.sort(key=lambda r: r["invested"], reverse=True)
    return rows, round(total_invested, 2)
