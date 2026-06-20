# Honest day-by-day BTC profit report

- **Data**: REAL Coin Metrics BTC/USD daily, 2025-04-19 → 2026-05-23 (400 days)
- **Price**: $85,125 → $76,620 (buy & hold -10.0%)
- **Costs**: 25bps/leg fee + 5bps slippage = 60bps round-trip (Bitkub-style taker)
- **Tuning**: grid-search bracket on in-sample 280d, verify out-of-sample 120d (no lookahead)

## 1) Strategy re-tuning (all strategies) — honest out-of-sample

| strategy | best bracket (tp/sl/hold) | IS %/day | OOS %/day | OOS net% | kept? |
|---|---|---:|---:|---:|:--:|
| trend_following | tp=500 sl=800 hold=20 | 0.035% | +0.018% | +2.2% | ✅ |
| momentum_ls | tp=3000 sl=150 hold=40 | 0.020% | -0.028% | -3.3% | ❌ |
| reversion_ls | tp=3000 sl=800 hold=80 | 0.041% | +0.054% | +6.8% | ✅ |
| breakout_ls | tp=2000 sl=150 hold=10 | 0.002% | +0.032% | +3.9% | ✅ |
| range_reversion | tp=500 sl=800 hold=80 | 0.008% | -0.037% | -4.3% | ❌ |

**Kept for the live ensemble:** trend_following, reversion_ls, breakout_ls

## 2) Day-by-day P&L — last 14 days (after fees)

| date | BTC close | signal | position | event | fees ฿ | day P&L ฿ | day % | equity ฿ | cum % |
|---|---:|:--:|:--:|:--|---:|---:|---:|---:|---:|
| 2026-05-10 | 82,257 | BUY | LONG | OPEN/LONG | 150 | -150 | -0.15% | 99,850 | -0.15% |
| 2026-05-11 | 81,715 | HOLD | LONG | HOLD | 0 | -329 | -0.33% | 99,521 | -0.48% |
| 2026-05-12 | 80,526 | HOLD | LONG | HOLD | 0 | -723 | -0.73% | 98,798 | -1.20% |
| 2026-05-13 | 79,292 | HOLD | FLAT | CLOSE/STOP | 145 | -894 | -0.91% | 97,903 | -2.10% |
| 2026-05-14 | 81,176 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-15 | 79,063 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-16 | 78,164 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-17 | 77,498 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-18 | 76,976 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-19 | 76,807 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-20 | 77,408 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-21 | 77,595 | HOLD | FLAT | — | 0 | +0 | +0.00% | 97,903 | -2.10% |
| 2026-05-22 | 75,568 | SELL | SHORT | OPEN/SHORT | 147 | -147 | -0.15% | 97,756 | -2.24% |
| 2026-05-23 | 76,620 | HOLD | SHORT | HOLD | 0 | -682 | -0.70% | 97,075 | -2.93% |

## 3) Verdict vs the 2-5%/day target

- Window cumulative after fees: **-2.93%** over 14 days
- Average day: **-0.211%/day**  ·  best **+0.00%**  ·  worst **-0.91%**
- Up days: **0/14**
- Days that actually hit **≥ 2%**: **0/14**

> **The honest truth:** 2-5%/day compounded is **+137,641%+ per year**. No real strategy on real BTC does this. The numbers above are what the tuned, fee-charged system *actually* produced on real prices — not a promise.
## 4) Every 2-week window across the out-of-sample year (not cherry-picked)

| 2-week window | net % after fees | avg %/day | up days | hit ≥2%/day |
|---|---:|---:|---:|---:|
| 2026-01-24 → 2026-02-06 | -2.75% | -0.193% | 2/14 | 1/14 |
| 2026-02-07 → 2026-02-20 | +1.18% | +0.086% | 5/14 | 0/14 |
| 2026-02-21 → 2026-03-06 | -0.12% | +0.004% | 5/14 | 3/14 |
| 2026-03-07 → 2026-03-20 | -2.19% | -0.156% | 1/14 | 0/14 |
| 2026-03-21 → 2026-04-03 | -0.85% | -0.060% | 3/14 | 0/14 |
| 2026-04-04 → 2026-04-17 | +1.28% | +0.096% | 7/14 | 1/14 |
| 2026-04-18 → 2026-05-01 | -2.49% | -0.178% | 4/14 | 0/14 |
| 2026-05-02 → 2026-05-15 | +1.38% | +0.099% | 7/14 | 0/14 |

- Out-of-sample full period: **-5.39%** over 120 days (≈ -0.046%/day)
- 2-week windows that were profitable: **3/8** (best +1.38%, worst -2.75%)
- 2-week windows that averaged ≥ 2%/day: **0/8**

