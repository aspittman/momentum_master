from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import trader
from trade_logger import execution_quality_fields


class TraderSafetyTests(unittest.TestCase):
    def test_execution_quality_is_adverse_positive_for_buys_and_sells(self):
        buy = execution_quality_fields("buy", 2, 100, 100.10)
        sell = execution_quality_fields("sell", 2, 100, 99.90)
        self.assertAlmostEqual(buy["slippage_bps"], 10.0)
        self.assertAlmostEqual(sell["slippage_bps"], 10.0)
        self.assertAlmostEqual(buy["slippage_dollars"], 0.20)
        self.assertAlmostEqual(sell["slippage_dollars"], 0.20)

    def test_only_us_equity_positions_are_selected(self):
        positions = [
            SimpleNamespace(symbol="AAPL", asset_class="us_equity"),
            SimpleNamespace(symbol="AAPL260821C00200000", asset_class="us_option"),
            SimpleNamespace(symbol="BTC/USD", asset_class="crypto"),
        ]
        client = SimpleNamespace(get_all_positions=lambda: positions)
        with patch.object(trader, "get_trading_client", return_value=client):
            self.assertEqual([position.symbol for position in trader.get_stock_positions()], ["AAPL"])

    def test_persisted_pending_exit_blocks_another_order(self):
        with patch.object(trader.bot_state, "pending_exit", return_value={"order_id": "sell-1"}), \
             patch.object(trader, "get_trading_client") as client:
            client.return_value.get_order_by_id.return_value = SimpleNamespace(status="filled")
            self.assertTrue(trader.has_pending_exit("AAPL"))

    def test_canceled_pending_exit_can_be_retried(self):
        with patch.object(trader.bot_state, "pending_exit", return_value={"order_id": "sell-1"}), \
             patch.object(trader.bot_state, "clear_pending_exit") as clear, \
             patch.object(trader, "get_trading_client") as client:
            client.return_value.get_order_by_id.return_value = SimpleNamespace(status="canceled")
            self.assertFalse(trader.has_pending_exit("AAPL"))
            clear.assert_called_once_with("AAPL")

    def test_protective_stop_is_submitted_and_persisted(self):
        order = SimpleNamespace(id="stop-1")
        with patch.object(trader.bot_state, "protective_stop", return_value={}), \
             patch.object(trader.bot_state, "set_protective_stop") as save, \
             patch.object(trader, "get_trading_client") as client:
            client.return_value.submit_order.return_value = order
            trader.ensure_protective_stop("AAPL", 1.25, 95.004)
            request = client.return_value.submit_order.call_args.args[0]
            self.assertEqual(request.symbol, "AAPL")
            self.assertEqual(request.qty, 1.25)
            self.assertEqual(request.stop_price, 95.0)
            save.assert_called_once_with("AAPL", "stop-1", 95.0)


if __name__ == "__main__":
    unittest.main()
