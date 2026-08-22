from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import pandas as pd

from analytics import load_trades, summarize_trades
from trade_logger import TRADE_FIELDS, TradeLogger
from risk import is_option_symbol


def _value(value: Any) -> str:
    return "" if value is None else str(value)


def _side(order: Any) -> str:
    value = getattr(order, "side", "")
    return str(getattr(value, "value", value)).lower()


def _filled_order_row(order: Any) -> dict[str, Any] | None:
    qty = float(getattr(order, "filled_qty", None) or 0)
    price = float(getattr(order, "filled_avg_price", None) or 0)
    if qty <= 0 or price <= 0:
        return None
    side = _side(order)
    if side not in {"buy", "sell"}:
        return None
    timestamp = getattr(order, "filled_at", None) or getattr(order, "submitted_at", None)
    row = {
        "timestamp": _value(timestamp), "symbol": _value(getattr(order, "symbol", "")).upper(),
        "side": side, "qty": qty, "notional": qty * price,
        "entry_price" if side == "buy" else "exit_price": price,
        "submitted_at": _value(getattr(order, "submitted_at", None)),
        "filled_at": _value(getattr(order, "filled_at", None)),
        "order_id": _value(getattr(order, "id", "")),
    }
    submitted, filled = getattr(order, "submitted_at", None), getattr(order, "filled_at", None)
    try:
        row["fill_latency_ms"] = (filled - submitted).total_seconds() * 1000
    except (TypeError, AttributeError):
        pass
    return row


def _apply_fifo_pnl(rows: list[dict[str, Any]]) -> None:
    lots: dict[str, deque[list[float]]] = defaultdict(deque)
    for row in rows:
        symbol, side = str(row.get("symbol", "")), str(row.get("side", "")).lower()
        try:
            qty = float(row.get("qty") or 0)
            price = float(row.get("entry_price" if side == "buy" else "exit_price") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0 or price <= 0:
            continue
        if side == "buy":
            lots[symbol].append([qty, price])
            continue
        if side != "sell":
            continue
        # Always recompute derived sell fields. An unmatched sell (for example,
        # an accidental short) must not retain locally estimated long P/L.
        row["entry_price"] = ""
        row["realized_pl"] = ""
        row["realized_pl_percent"] = ""
        remaining, cost = qty, 0.0
        while remaining > 1e-12 and lots[symbol]:
            lot = lots[symbol][0]
            used = min(remaining, lot[0])
            cost += used * lot[1]
            remaining -= used
            lot[0] -= used
            if lot[0] <= 1e-12:
                lots[symbol].popleft()
        matched = qty - remaining
        if matched > 1e-12 and remaining <= 1e-12:
            average_entry = cost / matched
            row["entry_price"] = average_entry
            row["realized_pl"] = matched * (price - average_entry)
            row["realized_pl_percent"] = price / average_entry - 1


def _allowed(symbol: str, allowed_symbols: set[str] | list[str] | tuple[str, ...] | None) -> bool:
    if allowed_symbols is None:
        return True
    return symbol.upper() in {str(item).upper() for item in allowed_symbols}


def reconcile_filled_orders(orders: list[Any], logger: TradeLogger,
                            allowed_symbols: set[str] | list[str] | tuple[str, ...] | None = None
                            ) -> dict[str, int]:
    """Merge filled broker orders into the CSV, keyed by immutable order ID."""
    existing = logger.read()
    by_id = {row.get("order_id", ""): row for row in existing if row.get("order_id")}
    imported = updated = 0
    for order in orders:
        broker_row = _filled_order_row(order)
        if broker_row is None:
            continue
        symbol = str(broker_row["symbol"])
        if is_option_symbol(symbol) or not _allowed(symbol, allowed_symbols):
            continue
        order_id = str(broker_row["order_id"])
        previous = by_id.get(order_id)
        if previous is None:
            previous = {field: "" for field in TRADE_FIELDS}
            existing.append(previous)
            by_id[order_id] = previous
            imported += 1
        else:
            updated += 1
        previous.update(broker_row)
    existing.sort(key=lambda row: str(row.get("timestamp", "")))
    _apply_fifo_pnl(existing)
    logger.replace(existing)
    total = sum(
        _allowed(str(row.get("symbol", "")), allowed_symbols)
        and not is_option_symbol(str(row.get("symbol", "")))
        for row in existing
    )
    return {"imported": imported, "updated": updated, "total": total}


def sync_from_alpaca(client: Any, logger: TradeLogger,
                     allowed_symbols: set[str] | list[str] | tuple[str, ...] | None = None
                     ) -> dict[str, int]:
    from alpaca.common.enums import Sort
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=500, direction=Sort.ASC)
    return reconcile_filled_orders(
        list(client.get_orders(filter=request)), logger, allowed_symbols=allowed_symbols
    )


def paper_trade_report(log_path: str, output_dir: str | None = None,
                       starting_capital: float | None = None,
                       allowed_symbols: set[str] | list[str] | tuple[str, ...] | None = None
                       ) -> dict[str, Any]:
    trades = load_trades(log_path)
    if not trades.empty and "symbol" in trades:
        trades = trades[~trades["symbol"].astype(str).map(is_option_symbol)].copy()
        if allowed_symbols is not None:
            allowed = {str(symbol).upper() for symbol in allowed_symbols}
            trades = trades[trades["symbol"].astype(str).str.upper().isin(allowed)].copy()
    if trades.empty:
        report: dict[str, Any] = {"logged_orders": 0, "buys": 0, "sells": 0,
                                  "matched_closed_trades": 0, "warning": "No paper orders are logged."}
    else:
        sides = trades.get("side", pd.Series(dtype=str)).astype(str).str.lower()
        realized = pd.to_numeric(trades.get("realized_pl"), errors="coerce")
        inventory: dict[str, float] = defaultdict(float)
        matched_indices = []
        for index, row in trades.iterrows():
            symbol, side = str(row.get("symbol", "")), str(row.get("side", "")).lower()
            try:
                qty = float(row.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0
            if side == "buy" and qty > 0:
                inventory[symbol] += qty
            elif side == "sell" and qty > 0 and inventory[symbol] >= qty - 1e-12:
                inventory[symbol] -= qty
                matched_indices.append(index)
        closed = trades.loc[matched_indices].copy()
        closed = closed[pd.to_numeric(closed.get("realized_pl"), errors="coerce").notna()]
        metrics = summarize_trades(closed)
        buys, sells = int((sides == "buy").sum()), int((sides == "sell").sum())
        report = {"logged_orders": int(len(trades)), "buys": buys, "sells": sells,
                  "matched_closed_trades": int(len(closed)), **metrics}
        slippage = pd.to_numeric(
            trades.get("slippage_bps", pd.Series(dtype=float)), errors="coerce"
        ).dropna()
        slippage_dollars = pd.to_numeric(
            trades.get("slippage_dollars", pd.Series(dtype=float)), errors="coerce"
        ).dropna()
        latency = pd.to_numeric(
            trades.get("fill_latency_ms", pd.Series(dtype=float)), errors="coerce"
        ).dropna()
        if not slippage.empty:
            report["execution_quality"] = {
                "measured_orders": int(len(slippage)),
                "average_slippage_bps": float(slippage.mean()),
                "median_slippage_bps": float(slippage.median()),
                "p95_adverse_slippage_bps": float(slippage.quantile(0.95)),
                "total_slippage_dollars": float(slippage_dollars.sum()),
                "average_fill_latency_ms": float(latency.mean()) if not latency.empty else None,
                "p95_fill_latency_ms": float(latency.quantile(0.95)) if not latency.empty else None,
            }
        if starting_capital and starting_capital > 0 and not closed.empty:
            pnl = pd.to_numeric(closed["realized_pl"], errors="coerce").fillna(0)
            equity = starting_capital + pnl.cumsum()
            peaks = equity.cummax().clip(lower=starting_capital)
            report["realized_return_percent"] = float(pnl.sum() / starting_capital)
            report["realized_max_drawdown"] = float((equity / peaks - 1).min())
            report["report_scope"] = "stock orders only; unrealized P/L excluded"
        if sells and not buys:
            report["warning"] = "Sell orders exist, but their corresponding buys are missing from the log."
    if output_dir:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "paper_summary.json").write_text(json.dumps(report, indent=2, default=str))
        trades.to_csv(path / "paper_trades.csv", index=False)
    return report
