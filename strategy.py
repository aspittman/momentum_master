from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from indicators import add_indicators, add_relative_strength_with_lookback
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
    macd: float
    macd_signal: float
    entry_reason: str = "momentum_entry"

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
    frame = add_relative_strength_with_lookback(frame, benchmark, settings.relative_strength_lookback)
    # The bot scans while the market is open; the final daily candle is incomplete.
    completed = frame.iloc[:-1] if settings.data_interval.endswith("d") else frame
    return evaluate_prepared_symbol(symbol, completed, settings)


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
    ema_rising = latest["ema_fast"] > previous["ema_fast"]
    macd_bullish = latest["macd"] > latest["macd_signal"]
    hist_increasing = latest["macd_hist"] > 0 and latest["macd_hist"] > previous["macd_hist"]
    volume_ratio = float(latest["Volume"] / latest["avg_volume"]) if latest["avg_volume"] else 0.0
    relative_strength = float(latest["relative_strength"])

    if not (price > ema_fast and ema_fast > ema_slow and ema_rising and macd_bullish and hist_increasing):
        return None
    if settings.require_relative_strength and relative_strength <= 0:
        return None
    if settings.require_volume_confirmation and volume_ratio < settings.min_volume_ratio:
        return None
    if settings.use_bollinger_confirmation:
        upper = float(latest["bb_upper"])
        if price > upper * (1 + settings.bollinger_max_extension):
            return None

    def normalized(value: float, typical_strong_value: float) -> float:
        """Scale unlike indicators to a bounded, comparable [-1, 1] range."""
        return max(-1.0, min(1.0, value / typical_strong_value))

    # Price-normalize MACD values before applying bounded scales. Dividing the
    # histogram by MACD itself was unstable whenever MACD approached zero and
    # allowed a single component to overwhelm the complete ranking.
    hist_percent = float(latest["macd_hist"]) / price
    acceleration_percent = float(latest["macd_hist"] - previous["macd_hist"]) / price
    ema_distance_raw = (price - ema_fast) / ema_fast
    ema_slope_raw = (ema_fast - float(previous["ema_fast"])) / float(previous["ema_fast"])
    recent_momentum_raw = float(latest["momentum_5"])
    rs_component = normalized(relative_strength, 0.10)
    hist_component = normalized(hist_percent, 0.01)
    acceleration_component = normalized(acceleration_percent, 0.005)
    ema_distance = normalized(ema_distance_raw, 0.10)
    ema_slope = normalized(ema_slope_raw, 0.02)
    volume_component = normalized(max(0.0, volume_ratio - 1.0), 1.0)
    recent_momentum = normalized(recent_momentum_raw, 0.10)
    breakout = 0.0
    if settings.enable_breakout_score and len(frame) > settings.breakout_lookback:
        prior_high = float(frame["High"].iloc[-settings.breakout_lookback - 1:-1].max())
        breakout = normalized(max(0.0, (price - prior_high) / prior_high), 0.10)
    score = (
        settings.score_weight_relative_strength * rs_component
        + settings.score_weight_macd_strength * hist_component
        + settings.score_weight_macd_acceleration * acceleration_component
        + settings.score_weight_ema_distance * ema_distance
        + settings.score_weight_ema_slope * ema_slope
        + settings.score_weight_volume * volume_component
        + settings.score_weight_price_momentum * recent_momentum
        + settings.score_weight_breakout * breakout
    )
    if score < settings.minimum_momentum_score:
        return None

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
        macd=float(latest["macd"]),
        macd_signal=float(latest["macd_signal"]),
    )


def scan_universe(universe: list[str], settings) -> list[Candidate]:
    benchmark = download_symbol(settings.benchmark_symbol, settings.data_period, settings.data_interval)
    if benchmark.empty or "Close" not in benchmark.columns:
        print(
            f"Unable to download benchmark data for {settings.benchmark_symbol}; "
            "skipping this scan cycle."
        )
        return []

    candidates: list[Candidate] = []
    for symbol in universe:
        print(f"Scanning {symbol}...")
        data = download_symbol(symbol, settings.data_period, settings.data_interval)
        candidate = evaluate_symbol(symbol, data, benchmark, settings)
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates
