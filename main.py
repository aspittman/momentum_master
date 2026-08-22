from __future__ import annotations

import fcntl
import sys
import time
import traceback

from config import settings
from indicators import add_indicators
from market_data import download_symbol
from strategy import market_regime_allows_buys, scan_universe
from risk import evaluate_risk_gate, risk_sized_notional
from universe import sector_for_symbol
from trader import (
    already_holding,
    buy_candidate,
    ConfigurationError,
    get_open_positions_count,
    get_total_market_value,
    get_trading_client,
    get_stock_positions,
    is_in_cooldown,
    is_long_position,
    manage_position,
    print_account_info,
    print_position,
    reconcile_pending_exits,
)


CONFIGURATION_ERROR_EXIT_CODE = 78
ALREADY_RUNNING_EXIT_CODE = 73
_instance_lock = None


def acquire_instance_lock() -> None:
    """Prevent two bot processes from trading the same account concurrently."""
    global _instance_lock
    lock_path = settings.env_file.parent / settings.state_dir / "bot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError("another MomentumMaster process is already running")
    _instance_lock = handle


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


def manage_open_positions() -> bool:
    print("\n=== MANAGING OPEN POSITIONS ===")
    sold_this_cycle: set[str] = set()
    positions = get_stock_positions()
    protection_ok = True
    configured_symbols = {symbol.upper() for symbol in settings.universe}
    all_symbols = {str(position.symbol).upper() for position in positions}
    non_long = [str(position.symbol).upper() for position in positions if not is_long_position(position)]
    if non_long:
        protection_ok = False
        print(f"SAFETY: non-long positions require operator review: {', '.join(sorted(non_long))}")
    unmanaged = sorted(all_symbols - configured_symbols)
    if unmanaged:
        print(
            "ACCOUNT NOTICE: positions outside this bot's universe will not be managed: "
            f"{', '.join(unmanaged)}"
        )
    symbols = {
        str(position.symbol).upper()
        for position in positions
        if is_long_position(position) and str(position.symbol).upper() in configured_symbols
    }
    # Reconcile against every actual account position so an unmanaged holding is
    # never mistaken for a completed MomentumMaster exit.
    reconcile_pending_exits(all_symbols)
    for symbol in symbols:
        try:
            if not already_holding(symbol):
                continue
            frame = latest_signal_frame(symbol)
            if frame is None or frame.empty:
                protection_ok = False
                print(f"SAFETY: no market data for {symbol}; new entries will be blocked.")
                continue
            if symbol not in sold_this_cycle and manage_position(symbol, frame):
                sold_this_cycle.add(symbol)
            print_position(symbol)
        except Exception as exc:
            protection_ok = False
            print(f"Error managing {symbol}: {exc}")
    return protection_ok


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
    if not manage_open_positions():
        print("SAFETY: not all held positions could be verified and managed. New buys disabled.")
        print_account_info()
        return

    from trader import trade_logger
    gate = evaluate_risk_gate(trade_logger.path, settings)
    if not gate.allowed:
        print(f"RISK CIRCUIT BREAKER: new buys disabled ({'; '.join(gate.reasons)}).")
        print_account_info()
        return

    if not can_open_new_buys():
        print_account_info()
        return

    print("\n=== SCANNING FOR NEW ENTRIES ===")
    candidates = scan_universe(settings.universe, settings)
    print(f"Found {len(candidates)} candidates.")

    open_positions = get_open_positions_count()
    total_capital_used = get_total_market_value()
    held_sectors = {}
    for position in get_stock_positions():
        sector = sector_for_symbol(str(position.symbol))
        held_sectors[sector] = held_sectors.get(sector, 0) + 1
    new_buys = 0
    for candidate in candidates[: settings.max_candidates_per_cycle]:
        if new_buys >= settings.max_new_buys_per_cycle:
            break
        if open_positions >= settings.max_positions:
            print("Max positions reached.")
            break
        if is_in_cooldown(candidate.symbol):
            print(f"{candidate.symbol} is on cooldown. Skipping.")
            continue
        sector = sector_for_symbol(candidate.symbol)
        if held_sectors.get(sector, 0) >= settings.max_positions_per_sector:
            print(f"Sector limit reached for {sector}. Skipping {candidate.symbol}.")
            continue
        notional = risk_sized_notional(candidate, settings)
        if notional < 1.0:
            print(f"Risk-sized allocation for {candidate.symbol} is below $1. Skipping.")
            continue
        if total_capital_used + notional > settings.max_total_capital:
            print("Max total capital reached.")
            break
        if buy_candidate(candidate, notional=notional):
            new_buys += 1
            open_positions += 1
            total_capital_used += notional
            held_sectors[sector] = held_sectors.get(sector, 0) + 1
        time.sleep(2)
    print_account_info()


def run_bot() -> None:
    acquire_instance_lock()
    # Recover fills completed while the process was stopped or after an order's
    # brief synchronous wait expired.
    from paper_trades import sync_from_alpaca
    from trader import trade_logger
    result = sync_from_alpaca(get_trading_client(), trade_logger)
    print(f"Paper trade log reconciled ({result['total']} filled orders).")
    print("Starting MomentumMaster stock momentum bot...")
    while True:
        wait_for_market_open()
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
        except RuntimeError as exc:
            if str(exc) == "another MomentumMaster process is already running":
                print(f"\nSAFETY: {exc}.")
                sys.exit(ALREADY_RUNNING_EXIT_CODE)
            print("\nBOT CRASHED - restarting soon...")
            print(f"Crash reason: {exc}")
            traceback.print_exc()
            time.sleep(30)
        except Exception as exc:
            print("\nBOT CRASHED - restarting soon...")
            print(f"Crash reason: {exc}")
            traceback.print_exc()
            time.sleep(30)
