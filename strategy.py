from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from indicators import add_indicators, add_relative_strength
from market_data import download_symbol


@dataclass(frozen=True)
class Candidate:
    symbol: str
    price: float
    score: float
    atr: float
    relative_strength: float
    volume_ratio: float
    macd_hist: float
    ema_fast: float
    ema_slow: float

    def as_dict(self) -> dict[str, float | str]:
        return self.__dict__.copy()


def market_regime_allows_buys(benchmark: pd.DataFrame, fast_length: int, slow_length: int) -> bool:
    if benchmark.empty or len(benchmark) < slow_length + 1:
        return False
    close = benchmark["Close"]
    fast_ma = close.rolling(fast_length).mean()
    slow_ma = close.rolling(slow_length).mean()
    return bool(close.iloc[-1] > slow_ma.iloc[-1] and fast_ma.iloc[-1] > slow_ma.iloc[-1])


def evaluate_symbol(symbol: str, data: pd.DataFrame, benchmark: pd.DataFrame, settings) -> Candidate | None:
    min_rows = max(
        settings.ema_slow,
        settings.macd_slow + settings.macd_signal,
        settings.atr_length,
        settings.volume_average_length,
        settings.bollinger_length,
    ) + 25
    if data.empty or len(data) < min_rows:
        return None

    frame = add_indicators(
        data,
        ema_fast=settings.ema_fast,
        ema_slow=settings.ema_slow,
        macd_fast=settings.macd_fast,
        macd_slow=settings.macd_slow,
        macd_signal=settings.macd_signal,
        atr_length=settings.atr_length,
        volume_average_length=settings.volume_average_length,
        bollinger_length=settings.bollinger_length,
        bollinger_std=settings.bollinger_std,
    )
    frame = add_relative_strength(frame, benchmark)
    return evaluate_prepared_symbol(symbol, frame, settings)


def evaluate_prepared_symbol(symbol: str, frame: pd.DataFrame, settings) -> Candidate | None:
    min_rows = max(
        settings.ema_slow,
        settings.macd_slow + settings.macd_signal,
        settings.atr_length,
        settings.volume_average_length,
        settings.bollinger_length,
    ) + 25
    if frame.empty or len(frame) < min_rows:
        return None

    latest = frame.iloc[-1]
    previous = frame.iloc[-2]

    values = [
        latest["Close"],
        latest["ema_fast"],
        latest["ema_slow"],
        latest["macd"],
        latest["macd_signal"],
        latest["macd_hist"],
        previous["macd_hist"],
        latest["relative_strength"],
        latest["avg_volume"],
        latest["atr"],
    ]
    if any(pd.isna(value) for value in values):
        return None

    price = float(latest["Close"])
    ema_fast = float(latest["ema_fast"])
    ema_slow = float(latest["ema_slow"])
    macd_crossed = previous["macd"] <= previous["macd_signal"] and latest["macd"] > latest["macd_signal"]
    hist_increasing = latest["macd_hist"] > 0 and latest["macd_hist"] > previous["macd_hist"]
    volume_ratio = float(latest["Volume"] / latest["avg_volume"]) if latest["avg_volume"] else 0.0
    relative_strength = float(latest["relative_strength"])

    if not (price > ema_fast and ema_fast > ema_slow and macd_crossed and hist_increasing):
        return None
    if settings.require_relative_strength and relative_strength <= 0:
        return None
    if settings.require_volume_confirmation and volume_ratio <= 1:
        return None
    if settings.use_bollinger_confirmation:
        upper = float(latest["bb_upper"])
        if price > upper * (1 + settings.bollinger_max_extension):
            return None

    trend_score = ((ema_fast - ema_slow) / ema_slow) * 100
    macd_score = float(latest["macd_hist"] - previous["macd_hist"]) * 10
    rs_score = relative_strength * 100
    volume_score = min(volume_ratio - 1, 3) * 5
    ema_distance_score = min(((price - ema_fast) / ema_fast) * 100, 10)
    acceleration_score = (float(latest["momentum_5"]) - float(latest["momentum_10"])) * 100
    score = trend_score + macd_score + rs_score + volume_score + ema_distance_score + acceleration_score

    return Candidate(
        symbol=symbol,
        price=price,
        score=round(float(score), 4),
        atr=float(latest["atr"]),
        relative_strength=relative_strength,
        volume_ratio=volume_ratio,
        macd_hist=float(latest["macd_hist"]),
        ema_fast=ema_fast,
        ema_slow=ema_slow,
    )


def scan_universe(universe: list[str], settings) -> list[Candidate]:
    benchmark = download_symbol(settings.benchmark_symbol, settings.data_period, settings.data_interval)
    candidates: list[Candidate] = []
    for symbol in universe:
        print(f"Scanning {symbol}...")
        data = download_symbol(symbol, settings.data_period, settings.data_interval)
        candidate = evaluate_symbol(symbol, data, benchmark, settings)
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates
