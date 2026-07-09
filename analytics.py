from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_trades(path: str = "logs/trades.csv") -> pd.DataFrame:
    trade_path = Path(path)
    if not trade_path.exists():
        return pd.DataFrame()
    return pd.read_csv(trade_path)


def summarize_trades(trades: pd.DataFrame) -> dict[str, float | int | str]:
    if trades.empty or "pnl" not in trades:
        return {}
    pnl = pd.to_numeric(trades["pnl"], errors="coerce").dropna()
    if pnl.empty:
        return {}
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    return {
        "total_trades": int(len(pnl)),
        "win_rate": float(len(wins) / len(pnl)),
        "expectancy": float(pnl.mean()),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else float("inf"),
        "average_win": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss": float(losses.mean()) if not losses.empty else 0.0,
        "total_pl": float(pnl.sum()),
    }


def equity_curve_from_pnl(trades: pd.DataFrame, starting_equity: float = 0.0) -> pd.Series:
    if trades.empty or "pnl" not in trades:
        return pd.Series(dtype=float)
    pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0)
    return starting_equity + pnl.cumsum()
