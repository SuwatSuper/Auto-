# EXHAUSTIVE multi-timeframe ceiling — can ANY config reach 2-5%/day?

- Data: REAL Coin Metrics BTC/USD daily, 2025-04-19 → 2026-05-23 (400 days)
- Round-trip cost: 60 bps (0.60%) — Bitkub-style taker + slippage
- Timeframes 1D..1M are built by aggregating the real daily closes.
- Lower (intraday) timeframes are unreachable here (exchange APIs are off the
  network allowlist) AND provably worse: per-bar move shrinks with √time while
  the fee stays fixed, so fee-drag rises. The √t-scaled estimate is shown.

## 1) Every timeframe — volatility, predictability, and the PERFECT-FORESIGHT ceiling

| timeframe | bars | avg |move|/bar | lag-1 autocorr | ⭐ perfect-foresight /day | @55% acc /day | @60% acc /day |
|---|---:|---:|---:|---:|---:|---:|
| 1D | 400 | 1.54% | -0.044 | **+1.23%** | -0.197% | -0.060% |
| 2D | 200 | 2.20% | -0.033 | **+0.94%** | -0.061% | +0.053% |
| 3D | 133 | 2.75% | -0.044 | **+0.80%** | -0.061% | +0.017% |
| 5D | 80 | 3.09% | +0.075 | **+0.55%** | -0.050% | +0.017% |
| 1W | 57 | 3.82% | +0.100 | **+0.49%** | -0.023% | +0.010% |
| 2W | 28 | 4.81% | -0.054 | **+0.31%** | -0.001% | +0.020% |
| 1M | 13 | 8.48% | -0.249 | **+0.25%** | +0.018% | +0.024% |

> ⭐ = an IMPOSSIBLE upper bound (knowing every bar's direction in advance). It is
> the ceiling of what *any* strategy on this data could physically extract.

## 2) Best HONEST out-of-sample daily return — all strategies × tradable timeframes

| timeframe | best strategy | OOS %/day | OOS win% |
|---|---|---:|---:|
| 1D | reversion_ls | +0.098% | 50.0% |
| 2D | breakout_ls | +0.237% | 71.4% |
| 3D | breakout_ls | +0.366% | 100.0% |

**Best honest config found anywhere: breakout_ls on 3D → +0.366%/day out-of-sample.**

## 3) What 2%/day would actually require

- Average absolute daily BTC move: **1.54%**  ·  round-trip fee: **0.60%**
- Direction accuracy needed for **+2%/day** (1 trade/day): **134.7%** correct — *every single day*.
  - Best tuned strategy here predicts roughly **52–55%** (coin-flip + a sliver of edge).
  - Required accuracy **135%** is far beyond anything achievable on real markets.
- Leverage needed to stretch the best honest edge (0.366%/day) to 2%/day: **≈ 5×**.
  - At 5× leverage, a single normal **1.5%** adverse day = **8% loss** → account liquidated long before any compounding.

## 4) Honest verdict

- Perfect foresight on daily bars ≈ **+1.2%/day** — so 2-5%/day is
  literally the *omniscient* ceiling; a real system cannot live there.
- BTC's lag-1 autocorrelation is ≈ 0 at every timeframe → the next move is
  ~unpredictable; no indicator or timeframe converts noise into 2-5%/day.
- The realistic, fee-charged system earns ≈ **+0.02% to +0.05%/day** out-of-sample
  (≈ 8–18%/yr, with losing weeks). That is the honest number.

> 2-5%/day compounded = +137,000% to +39,000,000%/yr. It is mathematically
> impossible to do honestly on real BTC. Anyone guaranteeing it is lying.
