from __future__ import annotations

import pandas as pd
import yfinance as yf


def download_symbol(symbol: str, period: str, interval: str) -> pd.DataFrame:
    data = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    return normalize_ohlcv(data)


def download_history(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    data = yf.download(symbol, start=start, end=end, interval=interval, progress=False, auto_adjust=False)
    return normalize_ohlcv(data)


def normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        return pd.DataFrame()
    return data[required].dropna()
