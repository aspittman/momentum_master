from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd


OPTION_SYMBOL = re.compile(r"\d{6}[CP]\d{8}$")


def is_option_symbol(symbol: str) -> bool:
    return bool(OPTION_SYMBOL.search(str(symbol).upper()))


def stock_closed_trades(path, allowed_symbols=None) -> pd.DataFrame:
    try:
        trades = pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()
    if trades.empty or "realized_pl" not in trades:
        return pd.DataFrame()
    trades = trades[~trades["symbol"].astype(str).map(is_option_symbol)].copy()
    if allowed_symbols is not None:
        allowed = {str(symbol).upper() for symbol in allowed_symbols}
        trades = trades[trades["symbol"].astype(str).str.upper().isin(allowed)].copy()
    trades["realized_pl"] = pd.to_numeric(trades["realized_pl"], errors="coerce")
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], errors="coerce", utc=True)
    return trades.dropna(subset=["realized_pl", "timestamp"]).sort_values("timestamp")


@dataclass(frozen=True)
class RiskGate:
    allowed: bool
    reasons: tuple[str, ...]
    daily_pl: float = 0.0
    weekly_pl: float = 0.0
    drawdown: float = 0.0
    consecutive_losses: int = 0


def evaluate_risk_gate(path, settings, now: datetime | None = None) -> RiskGate:
    trades = stock_closed_trades(path, getattr(settings, "universe", None))
    if trades.empty:
        return RiskGate(True, ())
    now = now or datetime.now(timezone.utc)
    today = now.date()
    week_start = today.fromordinal(today.toordinal() - today.weekday())
    daily = float(trades.loc[trades.timestamp.dt.date == today, "realized_pl"].sum())
    weekly = float(trades.loc[trades.timestamp.dt.date >= week_start, "realized_pl"].sum())
    pnl = trades.realized_pl
    equity = float(settings.max_total_capital) + pnl.cumsum()
    running_peak = equity.cummax().clip(lower=float(settings.max_total_capital))
    drawdown = float((equity / running_peak - 1).min())
    consecutive = 0
    for value in reversed(pnl.tolist()):
        if value < 0:
            consecutive += 1
        else:
            break
    reasons = []
    capital = float(settings.max_total_capital)
    if daily <= -capital * settings.max_daily_loss_percent:
        reasons.append(f"daily realized loss ${daily:.2f}")
    if weekly <= -capital * settings.max_weekly_loss_percent:
        reasons.append(f"weekly realized loss ${weekly:.2f}")
    if drawdown <= -settings.max_drawdown_percent:
        reasons.append(f"realized drawdown {drawdown:.1%}")
    if consecutive >= settings.max_consecutive_losses:
        reasons.append(f"{consecutive} consecutive losses")
    return RiskGate(not reasons, tuple(reasons), daily, weekly, drawdown, consecutive)


def risk_sized_notional(candidate, settings) -> float:
    initial_stop = max(
        candidate.price * (1 - settings.hard_stop_percent),
        candidate.price - settings.atr_multiplier * candidate.atr,
    )
    risk_per_share = candidate.price - initial_stop
    if risk_per_share <= 0:
        return 0.0
    risk_budget = settings.max_total_capital * getattr(settings, "risk_per_trade_percent", 0.005)
    return max(0.0, min(settings.dollars_per_trade, risk_budget * candidate.price / risk_per_share))
