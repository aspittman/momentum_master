from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from universe import UNIVERSE

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _symbols(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return list(default)
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


@dataclass(frozen=True)
class Settings:
    env_file: Path = BASE_DIR / ".env"

    alpaca_api_key: str = _str("ALPACA_API_KEY")
    alpaca_secret_key: str = _str("ALPACA_SECRET_KEY")
    alpaca_paper: bool = _bool("ALPACA_PAPER", True)

    universe: list[str] = field(default_factory=lambda: _symbols("UNIVERSE", UNIVERSE))
    benchmark_symbol: str = _str("BENCHMARK_SYMBOL", "SPY")
    scan_interval_seconds: int = _int("SCAN_INTERVAL_SECONDS", 300)
    data_period: str = _str("DATA_PERIOD", "1y")
    data_interval: str = _str("DATA_INTERVAL", "1d")

    max_positions: int = _int("MAX_POSITIONS", 5)
    max_total_capital: float = _float("MAX_TOTAL_CAPITAL", 2500)
    dollars_per_trade: float = _float("DOLLARS_PER_TRADE", 500)
    max_candidates_per_cycle: int = _int("MAX_CANDIDATES_PER_CYCLE", 10)

    ema_fast: int = _int("EMA_FAST", 20)
    ema_slow: int = _int("EMA_SLOW", 50)
    macd_fast: int = _int("MACD_FAST", 12)
    macd_slow: int = _int("MACD_SLOW", 26)
    macd_signal: int = _int("MACD_SIGNAL", 9)
    atr_length: int = _int("ATR_LENGTH", 14)
    atr_multiplier: float = _float("ATR_MULTIPLIER", 2.0)
    backup_stop_loss_percent: float = _float("BACKUP_STOP_LOSS_PERCENT", 0.05)

    cooldown_seconds: int = _int("COOLDOWN_SECONDS", 3600)
    volume_average_length: int = _int("VOLUME_AVERAGE_LENGTH", 20)
    require_volume_confirmation: bool = _bool("REQUIRE_VOLUME_CONFIRMATION", True)
    require_relative_strength: bool = _bool("REQUIRE_RELATIVE_STRENGTH", True)
    require_market_regime: bool = _bool("REQUIRE_MARKET_REGIME", True)

    market_ma_fast: int = _int("MARKET_MA_FAST", 50)
    market_ma_slow: int = _int("MARKET_MA_SLOW", 200)

    use_bollinger_confirmation: bool = _bool("USE_BOLLINGER_CONFIRMATION", False)
    bollinger_length: int = _int("BOLLINGER_LENGTH", 20)
    bollinger_std: float = _float("BOLLINGER_STD", 2.0)
    bollinger_max_extension: float = _float("BOLLINGER_MAX_EXTENSION", 0.03)

    state_dir: str = _str("STATE_DIR", "state")
    log_dir: str = _str("LOG_DIR", "logs")


settings = Settings()
