from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from config import settings
from indicators import add_indicators, add_relative_strength
from market_data import download_history
from strategy import evaluate_prepared_symbol, market_regime_allows_buys


@dataclass
class BacktestPosition:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    qty: float
    highest_price: float


def max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak:
            worst = min(worst, (equity - peak) / peak)
    return worst


def summarize(trades: list[dict], equity_curve: list[float]) -> dict:
    closed = pd.DataFrame([trade for trade in trades if trade["side"] == "sell"])
    if closed.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "total_pl": 0.0,
            "max_drawdown": max_drawdown(equity_curve),
            "best_symbol": "",
            "worst_symbol": "",
            "trades_by_symbol": {},
        }
    pnl = closed["pnl"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    by_symbol = closed.groupby("symbol")["pnl"].agg(["count", "sum"]).sort_values("sum", ascending=False)
    gross_loss = abs(losses.sum())
    return {
        "total_trades": int(len(closed)),
        "win_rate": float(len(wins) / len(closed)),
        "expectancy": float(pnl.mean()),
        "profit_factor": float(wins.sum() / gross_loss) if gross_loss else float("inf"),
        "average_win": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss": float(losses.mean()) if not losses.empty else 0.0,
        "total_pl": float(pnl.sum()),
        "max_drawdown": float(max_drawdown(equity_curve)),
        "best_symbol": str(by_symbol.index[0]),
        "worst_symbol": str(by_symbol.index[-1]),
        "trades_by_symbol": by_symbol.to_dict("index"),
    }


def run_backtest(start: str, end: str, initial_cash: float) -> tuple[list[dict], dict]:
    benchmark = download_history(settings.benchmark_symbol, start, end, settings.data_interval)
    histories = {
        symbol: download_history(symbol, start, end, settings.data_interval)
        for symbol in settings.universe
    }
    prepared = {}
    for symbol, data in histories.items():
        if data.empty:
            continue
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
        prepared[symbol] = add_relative_strength(frame, benchmark)

    dates = sorted(set().union(*(frame.index for frame in prepared.values())))
    cash = initial_cash
    positions: dict[str, BacktestPosition] = {}
    cooldowns: dict[str, pd.Timestamp] = {}
    trades: list[dict] = []
    equity_curve: list[float] = [initial_cash]

    for date in dates:
        market_slice = benchmark.loc[:date]
        can_buy = (
            not settings.require_market_regime
            or market_regime_allows_buys(market_slice, settings.market_ma_fast, settings.market_ma_slow)
        )

        for symbol, position in list(positions.items()):
            frame = prepared[symbol].loc[:date]
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            price = float(latest["Close"])
            atr = float(latest["atr"])
            position.highest_price = max(position.highest_price, price)
            atr_stop = position.highest_price - settings.atr_multiplier * atr
            backup_stop = position.entry_price * (1 - settings.backup_stop_loss_percent)
            if price <= max(atr_stop, backup_stop):
                proceeds = position.qty * price
                pnl = proceeds - (position.qty * position.entry_price)
                cash += proceeds
                trades.append(
                    {
                        "date": date,
                        "symbol": symbol,
                        "side": "sell",
                        "price": price,
                        "qty": position.qty,
                        "pnl": pnl,
                    }
                )
                cooldowns[symbol] = date
                del positions[symbol]

        market_value = 0.0
        for symbol, position in positions.items():
            frame = prepared[symbol].loc[:date]
            if not frame.empty:
                market_value += position.qty * float(frame.iloc[-1]["Close"])
        equity_curve.append(cash + market_value)

        if not can_buy or len(positions) >= settings.max_positions:
            continue

        candidates = []
        for symbol, frame in prepared.items():
            if symbol in positions:
                continue
            if symbol in cooldowns and (date - cooldowns[symbol]).total_seconds() < settings.cooldown_seconds:
                continue
            candidate = evaluate_prepared_symbol(symbol, frame.loc[:date], settings)
            if candidate:
                candidates.append(candidate)
        candidates.sort(key=lambda item: item.score, reverse=True)

        used_capital = sum(pos.qty * pos.entry_price for pos in positions.values())
        for candidate in candidates:
            if len(positions) >= settings.max_positions:
                break
            if used_capital + settings.dollars_per_trade > settings.max_total_capital:
                break
            if cash < settings.dollars_per_trade:
                break
            qty = settings.dollars_per_trade / candidate.price
            cash -= settings.dollars_per_trade
            used_capital += settings.dollars_per_trade
            positions[candidate.symbol] = BacktestPosition(
                symbol=candidate.symbol,
                entry_date=date,
                entry_price=candidate.price,
                qty=qty,
                highest_price=candidate.price,
            )
            trades.append(
                {
                    "date": date,
                    "symbol": candidate.symbol,
                    "side": "buy",
                    "price": candidate.price,
                    "qty": qty,
                    "pnl": 0.0,
                }
            )

    summary = summarize(trades, equity_curve)
    return trades, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest MomentumMaster.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--initial-cash", type=float, default=10000.0)
    args = parser.parse_args()

    _, summary = run_backtest(args.start, args.end, args.initial_cash)
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
