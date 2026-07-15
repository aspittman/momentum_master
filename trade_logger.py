from __future__ import annotations

import csv
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
    "order_id",
]


class TradeLogger:
    def __init__(self, log_dir: str = "logs") -> None:
        self.path = Path(log_dir) / "trades.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            with self.path.open(newline="") as handle:
                existing_fields = next(csv.reader(handle), [])
            if existing_fields != TRADE_FIELDS:
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
