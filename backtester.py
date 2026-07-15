from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from config import settings
from indicators import add_indicators, add_relative_strength_with_lookback
from market_data import download_history
from signals import momentum_exit_decision
from strategy import evaluate_prepared_symbol, market_regime_allows_buys


@dataclass
class BacktestPosition:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    qty: float
    highest_price: float
    candidate: object
    trailing_stop: float


def _configured(**overrides):
    values = dict(settings.__dict__)
    values.update(overrides)
    return SimpleNamespace(**values)


def _prepare(start: str, end: str, cfg):
    benchmark = download_history(cfg.benchmark_symbol, start, end, cfg.data_interval)
    prepared = {}
    for symbol in cfg.universe:
        data = download_history(symbol, start, end, cfg.data_interval)
        if data.empty:
            continue
        frame = add_indicators(
            data, ema_fast=cfg.ema_fast, ema_slow=cfg.ema_slow,
            macd_fast=cfg.macd_fast, macd_slow=cfg.macd_slow, macd_signal=cfg.macd_signal,
            atr_length=cfg.atr_length, volume_average_length=cfg.volume_average_length,
            bollinger_length=cfg.bollinger_length, bollinger_std=cfg.bollinger_std,
        )
        prepared[symbol] = add_relative_strength_with_lookback(
            frame, benchmark, cfg.relative_strength_lookback
        )
    return benchmark, prepared


def max_drawdown(equity: list[dict] | list[float]) -> float:
    values = [float(item["equity"]) if isinstance(item, dict) else float(item) for item in equity]
    if not values:
        return 0.0
    series = pd.Series(values)
    return float((series / series.cummax() - 1).min())


def summarize(trades: list[dict], equity_curve: list[dict]) -> dict:
    closed = pd.DataFrame([trade for trade in trades if trade["side"] == "sell"])
    if closed.empty:
        return {"total_trades": 0, "win_rate": 0.0, "total_pl": 0.0, "expectancy": 0.0,
                "average_win": 0.0, "average_loss": 0.0, "profit_factor": 0.0,
                "max_drawdown": max_drawdown(equity_curve), "average_holding_duration": 0.0,
                "median_holding_duration": 0.0, "best_symbol": "", "worst_symbol": "",
                "results_by_symbol": {}, "results_by_exit_reason": {}, "results_by_market_regime": {}}
    pnl = closed["realized_pl"]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    by_symbol = closed.groupby("symbol")["realized_pl"].agg(["count", "sum"])
    def grouped(column):
        return closed.groupby(column)["realized_pl"].agg(["count", "sum", "mean"]).to_dict("index")
    gross_loss = abs(float(losses.sum()))
    return {
        "total_trades": len(closed), "win_rate": float((pnl > 0).mean()),
        "total_pl": float(pnl.sum()), "expectancy": float(pnl.mean()),
        "average_win": float(wins.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(wins.sum() / gross_loss) if gross_loss else float("inf"),
        "max_drawdown": max_drawdown(equity_curve),
        "average_holding_duration": float(closed["holding_days"].mean()),
        "median_holding_duration": float(closed["holding_days"].median()),
        "best_symbol": str(by_symbol["sum"].idxmax()), "worst_symbol": str(by_symbol["sum"].idxmin()),
        "results_by_symbol": grouped("symbol"), "results_by_exit_reason": grouped("exit_reason"),
        "results_by_market_regime": grouped("market_regime"),
    }


def run_backtest(start: str, end: str, initial_cash: float, *, cfg=None,
                 output_dir: str | None = None, prepared_data=None):
    cfg = cfg or settings
    benchmark, prepared = prepared_data or _prepare(start, end, cfg)
    dates = sorted(set().union(*(frame.index for frame in prepared.values()))) if prepared else []
    cash, positions, cooldowns = initial_cash, {}, {}
    pending_buys: list = []
    pending_sells: dict[str, str] = {}
    trades, equity_curve = [], []

    for date in dates:
        # Orders generated from the previous completed bar execute at this bar's open.
        for symbol, reason in list(pending_sells.items()):
            if symbol not in positions or date not in prepared[symbol].index:
                continue
            position = positions.pop(symbol)
            row = prepared[symbol].loc[date]
            price = float(row["Open"])
            proceeds = position.qty * price
            pnl = position.qty * (price - position.entry_price)
            cash += proceeds
            regime = "bullish" if market_regime_allows_buys(
                benchmark.loc[:date].iloc[:-1], cfg.market_ma_fast, cfg.market_ma_slow
            ) else "bearish"
            trades.append({"timestamp": date, "symbol": symbol, "side": "sell", "qty": position.qty,
                "entry_price": position.entry_price, "exit_price": price, "realized_pl": pnl,
                "realized_pl_percent": price / position.entry_price - 1, "entry_score": position.candidate.score,
                "entry_reason": "momentum_entry", "exit_reason": reason,
                "atr_at_entry": position.candidate.atr, "atr_at_exit": row.get("atr", ""),
                "holding_days": (date - position.entry_date).total_seconds() / 86400, "market_regime": regime})
            cooldowns[symbol] = date
            del pending_sells[symbol]

        buys_executed = 0
        for candidate in pending_buys:
            symbol = candidate.symbol
            if buys_executed >= cfg.max_new_buys_per_cycle or len(positions) >= cfg.max_positions:
                break
            if symbol in positions or date not in prepared[symbol].index:
                continue
            if cooldowns.get(symbol) is not None and (date - cooldowns[symbol]).total_seconds() < cfg.cooldown_seconds:
                continue
            allocation = min(cfg.dollars_per_trade, cash)
            invested = sum(p.qty * p.entry_price for p in positions.values())
            if allocation < cfg.dollars_per_trade or invested + allocation > cfg.max_total_capital:
                continue
            price = float(prepared[symbol].loc[date, "Open"])
            qty = allocation / price
            cash -= allocation
            positions[symbol] = BacktestPosition(
                symbol, date, price, qty, price, candidate,
                price - cfg.atr_multiplier * candidate.atr,
            )
            trades.append({"timestamp": date, "symbol": symbol, "side": "buy", "qty": qty,
                           "entry_price": price, "entry_score": candidate.score,
                           "entry_reason": "momentum_entry", "atr_at_entry": candidate.atr})
            buys_executed += 1
        pending_buys = []

        # Completed-close decisions schedule orders for the next available bar.
        for symbol, position in positions.items():
            frame = prepared[symbol].loc[:date]
            if frame.empty or date not in frame.index:
                continue
            position.highest_price = max(position.highest_price, float(frame.iloc[-1]["Close"]))
            proposed_stop = position.highest_price - cfg.atr_multiplier * float(frame.iloc[-1]["atr"])
            position.trailing_stop = max(position.trailing_stop, proposed_stop)
            decision = momentum_exit_decision(frame, entry_price=position.entry_price,
                highest_price=position.highest_price, settings=cfg,
                atr_stop_floor=position.trailing_stop)
            if decision and symbol not in pending_sells:
                pending_sells[symbol] = decision.reason

        market_slice = benchmark.loc[:date]
        can_buy = not cfg.require_market_regime or market_regime_allows_buys(
            market_slice, cfg.market_ma_fast, cfg.market_ma_slow
        )
        if can_buy:
            candidates = []
            for symbol, frame in prepared.items():
                if symbol in positions or symbol in pending_sells or date not in frame.index:
                    continue
                if symbol in cooldowns and (date - cooldowns[symbol]).total_seconds() < cfg.cooldown_seconds:
                    continue
                candidate = evaluate_prepared_symbol(symbol, frame.loc[:date], cfg)
                if candidate:
                    candidates.append(candidate)
            pending_buys = sorted(candidates, key=lambda item: item.score, reverse=True)[:cfg.max_new_buys_per_cycle]

        market_value = sum(
            p.qty * float(prepared[s].loc[:date].iloc[-1]["Close"]) for s, p in positions.items()
        )
        equity_curve.append({"timestamp": date, "equity": cash + market_value})

    summary = summarize(trades, equity_curve)
    if output_dir:
        path = Path(output_dir); path.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(trades).to_csv(path / "trades.csv", index=False)
        pd.DataFrame(equity_curve).to_csv(path / "equity_curve.csv", index=False)
        (path / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return trades, summary


def parameter_comparison(start, end, initial_cash, output_dir):
    rows = []
    shared_data = _prepare(start, end, settings)
    exits = [(False, False, "atr_only"), (True, False, "atr_ema"),
             (False, True, "atr_macd"), (True, True, "atr_ema_macd")]
    for multiplier in [1.0, 1.25, 1.5, 1.75, 2.0]:
        for hard_stop in [0.03, 0.04, 0.05, 0.06]:
            for ema, macd, label in exits:
                cfg = _configured(atr_multiplier=multiplier, hard_stop_percent=hard_stop,
                                  enable_ema20_exit=ema, enable_macd_bearish_exit=macd)
                _, result = run_backtest(start, end, initial_cash, cfg=cfg, prepared_data=shared_data)
                rows.append({"atr_multiplier": multiplier, "hard_stop": hard_stop,
                             "momentum_exits": label, **result})
    path = Path(output_dir); path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path / "parameter_comparison_oos.csv", index=False)
    return rows


def walk_forward(start, end, initial_cash, train_days, test_days, output_dir):
    # Fixed parameters are reported on sequential unseen test windows; training windows are explicit
    # and deliberately not used to make an in-sample performance claim.
    cursor, finish, rows = pd.Timestamp(start), pd.Timestamp(end), []
    while cursor < finish:
        train_end = cursor + pd.Timedelta(days=train_days)
        test_end = min(train_end + pd.Timedelta(days=test_days), finish)
        if train_end >= finish:
            break
        _, in_sample = run_backtest(str(cursor.date()), str(train_end.date()), initial_cash)
        _, out_sample = run_backtest(str(train_end.date()), str(test_end.date()), initial_cash)
        rows.append({"train_start": cursor, "train_end": train_end, "test_end": test_end,
                     "in_sample": in_sample, "out_of_sample": out_sample})
        cursor = test_end
    path = Path(output_dir); path.mkdir(parents=True, exist_ok=True)
    (path / "walk_forward.json").write_text(json.dumps(rows, indent=2, default=str))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Backtest MomentumMaster without look-ahead bias.")
    parser.add_argument("--start", required=True); parser.add_argument("--end", required=True)
    parser.add_argument("--initial-cash", type=float, default=10000.0)
    parser.add_argument("--output-dir", default="backtest_results")
    parser.add_argument("--compare-parameters", action="store_true")
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--train-days", type=int, default=365); parser.add_argument("--test-days", type=int, default=90)
    args = parser.parse_args()
    if args.compare_parameters:
        result = parameter_comparison(args.start, args.end, args.initial_cash, args.output_dir)
        print(f"Saved {len(result)} out-of-sample parameter comparisons.")
    elif args.walk_forward:
        result = walk_forward(args.start, args.end, args.initial_cash, args.train_days, args.test_days, args.output_dir)
        print(f"Saved {len(result)} walk-forward windows.")
    else:
        _, result = run_backtest(args.start, args.end, args.initial_cash, output_dir=args.output_dir)
        for key, value in result.items(): print(f"{key}: {value}")


if __name__ == "__main__":
    main()
