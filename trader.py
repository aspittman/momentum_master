from __future__ import annotations

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from config import settings
from state import BotState
from trade_logger import TradeLogger


trading_client: TradingClient | None = None
bot_state = BotState(settings.state_dir)
trade_logger = TradeLogger(settings.log_dir)


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


def get_trading_client() -> TradingClient:
    global trading_client
    if trading_client is None:
        missing = [
            name
            for name, value in {
                "ALPACA_API_KEY": settings.alpaca_api_key,
                "ALPACA_SECRET_KEY": settings.alpaca_secret_key,
            }.items()
            if not value
        ]
        if missing:
            names = " and ".join(missing)
            raise ConfigurationError(f"Set {names} in {settings.env_file} before live or paper trading.")
        trading_client = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            paper=settings.alpaca_paper,
        )
    return trading_client


def get_total_market_value() -> float:
    try:
        return sum(float(position.market_value) for position in get_trading_client().get_all_positions())
    except Exception as exc:
        print(f"Error getting total market value: {exc}")
        return 0.0


def get_open_positions_count() -> int:
    return len(get_trading_client().get_all_positions())


def get_position(symbol: str):
    try:
        return get_trading_client().get_open_position(symbol)
    except APIError:
        return None


def already_holding(symbol: str) -> bool:
    return get_position(symbol) is not None


def place_market_order(
    symbol: str,
    side: str,
    *,
    qty: float | None = None,
    notional: float | None = None,
    reason: str = "",
    score: float | str = "",
    price: float | str = "",
) -> None:
    order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
    request = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        notional=notional,
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    order = get_trading_client().submit_order(request)
    trade_logger.log(
        symbol=symbol,
        side=side.lower(),
        qty=qty or "",
        notional=notional or "",
        reason=reason,
        order_id=getattr(order, "id", ""),
        score=score,
        price=price,
    )
    print(f"Placed {side.upper()} market order for {symbol}")


def buy_candidate(candidate) -> None:
    if already_holding(candidate.symbol):
        print(f"Already holding {candidate.symbol}. Skipping.")
        return
    place_market_order(
        candidate.symbol,
        "buy",
        notional=settings.dollars_per_trade,
        reason="momentum_entry",
        score=candidate.score,
        price=candidate.price,
    )
    bot_state.set_entry(candidate.symbol, candidate.price)


def sell_position(symbol: str, qty: float, reason: str, price: float | None = None) -> None:
    place_market_order(symbol, "sell", qty=qty, reason=reason, price=price or "")
    bot_state.mark_sold(symbol)


def manage_position(symbol: str, latest_price: float, latest_atr: float) -> bool:
    position = get_position(symbol)
    if position is None:
        return False

    qty = float(position.qty)
    entry_price = float(position.avg_entry_price)
    highest = bot_state.update_highest(symbol, latest_price)
    atr_stop = highest - (settings.atr_multiplier * latest_atr)
    backup_stop = entry_price * (1 - settings.backup_stop_loss_percent)
    stop_price = max(atr_stop, backup_stop)

    print(
        f"{symbol}: price={latest_price:.2f}, highest={highest:.2f}, "
        f"ATR stop={atr_stop:.2f}, backup stop={backup_stop:.2f}"
    )
    if latest_price <= stop_price:
        sell_position(symbol, qty, "atr_trailing_stop", latest_price)
        return True
    return False


def print_account_info() -> None:
    account = get_trading_client().get_account()
    print("\n===== ACCOUNT INFO =====")
    print(f"Equity: ${account.equity}")
    print(f"Buying Power: ${account.buying_power}")
    print("========================\n")


def print_position(symbol: str) -> None:
    position = get_position(symbol)
    if position is None:
        return
    print("----- POSITION -----")
    print(f"Symbol: {symbol}")
    print(f"Qty: {position.qty}")
    print(f"Avg Entry: ${position.avg_entry_price}")
    print(f"Current Price: ${position.current_price}")
    print(f"Unrealized P/L: ${position.unrealized_pl}")
    print("--------------------\n")
