from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRADE_FIELDS = [
    "timestamp",
    "symbol",
    "side",
    "qty",
    "notional",
    "price",
    "reason",
    "order_id",
    "score",
    "pnl",
]


class TradeLogger:
    def __init__(self, log_dir: str = "logs") -> None:
        self.path = Path(log_dir) / "trades.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
