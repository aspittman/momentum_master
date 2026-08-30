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

`launcher.py` restarts the bot after unexpected crashes. Trades are logged to `logs/trades.csv`, and runtime state is stored under `state/`. Filled stock entries receive a broker-side day stop that is restored or ratcheted as the bot runs. Stop orders reduce intraday risk but cannot guarantee the stop price when a stock gaps through it.

MomentumMaster only manages long positions whose symbols are in its configured
`UNIVERSE`. Other positions in the same Alpaca account still count toward account
exposure limits, but the bot will not sell them or attach protective stops to
them. A single-instance lock also prevents two MomentumMaster processes from
submitting orders concurrently.

The account summary includes a MomentumMaster-only gain/loss beginning August 21,
2026, after the shared-account reporting fix. It combines realized P/L since that
date with unrealized P/L for current positions in its configured universe,
expressed against `MAX_TOTAL_CAPITAL`.

To reconcile the log with Alpaca's filled paper orders and produce a separate
paper-performance report:

```bash
python backtester.py --paper-trades --sync-paper-trades
```

This writes `backtest_results/paper_trades.csv` and `paper_summary.json`. Re-running
the command is safe: broker orders are merged by order ID. Without
`--sync-paper-trades`, the report uses the local log and does not contact Alpaca.

## Backtest

```bash
python backtester.py --start 2022-01-01 --end 2025-12-31
```

Signal decisions use completed bars and execute at the next bar's open. Protective stops fill at the configured stop when the daily range touches it, or at the open when price gaps through it. Remaining holdings are marked out at the final close. Results, the equity curve, and the complete buy/sell ledger are saved under `backtest_results/`.

Parameter comparison (80 combinations, with no automatic winner selection):

```bash
python backtester.py --start 2024-01-01 --end 2025-12-31 --compare-parameters
```

Treat the supplied comparison period as out-of-sample; do not reuse the training period used to choose candidates or settings. Optional sequential walk-forward reporting is available with `--walk-forward --train-days 365 --test-days 90` and explicitly saves in-sample and out-of-sample results.

Important `.env` controls include `MAX_NEW_BUYS_PER_CYCLE`, `ATR_WINDOW`, `ATR_TRAILING_MULTIPLIER`, `HARD_STOP_PERCENT`, `ENABLE_EMA20_EXIT`, `ENABLE_MACD_BEARISH_EXIT`, `ENABLE_MARKET_REGIME_FILTER`, `RELATIVE_STRENGTH_LOOKBACK`, `MIN_VOLUME_RATIO`, and `COOLDOWN_SECONDS`. The defaults implement the short-term stock momentum profile described above.

## Risk controls

Entries are sized from the initial stop distance so the default maximum planned
loss is 0.5% of configured capital, capped at `$500` per position. New entries
are automatically suspended after a 2% daily realized loss, 5% weekly realized
loss, 8% realized peak-to-trough drawdown, or four consecutive stock losses.
Existing positions continue to be managed. New entries are also blocked whenever
market data or a protective stop for any held stock cannot be verified.

The related `.env` controls are `RISK_PER_TRADE_PERCENT`,
`MAX_DAILY_LOSS_PERCENT`, `MAX_WEEKLY_LOSS_PERCENT`, `MAX_DRAWDOWN_PERCENT`,
`MAX_CONSECUTIVE_LOSSES`, and `MAX_POSITIONS_PER_SECTOR`. Circuit breakers require
operator review before changing their thresholds. Broker stops reduce risk but
cannot prevent losses caused by overnight gaps or unavailable markets.

Paper reports exclude option contract symbols reconciled from the same Alpaca
account. Broker reconciliation, paper reports, and realized-loss circuit breakers
are restricted to MomentumMaster's configured `UNIVERSE`, so activity from ETF,
crypto, and other-symbol bots sharing the account is excluded. Reports include
realized return and realized drawdown. Unrealized P/L still
requires current broker positions and is explicitly excluded from the report.
New orders also record expected versus filled price, adverse slippage in basis
points and dollars, and fill latency. Positive slippage is adverse for both buys
and sells; negative values represent price improvement. The paper summary reports
average, median, and 95th-percentile adverse slippage so execution can be compared
with the historical stress thresholds.
