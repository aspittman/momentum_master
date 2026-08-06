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
    risk_per_trade_percent: float = _float("RISK_PER_TRADE_PERCENT", 0.005)
    max_candidates_per_cycle: int = _int("MAX_CANDIDATES_PER_CYCLE", 10)
    max_new_buys_per_cycle: int = _int("MAX_NEW_BUYS_PER_CYCLE", 2)
    max_positions_per_sector: int = _int("MAX_POSITIONS_PER_SECTOR", 2)

    max_daily_loss_percent: float = _float("MAX_DAILY_LOSS_PERCENT", 0.02)
    max_weekly_loss_percent: float = _float("MAX_WEEKLY_LOSS_PERCENT", 0.05)
    max_drawdown_percent: float = _float("MAX_DRAWDOWN_PERCENT", 0.08)
    max_consecutive_losses: int = _int("MAX_CONSECUTIVE_LOSSES", 4)

    ema_fast: int = _int("EMA_FAST", 20)
    ema_slow: int = _int("EMA_SLOW", 50)
    macd_fast: int = _int("MACD_FAST", 12)
    macd_slow: int = _int("MACD_SLOW", 26)
    macd_signal: int = _int("MACD_SIGNAL", 9)
    atr_length: int = _int("ATR_WINDOW", _int("ATR_LENGTH", 14))
    atr_multiplier: float = _float("ATR_TRAILING_MULTIPLIER", _float("ATR_MULTIPLIER", 1.5))
    hard_stop_percent: float = _float("HARD_STOP_PERCENT", 0.05)
    enable_ema20_exit: bool = _bool("ENABLE_EMA20_EXIT", True)
    enable_macd_bearish_exit: bool = _bool("ENABLE_MACD_BEARISH_EXIT", True)

    cooldown_seconds: int = _int("COOLDOWN_SECONDS", 3600)
    volume_average_length: int = _int("VOLUME_AVERAGE_WINDOW", _int("VOLUME_AVERAGE_LENGTH", 20))
    min_volume_ratio: float = _float("MIN_VOLUME_RATIO", 1.0)
    relative_strength_lookback: int = _int("RELATIVE_STRENGTH_LOOKBACK", 20)
    require_volume_confirmation: bool = _bool("ENABLE_VOLUME_CONFIRMATION", True)
    require_relative_strength: bool = _bool("ENABLE_RELATIVE_STRENGTH", True)
    require_market_regime: bool = _bool("ENABLE_MARKET_REGIME_FILTER", True)

    market_ma_fast: int = _int("MARKET_MA_FAST", 50)
    market_ma_slow: int = _int("MARKET_MA_SLOW", 200)

    use_bollinger_confirmation: bool = _bool("ENABLE_BOLLINGER_EXTENSION_FILTER", False)
    bollinger_length: int = _int("BOLLINGER_WINDOW", 20)
    bollinger_std: float = _float("BOLLINGER_STD_DEV", 2.0)
    bollinger_max_extension: float = _float("MAX_UPPER_BAND_EXTENSION_PERCENT", 0.03)

    minimum_momentum_score: float = _float("MINIMUM_MOMENTUM_SCORE", 0.0)
    score_weight_relative_strength: float = _float("SCORE_WEIGHT_RELATIVE_STRENGTH", 25.0)
    score_weight_macd_strength: float = _float("SCORE_WEIGHT_MACD_STRENGTH", 20.0)
    score_weight_macd_acceleration: float = _float("SCORE_WEIGHT_MACD_ACCELERATION", 15.0)
    score_weight_ema_distance: float = _float("SCORE_WEIGHT_EMA_DISTANCE", 10.0)
    score_weight_ema_slope: float = _float("SCORE_WEIGHT_EMA_SLOPE", 10.0)
    score_weight_volume: float = _float("SCORE_WEIGHT_VOLUME", 10.0)
    score_weight_price_momentum: float = _float("SCORE_WEIGHT_PRICE_MOMENTUM", 10.0)
    enable_breakout_score: bool = _bool("ENABLE_BREAKOUT_SCORE", True)
    breakout_lookback: int = _int("BREAKOUT_LOOKBACK", 20)
    score_weight_breakout: float = _float("SCORE_WEIGHT_BREAKOUT", 5.0)

    state_dir: str = _str("STATE_DIR", "state")
    log_dir: str = _str("LOG_DIR", "logs")


settings = Settings()
