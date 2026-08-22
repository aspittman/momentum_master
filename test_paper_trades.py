from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from paper_trades import paper_trade_report, reconcile_filled_orders
from state import BotState
from trade_logger import TradeLogger


def order(order_id, timestamp, symbol, side, qty, price):
    return SimpleNamespace(id=order_id, filled_at=timestamp, submitted_at=timestamp,
                           symbol=symbol, side=side, filled_qty=qty, filled_avg_price=price)


class PaperTradeTests(unittest.TestCase):
    def test_reconcile_is_idempotent_and_calculates_fifo_pnl(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            orders = [order("buy-1", "2026-01-01T00:00:00Z", "ABC", "buy", 2, 10),
                      order("sell-1", "2026-01-02T00:00:00Z", "ABC", "sell", 1, 12)]
            first = reconcile_filled_orders(orders, logger)
            second = reconcile_filled_orders(orders, logger)
            self.assertEqual(first, {"imported": 2, "updated": 0, "total": 2})
            self.assertEqual(second, {"imported": 0, "updated": 2, "total": 2})
            rows = logger.read()
            self.assertEqual(float(rows[1]["realized_pl"]), 2.0)
            self.assertEqual(float(rows[1]["entry_price"]), 10.0)

    def test_reconcile_replaces_provisional_zero_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            logger.log(symbol="ABC", side="sell", qty=0, order_id="sell-1")
            reconcile_filled_orders(
                [order("sell-1", "2026-01-02T00:00:00Z", "ABC", "sell", 3, 12)], logger)
            row = logger.read()[0]
            self.assertEqual(float(row["qty"]), 3.0)
            self.assertEqual(float(row["exit_price"]), 12.0)

    def test_reconcile_clears_pnl_from_unmatched_duplicate_sell(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            logger.log(symbol="ABC", side="buy", qty=1, entry_price=10, order_id="buy")
            logger.log(symbol="ABC", side="sell", qty=1, entry_price=10, exit_price=11,
                       realized_pl=1, realized_pl_percent=.1, order_id="sell-1")
            logger.log(symbol="ABC", side="sell", qty=1, entry_price=11, exit_price=12,
                       realized_pl=1, realized_pl_percent=1 / 11, order_id="sell-2")

            reconcile_filled_orders([], logger)

            rows = logger.read()
            self.assertEqual(float(rows[1]["realized_pl"]), 1.0)
            self.assertEqual(rows[2]["entry_price"], "")
            self.assertEqual(rows[2]["realized_pl"], "")

    def test_report_keeps_paper_results_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            reconcile_filled_orders(
                [order("b", "2026-01-01", "ABC", "buy", 1, 10),
                 order("s", "2026-01-02", "ABC", "sell", 1, 11)], logger)
            output = Path(directory) / "results"
            report = paper_trade_report(str(logger.path), str(output))
            self.assertEqual(report["logged_orders"], 2)
            self.assertEqual(report["matched_closed_trades"], 1)
            self.assertEqual(report["total_pl"], 1.0)
            self.assertTrue((output / "paper_summary.json").exists())
            self.assertTrue((output / "paper_trades.csv").exists())

    def test_options_are_excluded_from_stock_report_and_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            result = reconcile_filled_orders([
                order("ob", "2026-01-01", "PFE260918C00025000", "buy", 1, 1),
                order("os", "2026-01-02", "PFE260918C00025000", "sell", 1, 2),
                order("sb", "2026-01-01", "ABC", "buy", 1, 10),
                order("ss", "2026-01-02", "ABC", "sell", 1, 11),
            ], logger)
            self.assertEqual(result["total"], 2)
            report = paper_trade_report(str(logger.path), starting_capital=100)
            self.assertEqual(report["total_pl"], 1.0)
            self.assertEqual(report["realized_return_percent"], 0.01)

    def test_shared_account_orders_are_filtered_to_configured_universe(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            result = reconcile_filled_orders([
                order("stock-b", "2026-01-01", "AAPL", "buy", 1, 100),
                order("stock-s", "2026-01-02", "AAPL", "sell", 1, 110),
                order("etf-b", "2026-01-01", "XLP", "buy", 1, 80),
                order("crypto-b", "2026-01-01", "BTC/USD", "buy", 1, 50000),
            ], logger, allowed_symbols={"AAPL"})

            self.assertEqual(result, {"imported": 2, "updated": 0, "total": 2})
            self.assertEqual({row["symbol"] for row in logger.read()}, {"AAPL"})
            report = paper_trade_report(
                str(logger.path), allowed_symbols={"AAPL"}, starting_capital=1000
            )
            self.assertEqual(report["logged_orders"], 2)
            self.assertEqual(report["total_pl"], 10.0)

    def test_report_excludes_existing_foreign_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            reconcile_filled_orders([
                order("stock-b", "2026-01-01", "AAPL", "buy", 1, 100),
                order("stock-s", "2026-01-02", "AAPL", "sell", 1, 110),
                order("etf-b", "2026-01-01", "XLP", "buy", 1, 80),
                order("etf-s", "2026-01-02", "XLP", "sell", 1, 70),
            ], logger)

            report = paper_trade_report(str(logger.path), allowed_symbols={"AAPL"})
            self.assertEqual(report["logged_orders"], 2)
            self.assertEqual(report["total_pl"], 10.0)

    def test_report_summarizes_execution_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TradeLogger(directory)
            logger.log(symbol="ABC", side="buy", qty=1, entry_price=10,
                       expected_price=9.99, slippage_bps=10, slippage_dollars=.01,
                       fill_latency_ms=100, order_id="b")
            logger.log(symbol="ABC", side="sell", qty=1, entry_price=10, exit_price=11,
                       realized_pl=1, expected_price=11.01, slippage_bps=9,
                       slippage_dollars=.01, fill_latency_ms=200, order_id="s")
            quality = paper_trade_report(str(logger.path))["execution_quality"]
            self.assertEqual(quality["measured_orders"], 2)
            self.assertAlmostEqual(quality["average_slippage_bps"], 9.5)
            self.assertAlmostEqual(quality["total_slippage_dollars"], .02)
            self.assertAlmostEqual(quality["average_fill_latency_ms"], 150)

    def test_pending_exit_is_persisted_and_cleared_when_sold(self):
        with tempfile.TemporaryDirectory() as directory:
            state = BotState(directory)
            state.set_pending_exit("ABC", "order-1", "hard_stop")
            reloaded = BotState(directory)
            self.assertEqual(reloaded.pending_exit("ABC")["order_id"], "order-1")
            self.assertEqual(reloaded.pending_exit("ABC")["reason"], "hard_stop")
            reloaded.mark_sold("ABC")
            self.assertEqual(reloaded.pending_exit("ABC"), {})


if __name__ == "__main__":
    unittest.main()
