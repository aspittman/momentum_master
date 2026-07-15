from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExitDecision:
    reason: str
    atr_stop: float
    hard_stop: float


def momentum_exit_decision(
    frame: pd.DataFrame,
    *,
    entry_price: float,
    highest_price: float,
    settings,
    enable_ema_exit: bool | None = None,
    enable_macd_exit: bool | None = None,
    atr_stop_floor: float | None = None,
    completed_bar_offset: int = 0,
) -> ExitDecision | None:
    """Evaluate completed bars in the required safety-first priority order."""
    if frame.empty:
        return None
    latest = frame.iloc[-1]
    price = float(latest["Close"])
    atr = float(latest["atr"])
    if pd.isna(atr) or atr <= 0:
        atr_stop = float("-inf")
    else:
        atr_stop = highest_price - settings.atr_multiplier * atr
    if atr_stop_floor is not None:
        atr_stop = max(atr_stop, atr_stop_floor)
    hard_stop = entry_price * (1 - settings.hard_stop_percent)
    if price <= hard_stop:
        return ExitDecision("hard_stop", atr_stop, hard_stop)
    if price <= atr_stop:
        return ExitDecision("atr_trailing_stop", atr_stop, hard_stop)

    signal_latest = frame.iloc[-1 - completed_bar_offset]
    signal_price = float(signal_latest["Close"])
    use_ema = settings.enable_ema20_exit if enable_ema_exit is None else enable_ema_exit
    if use_ema and not pd.isna(signal_latest["ema_fast"]) and signal_price < float(signal_latest["ema_fast"]):
        return ExitDecision("ema20_momentum_fade", atr_stop, hard_stop)

    use_macd = settings.enable_macd_bearish_exit if enable_macd_exit is None else enable_macd_exit
    if use_macd and len(frame) >= 2 + completed_bar_offset:
        previous = frame.iloc[-2 - completed_bar_offset]
        crossed_bearish = (
            float(previous["macd"]) >= float(previous["macd_signal"])
            and float(signal_latest["macd"]) < float(signal_latest["macd_signal"])
        )
        if crossed_bearish:
            return ExitDecision("macd_momentum_fade", atr_stop, hard_stop)
    return None
