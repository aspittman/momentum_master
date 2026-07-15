from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BotState:
    def __init__(self, state_dir: str = "state") -> None:
        self.path = Path(state_dir) / "bot_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "cooldowns": {},
            "highest_prices": {},
            "entry_prices": {},
            "trailing_stops": {},
            "entries": {},
        }
        self.load()

    def load(self) -> None:
        if self.path.exists():
            with self.path.open() as handle:
                loaded = json.load(handle)
            self.data.update(loaded)

    def save(self) -> None:
        with self.path.open("w") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=True)

    def is_on_cooldown(self, symbol: str, cooldown_seconds: int) -> bool:
        sold_at = self.data["cooldowns"].get(symbol)
        if not sold_at:
            return False
        elapsed = datetime.now(timezone.utc).timestamp() - float(sold_at)
        return elapsed < cooldown_seconds

    def mark_sold(self, symbol: str) -> None:
        self.data["cooldowns"][symbol] = datetime.now(timezone.utc).timestamp()
        self.data["highest_prices"].pop(symbol, None)
        self.data["entry_prices"].pop(symbol, None)
        self.data["trailing_stops"].pop(symbol, None)
        self.data["entries"].pop(symbol, None)
        self.save()

    def set_entry(self, symbol: str, price: float, metadata: dict[str, Any] | None = None) -> None:
        self.data["entry_prices"][symbol] = price
        self.data["highest_prices"][symbol] = price
        entry = dict(metadata or {})
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self.data["entries"][symbol] = entry
        self.save()

    def update_highest(self, symbol: str, price: float) -> float:
        highest = max(float(self.data["highest_prices"].get(symbol, price)), price)
        self.data["highest_prices"][symbol] = highest
        self.save()
        return highest

    def update_trailing_stop(self, symbol: str, proposed: float) -> float:
        previous = float(self.data["trailing_stops"].get(symbol, proposed))
        stop = max(previous, proposed)
        self.data["trailing_stops"][symbol] = stop
        self.save()
        return stop

    def entry_metadata(self, symbol: str) -> dict[str, Any]:
        return dict(self.data["entries"].get(symbol, {}))
