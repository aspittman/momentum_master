from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import trader
import main
from trade_logger import execution_quality_fields


class TraderSafetyTests(unittest.TestCase):
    def test_account_positions_outside_universe_are_not_managed(self):
        positions = [
            SimpleNamespace(symbol="AAPL", side="long", qty="1"),
            SimpleNamespace(symbol="XLP", side="long", qty="1"),
        ]
        frame = SimpleNamespace(empty=False)
        with patch.object(main, "settings", SimpleNamespace(universe=["AAPL"])), \
             patch.object(main, "get_stock_positions", return_value=positions), \
             patch.object(main, "reconcile_pending_exits") as reconcile, \
             patch.object(main, "already_holding", return_value=True), \
             patch.object(main, "latest_signal_frame", return_value=frame), \
             patch.object(main, "manage_position", return_value=False) as manage, \
             patch.object(main, "print_position"):
            self.assertTrue(main.manage_open_positions())
            reconcile.assert_called_once_with({"AAPL", "XLP"})
            manage.assert_called_once_with("AAPL", frame)

    def test_execution_quality_is_adverse_positive_for_buys_and_sells(self):
        buy = execution_quality_fields("buy", 2, 100, 100.10)
        sell = execution_quality_fields("sell", 2, 100, 99.90)
        self.assertAlmostEqual(buy["slippage_bps"], 10.0)
        self.assertAlmostEqual(sell["slippage_bps"], 10.0)
        self.assertAlmostEqual(buy["slippage_dollars"], 0.20)
        self.assertAlmostEqual(sell["slippage_dollars"], 0.20)

    def test_market_order_notional_is_rounded_to_cents(self):
        filled = SimpleNamespace(
            id="buy-1", filled_at="now", filled_avg_price="100",
            filled_qty="1.2346", submitted_at=None,
        )
        with patch.object(trader, "get_trading_client") as client, \
             patch.object(trader.trade_logger, "log"):
            client.return_value.submit_order.return_value = filled
            trader.place_market_order("AAPL", "buy", notional=123.456789)
        request = client.return_value.submit_order.call_args.args[0]
        self.assertEqual(request.notional, 123.46)

    def test_only_us_equity_positions_are_selected(self):
        positions = [
            SimpleNamespace(symbol="AAPL", asset_class="us_equity"),
            SimpleNamespace(symbol="AAPL260821C00200000", asset_class="us_option"),
            SimpleNamespace(symbol="BTC/USD", asset_class="crypto"),
        ]
        client = SimpleNamespace(get_all_positions=lambda: positions)
        with patch.object(trader, "get_trading_client", return_value=client):
            self.assertEqual([position.symbol for position in trader.get_stock_positions()], ["AAPL"])

    def test_short_position_is_not_treated_as_long(self):
        self.assertFalse(trader.is_long_position(
            SimpleNamespace(symbol="AAPL", side="short", qty="1")
        ))
        self.assertTrue(trader.is_long_position(
            SimpleNamespace(symbol="MSFT", side="long", qty="1")
        ))

    def test_persisted_pending_exit_blocks_another_order(self):
        with patch.object(trader.bot_state, "pending_exit", return_value={"order_id": "sell-1"}), \
             patch.object(trader, "get_trading_client") as client:
            client.return_value.get_order_by_id.return_value = SimpleNamespace(status="filled")
            self.assertTrue(trader.has_pending_exit("AAPL"))

    def test_immediately_filled_exit_remains_pending_until_position_disappears(self):
        filled = SimpleNamespace(id="sell-1", filled_at="now")
        with patch.object(trader, "has_pending_exit", return_value=False), \
             patch.object(trader, "cancel_protective_stop", return_value=True), \
             patch.object(trader, "has_open_order", return_value=False), \
             patch.object(trader, "place_market_order", return_value=filled), \
             patch.object(trader.bot_state, "entry_metadata", return_value={"price": 10}), \
             patch.object(trader.bot_state, "set_pending_exit") as pending, \
             patch.object(trader, "mark_recently_sold") as sold:
            self.assertTrue(trader.sell_position("AAPL", 1, "test", 11, {}))
            pending.assert_called_once_with("AAPL", "sell-1", "test")
            sold.assert_not_called()

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

    def test_filled_protective_stop_is_not_replaced_for_stale_position(self):
        with patch.object(trader.bot_state, "protective_stop", return_value={
                 "order_id": "stop-1", "stop_price": 95.0,
             }), patch.object(trader, "get_trading_client") as client:
            client.return_value.get_order_by_id.return_value = SimpleNamespace(status="filled")
            self.assertTrue(trader.ensure_protective_stop("AAPL", 1, 96.0))
            client.return_value.submit_order.assert_not_called()
            client.return_value.replace_order_by_id.assert_not_called()

    def test_bot_profit_loss_excludes_other_bots_symbols(self):
        rows = [
            {"timestamp": "2026-08-20T23:59:59Z", "symbol": "AAPL", "realized_pl": "700"},
            {"timestamp": "2026-08-21T00:00:00Z", "symbol": "AAPL", "realized_pl": "100"},
            {"timestamp": "2026-08-22T00:00:00Z", "symbol": "XLP", "realized_pl": "900"},
        ]
        positions = [
            SimpleNamespace(symbol="AAPL", unrealized_pl="25"),
            SimpleNamespace(symbol="SPY", unrealized_pl="500"),
        ]
        configured = SimpleNamespace(universe=["AAPL"], max_total_capital=2500)
        with patch.object(trader, "settings", configured), \
             patch.object(trader.trade_logger, "read", return_value=rows):
            total, gain_loss = trader.bot_profit_loss(positions)
        self.assertEqual(total, 125.0)
        self.assertEqual(gain_loss, 0.05)

    def test_account_info_prints_bot_specific_gain_loss(self):
        client = Mock()
        client.get_account.return_value = SimpleNamespace(equity="100000", buying_power="50000")
        client.get_all_positions.return_value = []
        with patch.object(trader, "get_trading_client", return_value=client), \
             patch.object(trader, "bot_profit_loss", return_value=(55.5, 0.0222)), \
             patch("builtins.print") as output:
            trader.print_account_info()
        output.assert_any_call(
            "MomentumMaster Gain/Loss Since Aug 21, 2026: +2.22% (+55.50)"
        )


if __name__ == "__main__":
    unittest.main()
