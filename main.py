from __future__ import annotations

import sys
import time
import traceback

from config import settings
from indicators import add_indicators
from market_data import download_symbol
from strategy import market_regime_allows_buys, scan_universe
from trader import (
    already_holding,
    buy_candidate,
    ConfigurationError,
    get_open_positions_count,
    get_total_market_value,
    get_trading_client,
    is_in_cooldown,
    manage_position,
    print_account_info,
    print_position,
)


CONFIGURATION_ERROR_EXIT_CODE = 78


def wait_for_market_open() -> None:
    while True:
        clock = get_trading_client().get_clock()
        if clock.is_open:
            return
        print(f"Market is closed. Next open: {clock.next_open}")
        time.sleep(60)


def latest_signal_frame(symbol: str):
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
    return frame


def manage_open_positions() -> None:
    print("\n=== MANAGING OPEN POSITIONS ===")
    sold_this_cycle: set[str] = set()
    symbols = [str(position.symbol) for position in get_trading_client().get_all_positions()]
    for symbol in symbols:
        try:
            if not already_holding(symbol):
                continue
            frame = latest_signal_frame(symbol)
            if frame is None or frame.empty:
                continue
            if symbol not in sold_this_cycle and manage_position(symbol, frame):
                sold_this_cycle.add(symbol)
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
    new_buys = 0
    for candidate in candidates[: settings.max_candidates_per_cycle]:
        if new_buys >= settings.max_new_buys_per_cycle:
            break
        if open_positions >= settings.max_positions:
            print("Max positions reached.")
            break
        if total_capital_used + settings.dollars_per_trade > settings.max_total_capital:
            print("Max total capital reached.")
            break
        if is_in_cooldown(candidate.symbol):
            print(f"{candidate.symbol} is on cooldown. Skipping.")
            continue
        if buy_candidate(candidate):
            new_buys += 1
            open_positions += 1
            total_capital_used += settings.dollars_per_trade
        time.sleep(2)
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
        except ConfigurationError as exc:
            print(f"\nCONFIGURATION ERROR: {exc}")
            sys.exit(CONFIGURATION_ERROR_EXIT_CODE)
        except Exception as exc:
            print("\nBOT CRASHED - restarting soon...")
            print(f"Crash reason: {exc}")
            traceback.print_exc()
            time.sleep(30)
