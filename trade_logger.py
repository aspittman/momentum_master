from __future__ import annotations

import csv
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRADE_FIELDS = [
    "timestamp",
    "symbol",
    "side",
    "qty",
    "notional",
    "entry_price", "exit_price", "realized_pl", "realized_pl_percent",
    "entry_score", "entry_reason", "exit_reason", "atr_at_entry", "atr_at_exit",
    "ema20", "ema50", "macd", "macd_signal", "macd_histogram",
    "relative_strength_score", "volume_ratio", "holding_duration",
    "expected_price", "slippage_bps", "slippage_dollars",
    "submitted_at", "filled_at", "fill_latency_ms",
    "order_id",
]


def execution_quality_fields(side: str, qty: float, expected_price: float,
                             fill_price: float) -> dict[str, float]:
    """Return positive values for adverse execution and negative for improvement."""
    direction = 1.0 if side.lower() == "buy" else -1.0
    price_difference = direction * (fill_price - expected_price)
    return {
        "expected_price": expected_price,
        "slippage_bps": price_difference / expected_price * 10_000,
        "slippage_dollars": qty * price_difference,
    }


class TradeLogger:
    def __init__(self, log_dir: str = "logs") -> None:
        self.path = Path(log_dir) / "trades.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            with self.path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                existing_fields = reader.fieldnames or []
                existing_rows = list(reader)
            if existing_fields != TRADE_FIELDS:
                if set(existing_fields).issubset(TRADE_FIELDS):
                    # Additive schema upgrades preserve the active ledger and
                    # leave historical quality fields blank when unknowable.
                    self.replace(existing_rows)
                else:
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    shutil.move(self.path, self.path.with_name(f"trades_legacy_{stamp}.csv"))
        if not self.path.exists():
            with self.path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
                writer.writeheader()

    def log(self, **kwargs: Any) -> None:
        row = {field: kwargs.get(field, "") for field in TRADE_FIELDS}
        row["timestamp"] = row["timestamp"] or datetime.now(timezone.utc).isoformat()
        with self.path.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writerow(row)

    def read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as handle:
            return list(csv.DictReader(handle))

    def replace(self, rows: list[dict[str, Any]]) -> None:
        """Atomically replace the log after broker reconciliation."""
        temporary = self.path.with_suffix(".csv.tmp")
        with temporary.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writeheader()
            for values in rows:
                writer.writerow({field: values.get(field, "") for field in TRADE_FIELDS})
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.path)
