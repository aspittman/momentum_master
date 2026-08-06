MEGA_CAPS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMD",
    "META",
    "AMZN",
    "GOOGL",
    "NFLX",
    "TSLA",
    "AVGO",
]

LARGE_CAPS = [
    "JPM",
    "LLY",
    "CAT",
    "COST",
    "WMT",
    "XOM",
    "CVX",
    "UNH",
    "HD",
    "BA",
]

GROWTH = [
    "PLTR",
    "SMCI",
    "CRWD",
    "PANW",
    "SNOW",
    "SHOP",
    "ARM",
    "MU",
]

UNIVERSE = MEGA_CAPS + LARGE_CAPS + GROWTH

# Coarse risk buckets. These are intentionally broader than formal GICS sectors:
# the purpose is to prevent several highly correlated momentum bets at once.
SECTOR_BY_SYMBOL = {
    "AAPL": "technology", "MSFT": "technology", "NVDA": "semiconductors",
    "AMD": "semiconductors", "META": "internet", "AMZN": "consumer_internet",
    "GOOGL": "internet", "NFLX": "internet", "TSLA": "consumer_growth",
    "AVGO": "semiconductors", "JPM": "financials", "LLY": "healthcare",
    "CAT": "industrials", "COST": "consumer_defensive", "WMT": "consumer_defensive",
    "XOM": "energy", "CVX": "energy", "UNH": "healthcare", "HD": "consumer_growth",
    "BA": "industrials", "PLTR": "technology", "SMCI": "technology",
    "CRWD": "technology", "PANW": "technology", "SNOW": "technology",
    "SHOP": "consumer_internet", "ARM": "semiconductors", "MU": "semiconductors",
}


def sector_for_symbol(symbol: str) -> str:
    return SECTOR_BY_SYMBOL.get(symbol.upper(), f"other:{symbol.upper()}")
