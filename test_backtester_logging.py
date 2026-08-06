from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from backtester import BacktestDataError, run_backtest


class BacktesterLoggingTests(unittest.TestCase):
    def test_missing_market_data_fails_instead_of_writing_zero_report(self):
        cfg = SimpleNamespace(benchmark_symbol="SPY")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BacktestDataError):
                run_backtest("2026-01-02", "2026-01-05", 100.0, cfg=cfg,
                    output_dir=directory,
                    prepared_data=(pd.DataFrame(), {}))
            self.assertFalse((Path(directory) / "summary.json").exists())

    def test_open_position_is_logged_as_end_of_backtest_sale(self):
        dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
        stock = pd.DataFrame({
            "Open": [10.0, 11.0], "High": [11.0, 12.5], "Low": [10.0, 11.0],
            "Close": [10.5, 12.0], "atr": [1.0, 1.0],
        }, index=dates)
        benchmark = pd.DataFrame({"Close": [100.0, 101.0]}, index=dates)
        candidate = SimpleNamespace(symbol="ABC", score=80.0, atr=1.0, price=10.5)
        cfg = SimpleNamespace(
            max_new_buys_per_cycle=1, max_positions=1, cooldown_seconds=0,
            dollars_per_trade=100.0, max_total_capital=100.0,
            atr_multiplier=1.5, hard_stop_percent=0.05, risk_per_trade_percent=0.05,
            max_positions_per_sector=2, require_market_regime=False,
            market_ma_fast=1, market_ma_slow=2,
        )
        with tempfile.TemporaryDirectory() as directory, \
             patch("backtester.evaluate_prepared_symbol", return_value=candidate), \
             patch("backtester.momentum_exit_decision", return_value=None), \
             patch("backtester.market_regime_allows_buys", return_value=True):
            trades, summary = run_backtest(
                "2026-01-02", "2026-01-05", 100.0, cfg=cfg,
                output_dir=directory, prepared_data=(benchmark, {"ABC": stock}),
            )
            self.assertEqual([trade["side"] for trade in trades], ["buy", "sell"])
            self.assertEqual(trades[-1]["exit_reason"], "end_of_backtest")
            self.assertAlmostEqual(trades[-1]["realized_pl"], 100.0 / 11.0)
            self.assertEqual(summary["total_trades"], 1)
            saved = pd.read_csv(Path(directory) / "trades.csv")
            self.assertEqual(saved["side"].tolist(), ["buy", "sell"])

    def test_intraday_protective_stop_fills_at_stop_price(self):
        dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
        stock = pd.DataFrame({
            "Open": [10.0, 10.0], "High": [10.5, 10.2], "Low": [9.8, 8.0],
            "Close": [10.0, 8.5], "atr": [1.0, 1.0],
        }, index=dates)
        benchmark = pd.DataFrame({"Close": [100.0, 101.0]}, index=dates)
        candidate = SimpleNamespace(symbol="ABC", score=80.0, atr=1.0, price=10.0)
        cfg = SimpleNamespace(
            max_new_buys_per_cycle=1, max_positions=1, cooldown_seconds=0,
            dollars_per_trade=100.0, max_total_capital=100.0,
            atr_multiplier=1.5, hard_stop_percent=0.05, risk_per_trade_percent=0.05,
            max_positions_per_sector=2,
            require_market_regime=False, market_ma_fast=1, market_ma_slow=2,
        )
        with patch("backtester.evaluate_prepared_symbol", return_value=candidate), \
             patch("backtester.momentum_exit_decision", return_value=None), \
             patch("backtester.market_regime_allows_buys", return_value=True):
            trades, _ = run_backtest("2026-01-02", "2026-01-05", 100.0, cfg=cfg,
                prepared_data=(benchmark, {"ABC": stock}))
        sell = [trade for trade in trades if trade["side"] == "sell"][0]
        self.assertEqual(sell["exit_reason"], "protective_stop")
        self.assertAlmostEqual(sell["exit_price"], 9.5)


if __name__ == "__main__":
    unittest.main()
