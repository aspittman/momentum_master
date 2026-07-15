# MomentumMaster

MomentumMaster is a stock-only short-term momentum trading bot. It ranks liquid individual stocks by accelerating EMA/MACD momentum, relative strength versus SPY, and volume. It buys only the strongest candidates in a healthy market and exits quickly using a ratcheting 1.5× ATR stop, EMA 20/MACD momentum-fade exits, and a 5% emergency stop.

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

Signal decisions use completed bars and execute at the next bar's open. Results, the equity curve, and trades are saved under `backtest_results/`.

Parameter comparison (80 combinations, with no automatic winner selection):

```bash
python backtester.py --start 2024-01-01 --end 2025-12-31 --compare-parameters
```

Treat the supplied comparison period as out-of-sample; do not reuse the training period used to choose candidates or settings. Optional sequential walk-forward reporting is available with `--walk-forward --train-days 365 --test-days 90` and explicitly saves in-sample and out-of-sample results.

Important `.env` controls include `MAX_NEW_BUYS_PER_CYCLE`, `ATR_WINDOW`, `ATR_TRAILING_MULTIPLIER`, `HARD_STOP_PERCENT`, `ENABLE_EMA20_EXIT`, `ENABLE_MACD_BEARISH_EXIT`, `ENABLE_MARKET_REGIME_FILTER`, `RELATIVE_STRENGTH_LOOKBACK`, `MIN_VOLUME_RATIO`, and `COOLDOWN_SECONDS`. The defaults implement the short-term stock momentum profile described above.
