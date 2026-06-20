# P0 — Bracket edge measurement

An **offline, paper-only** tool that measures whether the bracketed strategies
have real edge. It never places an order and never touches the
money/treasury/risk/execution layers — it only *measures*.

## Files

| File | Layer | Role |
|------|-------|------|
| `src/domain/backtest/bracket_engine.py` | 1 (domain, Decimal-only) | Resolves each bracketed entry WIN/LOSS/OPEN; computes win-rate vs breakeven. |
| `src/infrastructure/gateway/bitkub_klines.py` | 3 (infra) | Read-only OHLC fetcher (public Bitkub UDF endpoint) + CSV loader/writer. |
| `scripts/backtest_edge.py` | tooling | CLI runner (`--fetch` / `--csv`, `fixed`/`atr`/`both`). |
| `tests/domain/test_bracket_engine.py` | — | 8 unit tests. |
| `tests/infrastructure/test_bitkub_klines.py` | — | 6 unit tests. |

## The yardstick

A *bracket* is an entry plus a take-profit (TP) and stop-loss (SL). For a trade
costing `cost_bps` round-trip (fees + slippage, both legs):

```
breakeven_rate = (sl_bps + cost_bps) / (tp_bps + sl_bps)
```

A strategy has **positive expectancy only when `win% > breakeven%`** (edge =
YES). For a fixed symmetric bracket the two statements are exactly equivalent;
the engine also reports realised per-trade expectancy in bps so the verdict is
auditable.

Conservative tie-break: within a bar the **stop is tested before the TP**, so a
bar that straddles both levels resolves as a LOSS (matches
`domain.trading.paper`). Entry fills at the signal bar's close; the bracket is
monitored over the next `--max-hold` bars (no same-bar lookahead).

## Usage

```bash
# Live Bitkub candles (needs network egress to api.bitkub.com)
PYTHONPATH=src python scripts/backtest_edge.py --fetch \
    --symbol BTC_THB --resolution 15m --bars 1500 --bracket both \
    --cache-csv data/btc_15m.csv

# Offline from a CSV (ts/open/high/low/close[/volume] columns)
PYTHONPATH=src python scripts/backtest_edge.py --csv data/btc_15m.csv --bracket both
```

Key flags: `--tp-bps` / `--sl-bps` (fixed bracket size), `--fee-bps` /
`--slip-bps` (per-leg cost; round-trip cost = `2·(fee+slip)`), `--max-hold`
(bars), `--cache-csv` (save fetched candles for repeatable offline runs).

### Bracket modes

- `fixed` — impose one symmetric bracket on every entry; `win% > breakeven%` is
  *exactly* positive expectancy. Also emits a `baseline_long` row (blind entries
  spaced by the holding horizon) as a market-drift sanity check.
- `atr`   — honour each strategy's own ATR-derived stop/take; `breakeven%` is the
  per-trade average.
- `both`  — print both tables (default).

## Reading the result

```
strategy          trades win loss open    win%  breakeven%  edge  exp(bps)
trend_following       18   8   10   0  44.44%     80.00%     no     -71.1
```

`edge = YES ⟺ win% > breakeven%`. On pure noise, every strategy should show
`edge = no` with negative expectancy after costs — an honest tool never invents
edge.

## Offline data

If `--fetch` is blocked (e.g. a restricted network egress allowlist), the tool
prints the exact HTTP error and runs identically with `--csv PATH`. Use
`--cache-csv` on a machine that *can* reach Bitkub to capture candles, then
replay them offline.
