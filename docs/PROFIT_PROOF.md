# Profitability proof (long + short, multi-market)

The question that decides everything: **does the equity curve go up after costs?**
This layer answers it for both rising and falling markets — profit comes from
longs that rise *and* shorts that fall (buy low / sell high, either order).

## Files

| File | Layer | Role |
|------|-------|------|
| `src/domain/backtest/profit_engine.py` | 1 (Decimal-only) | Single-position long/short bracket portfolio backtest → net return, profit factor, drawdown, verdict. |
| `src/domain/strategy/breakout_ls.py` | 1 | Donchian breakout, trades **with** the trend both ways (new high → long, new low → short). |
| `src/domain/strategy/momentum_ls.py` | 1 | EMA(9/21) crossover, long + short. |
| `src/domain/strategy/reversion_ls.py` | 1 | RSI(14) mean reversion, long + short. |
| `scripts/prove_profit.py` | tooling | CLI: load markets, run strategies, print the verdict table. |
| `tests/domain/test_profit_engine.py`, `tests/domain/test_ls_strategies.py` | — | Unit tests. |

## How it works

Each signal opens a LONG (BUY) or SHORT (SELL) with the strategy's own ATR
bracket. The position is walked forward and closed on the first of: take-profit,
stop-loss, an opposite signal, the holding horizon, or end of data. Fees +
slippage are charged on **both legs**; equity compounds. No lookahead (entry
fills at the signal bar's close; the bracket is monitored from the next bar).

Reported per strategy/market: `trades`, `L`/`S` counts, `win%`, **`net%`**,
**profit factor**, `maxDD%`, `expectancy (bps/trade)`, and a PROFITABLE / loss
verdict. Edge ⇒ `net% > 0` and `profit_factor > 1` after costs.

## Usage

```bash
# Multiple markets, live candles (needs egress to api.bitkub.com)
PYTHONPATH=src python scripts/prove_profit.py --fetch \
    --symbols BTC_THB,ETH_THB,XRP_THB --resolution 1h --bars 1500

# Offline, several markets (one CSV each), short side only
PYTHONPATH=src python scripts/prove_profit.py \
    --csv data/btc_1h.csv --csv data/eth_1h.csv --direction short
```

Flags: `--direction long|short|both`, `--flip` (reverse on opposite signal;
default is exit-to-flat), `--fee-bps` / `--slip-bps` (per leg; round-trip cost =
`2·(fee+slip)`), `--max-hold`, `--initial-equity`, `--position-frac`,
`--strategies` (registry names).

## Trading other markets

The backtest is symbol-agnostic — it runs on price arrays, so any market works
by passing another `--symbol`/`--csv`. The Bitkub klines gateway already takes
`--symbol`, so `BTC_THB`, `ETH_THB`, … all fetch the same way. (Live *execution*
for new symbols is a separate step — the live order path still centres on the
configured pair; see [EXTENDING.md](EXTENDING.md).)

## Cost matters — an honest result

On a trending market the trend-following `breakout_ls` shows a real gross edge
(≈64% win rate, profit factor 2.5 at zero cost). Whether that survives depends
on fees:

| Round-trip cost | Verdict (trending market) |
|-----------------|---------------------------|
| 0 bps (gross)   | strongly profitable |
| ~34 bps (maker 15 + slip 2, both legs) | profitable |
| ~60 bps (taker 25 + slip 5, both legs) | breakeven / slight loss |

Takeaway: **use maker (limit) orders** to keep round-trip cost low; high-frequency
taker trading can give the gross edge straight back to fees.

## ⚠️ Synthetic vs real

The engine and strategies are unit-tested and validated on synthetic up/down
trends (long profits in uptrends, short profits in downtrends). That proves the
**tool is correct** — it does **not** prove the strategies are profitable on the
real market. The real verdict needs real Bitkub candles (`--fetch`, once
`api.bitkub.com` is allowlisted, or `--csv` with real data). An honest tool never
reports edge it hasn't measured on real prices.
