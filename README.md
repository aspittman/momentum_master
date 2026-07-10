# MomentumMaster

MomentumMaster is a stock-only short-term momentum trading bot. It ranks liquid individual stocks by accelerating momentum, buys the highest-scoring candidates when the market regime is healthy, and exits with ATR-based risk controls.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Edit `.env` with Alpaca credentials. Paper trading is enabled by default.

## Run

```bash
python launcher.py
```

`launcher.py` restarts the bot after unexpected crashes. Trades are logged to `logs/trades.csv`, and runtime state is stored under `state/`.

## Backtest

```bash
python backtester.py --start 2022-01-01 --end 2025-12-31
```

The backtester reports total trades, win rate, expectancy, profit factor, average win/loss, total P/L, max drawdown, best/worst symbol, and trades by symbol.
