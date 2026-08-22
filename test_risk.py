from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from risk import evaluate_risk_gate, is_option_symbol, risk_sized_notional


class RiskTests(unittest.TestCase):
    def settings(self, **overrides):
        values = dict(
            max_total_capital=2500.0, risk_per_trade_percent=0.005,
            dollars_per_trade=500.0, hard_stop_percent=0.05, atr_multiplier=1.5,
            max_daily_loss_percent=0.02, max_weekly_loss_percent=0.05,
            max_drawdown_percent=0.08, max_consecutive_losses=4,
        )
        values.update(overrides)
        return SimpleNamespace(**values)

    def write_trades(self, directory, rows):
        path = Path(directory) / "trades.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_position_size_is_limited_by_dollars_at_risk(self):
        candidate = SimpleNamespace(price=100.0, atr=10.0)
        self.assertAlmostEqual(risk_sized_notional(candidate, self.settings()), 250.0)

    def test_daily_loss_and_streak_block_new_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_trades(directory, [
                {"timestamp": "2026-08-06T14:00:00Z", "symbol": "AAPL", "realized_pl": -20},
                {"timestamp": "2026-08-06T15:00:00Z", "symbol": "MSFT", "realized_pl": -35},
            ])
            gate = evaluate_risk_gate(
                path, self.settings(max_consecutive_losses=2),
                datetime(2026, 8, 6, 20, tzinfo=timezone.utc),
            )
            self.assertFalse(gate.allowed)
            self.assertTrue(any("daily" in reason for reason in gate.reasons))
            self.assertTrue(any("consecutive" in reason for reason in gate.reasons))

    def test_options_do_not_affect_stock_circuit_breaker(self):
        self.assertTrue(is_option_symbol("PFE260918C00025000"))
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_trades(directory, [{
                "timestamp": "2026-08-06T14:00:00Z", "symbol": "PFE260918C00025000",
                "realized_pl": -500,
            }])
            self.assertTrue(evaluate_risk_gate(path, self.settings()).allowed)

    def test_symbols_outside_strategy_universe_do_not_trip_circuit_breaker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_trades(directory, [
                {"timestamp": "2026-08-06T14:00:00Z", "symbol": "XLP", "realized_pl": -500},
                {"timestamp": "2026-08-06T15:00:00Z", "symbol": "BTC/USD", "realized_pl": -500},
            ])
            configured = self.settings(universe=["AAPL"])
            gate = evaluate_risk_gate(
                path, configured, datetime(2026, 8, 6, 20, tzinfo=timezone.utc)
            )
            self.assertTrue(gate.allowed)
            self.assertEqual(gate.daily_pl, 0.0)


if __name__ == "__main__":
    unittest.main()
