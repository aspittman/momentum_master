from __future__ import annotations

import time
import traceback

from config import settings
from indicators import add_indicators
from market_data import download_symbol
from strategy import market_regime_allows_buys, scan_universe
from trader import (
    already_holding,
    bot_state,
    buy_candidate,
    get_open_positions_count,
    get_total_market_value,
    get_trading_client,
    manage_position,
    print_account_info,
    print_position,
)


def wait_for_market_open() -> None:
    while True:
        clock = get_trading_client().get_clock()
        if clock.is_open:
            return
        print(f"Market is closed. Next open: {clock.next_open}")
        time.sleep(60)


def latest_atr_and_price(symbol: str) -> tuple[float, float] | None:
    data = download_symbol(symbol, settings.data_period, settings.data_interval)
    if data.empty:
        return None
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
    latest = frame.iloc[-1]
    return float(latest["Close"]), float(latest["atr"])


def manage_open_positions() -> None:
    print("\n=== MANAGING OPEN POSITIONS ===")
    for symbol in settings.universe:
        try:
            if not already_holding(symbol):
                continue
            latest = latest_atr_and_price(symbol)
            if latest is None:
                continue
            price, atr = latest
            manage_position(symbol, price, atr)
            print_position(symbol)
        except Exception as exc:
            print(f"Error managing {symbol}: {exc}")


def can_open_new_buys() -> bool:
    if not settings.require_market_regime:
        return True
    benchmark = download_symbol(settings.benchmark_symbol, settings.data_period, settings.data_interval)
    allowed = market_regime_allows_buys(benchmark, settings.market_ma_fast, settings.market_ma_slow)
    if not allowed:
        print("Market regime is bearish. New buys disabled; existing positions will still be managed.")
    return allowed


def run_cycle() -> None:
    print("\n==============================")
    print("NEW MOMENTUMMASTER CYCLE")
    print("==============================")
    manage_open_positions()

    if not can_open_new_buys():
        print_account_info()
        return

    print("\n=== SCANNING FOR NEW ENTRIES ===")
    candidates = scan_universe(settings.universe, settings)
    print(f"Found {len(candidates)} candidates.")

    open_positions = get_open_positions_count()
    total_capital_used = get_total_market_value()
    for candidate in candidates[: settings.max_candidates_per_cycle]:
        if open_positions >= settings.max_positions:
            print("Max positions reached.")
            break
        if total_capital_used + settings.dollars_per_trade > settings.max_total_capital:
            print("Max total capital reached.")
            break
        if bot_state.is_on_cooldown(candidate.symbol, settings.cooldown_seconds):
            print(f"{candidate.symbol} is on cooldown. Skipping.")
            continue
        buy_candidate(candidate)
        time.sleep(2)
        open_positions = get_open_positions_count()
        total_capital_used = get_total_market_value()
    print_account_info()


def run_bot() -> None:
    wait_for_market_open()
    print("Starting MomentumMaster stock momentum bot...")
    while True:
        run_cycle()
        time.sleep(settings.scan_interval_seconds)


if __name__ == "__main__":
    while True:
        try:
            run_bot()
        except KeyboardInterrupt:
            print("\nBot stopped manually.")
            break
        except Exception as exc:
            print("\nBOT CRASHED - restarting soon...")
            print(f"Crash reason: {exc}")
            traceback.print_exc()
            time.sleep(30)
