from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands


def add_indicators(
    data: pd.DataFrame,
    *,
    ema_fast: int,
    ema_slow: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    atr_length: int,
    volume_average_length: int,
    bollinger_length: int,
    bollinger_std: float,
) -> pd.DataFrame:
    frame = data.copy()
    close = frame["Close"]

    frame["ema_fast"] = EMAIndicator(close=close, window=ema_fast).ema_indicator()
    frame["ema_slow"] = EMAIndicator(close=close, window=ema_slow).ema_indicator()

    macd = MACD(
        close=close,
        window_fast=macd_fast,
        window_slow=macd_slow,
        window_sign=macd_signal,
    )
    frame["macd"] = macd.macd()
    frame["macd_signal"] = macd.macd_signal()
    frame["macd_hist"] = macd.macd_diff()

    atr = AverageTrueRange(
        high=frame["High"],
        low=frame["Low"],
        close=close,
        window=atr_length,
    )
    frame["atr"] = atr.average_true_range()
    frame["avg_volume"] = frame["Volume"].rolling(volume_average_length).mean()
    frame["momentum_5"] = close.pct_change(5)
    frame["momentum_10"] = close.pct_change(10)
    frame["rsi"] = RSIIndicator(close=close, window=14).rsi()

    bands = BollingerBands(close=close, window=bollinger_length, window_dev=bollinger_std)
    frame["bb_upper"] = bands.bollinger_hband()
    frame["bb_middle"] = bands.bollinger_mavg()
    frame["bb_lower"] = bands.bollinger_lband()
    return frame


def add_relative_strength(data: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    aligned_benchmark = benchmark["Close"].reindex(frame.index).ffill()
    symbol_return = frame["Close"].pct_change(20)
    benchmark_return = aligned_benchmark.pct_change(20)
    frame["relative_strength"] = symbol_return - benchmark_return
    return frame
