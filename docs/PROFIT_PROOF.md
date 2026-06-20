# Profitability proof (long + short, multi-market)

> ## Can you prove it makes money 100%? — No. Nobody can.
> No trading system can guarantee profit: markets are non-stationary and past
> results never bind the future. Any tool that prints "100% guaranteed profit"
> is lying (and would violate this repo's own honesty guard). What we provide is
> the strongest **honest** evidence: out-of-sample testing, statistical
> significance, and Monte-Carlo outcome distributions — *confidence*, never
> certainty. Size positions for the bad-luck case, always.

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

## Confidence, not certainty — `validate_profit.py`

`scripts/validate_profit.py` is the rigorous validator. It runs three independent
checks and prints a probabilistic verdict (never "100%"):

1. **Out-of-sample** — observes on the first `--split` (default 70%) of the data,
   then *tests on the unseen rest*. An edge that disappears OOS was overfit.
2. **Statistical significance** (`src/domain/backtest/statistics.py`) — the
   t-statistic and 95% confidence interval of the OOS per-trade return. `t > 1.96`
   means the mean return is distinguishable from zero at ~95%.
3. **Monte Carlo** — bootstraps the realised trades thousands of times to get the
   *distribution* of outcomes: probability of ending profitable, median, and the
   bad-luck 5th-percentile / worst-case return.

```bash
PYTHONPATH=src python scripts/validate_profit.py --csv data/btc_1h.csv \
    --strategies breakout_ls --split 0.7 --mc-runs 2000
```

Verdict ladder: **HIGH** = profitable OOS *and* `t > 1.96` *and* ≥95% of Monte
Carlo runs profitable; **MODERATE** = OOS profitable with one of the two strong
signals; **WEAK / likely luck**; **NO edge**. Even HIGH is not a guarantee.

## Real BTC history, by regime, per agent — `backtest_history.py`

`scripts/backtest_history.py` runs every registered strategy over the **real**
long BTC/USD history (Coin Metrics daily reference price, ~2010→today, fetched
from a public GitHub dataset via `src/infrastructure/gateway/coinmetrics.py`) and
reports, **per market regime** (UPTREND / DOWNTREND / RANGE):

- a per-agent table (trades, win%, net%, profit factor, max drawdown, expectancy);
- **what each agent captures** — average return per trade (bps) split by regime,
  so you can see e.g. trend-followers earn in uptrends while mean-reversion earns
  on bear-market bounces;
- a confidence verdict (out-of-sample + significance + Monte-Carlo on the OOS
  trades).

```bash
PYTHONPATH=src python scripts/backtest_history.py --direction both     # fetch live
PYTHONPATH=src python scripts/backtest_history.py --csv data/btc_daily.csv
```

### What 15.8 years of real BTC says (honest finding)

- Across the **whole** history some strategies look very profitable, but that is
  dominated by **unrepeatable** 2011-era 100× moves.
- On the **out-of-sample** recent slice, **no strategy shows a statistically
  significant edge** (all t < 2) — a few are marginally positive but within luck.
- The regime breakdown is the durable signal: breakout/trend-following capture
  **uptrends**, RSI reversion captures **downtrend bounces**, and most edge
  evaporates in **range** after costs.

Takeaway: this is exactly why the tool exists — it stops you deploying a strategy
that looks great in-sample but has no real forward edge. Regime-aware selection
(use the trend-follower in trends, reversion in chop) is where the honest edge is.

## ⚠️ Synthetic vs real

The engine and strategies are unit-tested and validated on synthetic up/down
trends (long profits in uptrends, short profits in downtrends). That proves the
**tool is correct** — it does **not** prove the strategies are profitable on the
real market. The real verdict needs real Bitkub candles (`--fetch`, once
`api.bitkub.com` is allowlisted, or `--csv` with real data). An honest tool never
reports edge it hasn't measured on real prices.
