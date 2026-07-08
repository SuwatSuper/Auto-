"""Tests for set_edge_finder.py v2 (multi-strategy)."""
import numpy as np
import pandas as pd
import pytest
import set_edge_finder as sef

# Unit tests ปิด Friday anchor เป็นค่าเริ่มต้น (มีเทสต์เฉพาะของ mask ด้านล่าง)
sef.FRIDAY_ONLY = False


def _ticker(name, closes):
    n = len(closes)
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"Ticker": name, "Date": dates, "Open": c,
                         "High": c + 2.0, "Low": c - 2.0, "Close": c,
                         "Volume": np.full(n, 1000)})


def _multi(nt=4, n=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.concat([_ticker(f"T{i}", 100 + np.cumsum(rng.normal(0, 1, n))) for i in range(nt)],
                     ignore_index=True)


def test_rsi_bounds():
    up = pd.Series(np.linspace(100, 130, 40))
    assert sef.wilder_rsi(up, 14).dropna().between(0, 100).all()
    assert sef.wilder_rsi(up, 14).dropna().iloc[-1] > 50


def test_rsi_flat_is_50():
    assert (sef.wilder_rsi(pd.Series([10.0]*20), 14).dropna() == 50.0).all()


def test_ema_matches_pandas():
    s = pd.Series(np.arange(1, 30, dtype=float))
    assert np.allclose(sef.ema(s, 10).values, s.ewm(span=10, adjust=False).mean().values)


def test_atr_positive():
    df = _ticker("X", list(np.linspace(100, 120, 40)))
    assert (sef.atr(df["High"], df["Low"], df["Close"], 14).dropna() >= 0).all()


def test_adx_bounded():
    df = _ticker("X", list(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 100))))
    assert sef.adx(df["High"], df["Low"], df["Close"], 14).dropna().between(0, 100).all()


def test_macd_cross_is_bool():
    s = pd.Series(100 + np.cumsum(np.random.default_rng(2).normal(0, 1, 100)))
    assert sef.macd_cross_up(s, 12, 26).dtype == bool


def test_wilson_lb():
    assert sef.wilson_lb(0, 0) == 0.0
    assert sef.wilson_lb(8, 10) < 0.8
    assert sef.wilson_lb(800, 1000) > sef.wilson_lb(8, 10)


def test_precompute_forward_cols():
    data = sef.precompute(_multi(2, 120))
    mh = max(sef.SPACE["hold_days"])
    for k in range(1, mh + 1):
        assert f"H{k}" in data and f"L{k}" in data and f"C{k}" in data
    assert "Entry" in data and "VolSMA20" in data


def test_entry_is_next_open():
    raw = _ticker("X", list(np.linspace(100, 120, 40)))
    data = sef.precompute(raw)
    expected = raw.sort_values("Date")["Open"].shift(-1).values
    got = data.sort_values(["Ticker", "Date"])["Entry"].values
    np.testing.assert_array_equal(got[:-1], expected[:-1])


def test_build_cache_has_all_indicators():
    cache = sef.build_cache(sef.precompute(_multi(3, 200)))
    assert cache["rsi"] and cache["bb"] and cache["ema"] and cache["atr"]
    assert cache["donch"] and cache["macd"]


def test_all_four_families_produce_bool_masks():
    data = sef.precompute(_multi(4, 250, seed=7))
    cache = sef.build_cache(data)
    for fam in [0, 1, 2, 3]:
        p = (fam, 14, 35, 10, 1.5, 20, 10, 50, 0, 3, 5, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
        mask = sef._entry_signal(cache, p)
        assert mask.dtype == bool and len(mask) == len(data)


def test_breakout_fires_on_new_high():
    data = sef.precompute(_ticker("X", list(np.linspace(100, 200, 80))))
    cache = sef.build_cache(data)
    p = (1, 14, 35, 10, 1.5, 10, 10, 50, 0, 3, 5, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    assert sef._entry_signal(cache, p).sum() > 0


def test_evaluate_percent_exit():
    closes = [100.0]*20 + [100, 99, 96, 92, 87] + list(np.linspace(90, 140, 25))
    cache = sef.build_cache(sef.precompute(_ticker("X", closes)))
    p = (0, 7, 45, 10, 1.5, 20, 10, 50, 0, 3, 20, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    r = sef.evaluate(cache, p)
    assert r is not None and 0 <= r["win_rate"] <= 100 and "median_net" in r


def test_evaluate_atr_exit_runs():
    cache = sef.build_cache(sef.precompute(_multi(4, 250, seed=3)))
    p = (0, 14, 45, 10, 1.5, 20, 10, 50, 1, 2, 3, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    r = sef.evaluate(cache, p)
    if r is not None:
        assert 0 <= r["win_rate"] <= 100 and r["n_resolved"] >= 1


def test_evaluate_no_signal_none():
    cache = sef.build_cache(sef.precompute(_ticker("X", [100.0]*80)))
    p = (0, 14, 5, 10, 2.5, 20, 10, 50, 0, 3, 13, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    assert sef.evaluate(cache, p) is None


def test_adx_filter_reduces_signals():
    cache = sef.build_cache(sef.precompute(_multi(5, 300, seed=11)))
    base = (2, 14, 45, 10, 1.5, 20, 10, 50, 0, 3, 5, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    filt = (2, 14, 45, 10, 1.5, 20, 10, 50, 0, 3, 5, 14, 5, 25, 0, 14, 20, 2.0, 2.0, 0, 0)
    r0 = sef.evaluate(cache, base); r1 = sef.evaluate(cache, filt)
    assert (r1["n_signals"] if r1 else 0) <= (r0["n_signals"] if r0 else 0)


def test_iter_combos_unique():
    combos = list(sef.iter_combos(500, seed=1))
    assert len(combos) == len(set(combos)) == 500


def test_iter_combos_deterministic():
    assert list(sef.iter_combos(300, 42)) == list(sef.iter_combos(300, 42))


def test_iter_combos_enumerates_full():
    orig = {k: list(v) for k, v in sef.SPACE.items()}
    try:
        for k in sef.SPACE:
            sef.SPACE[k] = [orig[k][0]]
        sef.SPACE["entry_family"] = [0, 1]
        assert len(list(sef.iter_combos(10_000_000, seed=1))) == 2
    finally:
        for k, v in orig.items():
            sef.SPACE[k] = v


def test_friction_value():
    assert sef.FRICTION_PCT == pytest.approx(0.514, abs=1e-9)


# ---------------------------------------------------------------- v3: limit entry
def _crafted_signal_frame(day1_low, day1_high, later_close, later_high):
    """30 flat bars @100, dip bar close=95 (fires MR signal with rp=7, rt=45,
    bb=(10,1.5)), then fully controlled forward bars."""
    n = 40
    close = [100.0]*30 + [95.0] + [day1_close_placeholder := 99.5] + [later_close]*8
    df = pd.DataFrame({
        "Ticker": "X",
        "Date": pd.date_range("2021-01-01", periods=n, freq="B"),
        "Open": close, "High": close, "Low": close, "Close": close,
        "Volume": [1000.0]*n,
    })
    # signal bar (idx 30)
    df.loc[30, ["Open","High","Low"]] = [100.0, 100.0, 94.5]
    # day1 after signal (idx 31): controlled fill/high
    df.loc[31, "Low"] = day1_low
    df.loc[31, "High"] = day1_high
    # days 2.. : controlled highs
    for j in range(32, 40):
        df.loc[j, "High"] = later_high
        df.loc[j, "Low"] = later_close - 0.2
    return df


def test_limit_not_filled_when_low_shallow():
    # limit -2% from close 95 = 93.10; day1 low 99 -> no fill -> 0 signals in limit mode
    # later_high=105 lets the MARKET baseline resolve (TP from open 99.5 = 104.475)
    raw = _crafted_signal_frame(day1_low=99.0, day1_high=100.0,
                                 later_close=100.0, later_high=105.0)
    data = sef.precompute(raw); cache = sef.build_cache(data)
    p_market = (0, 7, 45, 10, 1.5, 20, 10, 50, 0, 5, 50, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    p_limit  = (0, 7, 45, 10, 1.5, 20, 10, 50, 0, 5, 50, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 2, 0)
    r_m = sef.evaluate(cache, p_market)
    r_l = sef.evaluate(cache, p_limit)
    assert r_m is not None and r_m["n_signals"] >= 1
    assert r_l is None or r_l["n_signals"] == 0


def test_limit_fill_entry_price_is_limit():
    # limit -2% = 93.10 fills (day1 low 80). TP=5% from 93.10 = 97.755.
    # day1 high kept BELOW TP; day2+ high 98 >= TP -> TP on day2.
    # avg_net must equal exactly 5 - friction, proving entry == limit price.
    raw = _crafted_signal_frame(day1_low=80.0, day1_high=96.5,
                                 later_close=97.0, later_high=98.0)
    data = sef.precompute(raw); cache = sef.build_cache(data)
    p_limit = (0, 7, 45, 10, 1.5, 20, 10, 50, 0, 5, 50, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 2, 0)
    r = sef.evaluate(cache, p_limit)
    assert r is not None and r["n_signals"] == 1
    assert r["win_rate"] == 100.0
    assert abs(r["avg_net"] - (5 - sef.FRICTION_PCT)) < 0.02


def test_limit_mode_skips_tp_on_fill_day():
    # Day1 high 200 (would hit TP). Later highs BELOW TP. With the conservative
    # skip rule, TP never counts -> no resolved trades -> evaluate returns None.
    raw = _crafted_signal_frame(day1_low=80.0, day1_high=200.0,
                                 later_close=94.0, later_high=94.2)
    data = sef.precompute(raw); cache = sef.build_cache(data)
    p_limit = (0, 7, 45, 10, 1.5, 20, 10, 50, 0, 5, 50, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 2, 0)
    r = sef.evaluate(cache, p_limit)
    # if TP were (wrongly) counted on the fill day, r would show win_rate 100.
    assert r is None or r["win_rate"] < 100.0


def test_regime_filter_reduces_or_equal():
    raw = _multi(5, 250, seed=11)
    data = sef.precompute(raw); cache = sef.build_cache(data)
    base = (0, 14, 45, 10, 1.5, 20, 10, 50, 0, 3, 8, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    regf = (0, 14, 45, 10, 1.5, 20, 10, 50, 0, 3, 8, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 1)
    r0 = sef.evaluate(cache, base); r1 = sef.evaluate(cache, regf)
    n0 = r0["n_signals"] if r0 else 0
    n1 = r1["n_signals"] if r1 else 0
    assert n1 <= n0


def test_breadth_column_exists_and_bounded():
    raw = _multi(3, 120, seed=2)
    data = sef.precompute(raw)
    b = data["Breadth"].dropna()
    assert len(b) > 0
    assert b.between(0, 1).all()
    assert b.dtype == float  # object dtype would crash np.isnan in evaluate


def test_space_product_updated():
    total = 1
    for v in sef.SPACE.values():
        total *= len(v)
    assert total == 445906944  # updated: 7 families + new params


# ---------------------------------------------------------------- v4: Friday anchor
def test_weekend_mask_marks_last_trading_day_per_week():
    # สัปดาห์แรกครบ จ-ศ; สัปดาห์สองศุกร์หยุด -> พฤหัสต้องถูกนับเป็นแท่งท้ายสัปดาห์
    dates = pd.to_datetime([
        "2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12",
        "2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18",
    ])
    c = np.linspace(100, 108, len(dates))
    raw = pd.DataFrame({"Ticker": "X", "Date": dates, "Open": c, "High": c + 1,
                        "Low": c - 1, "Close": c, "Volume": 1000})
    data = sef.precompute(raw)
    we = data.loc[data["IsWeekEnd"], "Date"].dt.strftime("%Y-%m-%d").tolist()
    assert we == ["2024-01-12", "2024-01-18"]


def test_friday_only_reduces_or_equal_signals():
    old = sef.FRIDAY_ONLY
    try:
        raw = _multi(4, 250, seed=13)
        data = sef.precompute(raw)
        cache = sef.build_cache(data)
        p = (0, 14, 45, 10, 1.5, 20, 10, 50, 0, 3, 8, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
        sef.FRIDAY_ONLY = False
        r_all = sef.evaluate(cache, p)
        sef.FRIDAY_ONLY = True
        r_fri = sef.evaluate(cache, p)
        n_all = r_all["n_signals"] if r_all else 0
        n_fri = r_fri["n_signals"] if r_fri else 0
        assert n_fri <= n_all
    finally:
        sef.FRIDAY_ONLY = old


def test_universe_and_target_config():
    assert len(sef.QUALITY19) == 19
    for dead in ["INTUCH", "MAKRO", "ORIGIN", "STEC"]:
        assert dead not in sef.SET100
    assert sef.TICKERS is sef.QUALITY19 or sef.TICKERS is sef.SET100
    assert sef.NET_RETURN_MIN == 3.0          # เป้า 3%/สัปดาห์ ตามคำสั่งผู้ใช้
    assert sef.BUDGET_PER_TRADE_THB == 10_000
    assert sef.BOARD_LOT == 100


# ---------------------------------------------------------------- v5: Verdict Agent
def _confirmed_row(**over):
    base = dict(entry_family=0, rsi_period=7, rsi_threshold=60, bb_period=10, bb_std=1.5,
                donchian_n=20, ema_fast=10, ema_slow=50, exit_mode=0, tp_val=5, sl_val=13,
                atr_period=14, hold_days=5, adx_min=0, vol_filter=0, stoch_period=14, stoch_th=20, gap_pct=2.0, vol_mult=2.0,
                entry_mode=0, regime_filter=0, in_n=40, in_wr=90.0, in_net=3.2, in_med=2.0,
                oos_signals=12, oos_resolved=10, oos_wr=80.0, oos_wilson_lb=49.0,
                oos_net=3.1, oos_med=2.5)
    base.update(over)
    return base


def _verdict_raw(price=10.0, last=9.0, ticker="CHEAP", n=120):
    close = np.array([price] * (n - 1) + [last])
    return pd.DataFrame({"Ticker": ticker,
                         "Date": pd.date_range("2021-01-01", periods=n, freq="B"),
                         "Open": close, "High": close + price * 0.02,
                         "Low": close - price * 0.02, "Close": close,
                         "Volume": 1000.0})


def test_verdict_no_confirmed_is_no_trade():
    vr = sef.VerdictAgent().decide(_verdict_raw(), pd.DataFrame())
    assert vr.k_used == 0 and len(vr.verdicts) == 0
    assert "ไม่เข้า" in vr.overall


def test_verdict_consensus_trade():
    confirmed = pd.DataFrame([_confirmed_row(oos_net=3.0 + i * 0.1) for i in range(5)])
    vr = sef.VerdictAgent(top_k=5, min_agree=3).decide(_verdict_raw(), confirmed)
    assert vr.k_used == 5 and len(vr.verdicts) == 1
    v = vr.verdicts[0]
    assert v.ticker == "CHEAP" and v.agree_count == 5
    assert v.action.startswith("เข้า") and v.budget_ok and v.lots >= 1


def test_verdict_budget_blocks_trade():
    raw = _verdict_raw(price=500.0, last=450.0, ticker="PRICY")  # 1 lot = 45,000 > 10,000
    confirmed = pd.DataFrame([_confirmed_row() for _ in range(5)])
    vr = sef.VerdictAgent().decide(raw, confirmed)
    assert len(vr.verdicts) == 1
    v = vr.verdicts[0]
    assert not v.budget_ok and v.action.startswith("เฝ้าดู")
    assert "งบ" in v.reasons


def test_verdict_deterministic():
    raw = _verdict_raw()
    confirmed = pd.DataFrame([_confirmed_row() for _ in range(5)])
    a = sef.VerdictAgent().decide(raw, confirmed)
    b = sef.VerdictAgent().decide(raw, confirmed)
    assert a == b


def test_verdict_agent_validates_config():
    import pytest as _pt
    with _pt.raises(ValueError):
        sef.VerdictAgent(top_k=0)
    with _pt.raises(ValueError):
        sef.VerdictAgent(min_agree=0)


def test_params_from_row_preserves_float():
    # กันบั๊กแฝง [สูง]: cast เดิมปัด 2.5 -> 2 เงียบ ๆ = validate ผิดสมการ
    row = pd.Series(_confirmed_row(tp_val=2.5, rsi_threshold=22.5))
    d = dict(zip(sef.PARAM_KEYS, sef._params_from_row(row)))
    assert d["tp_val"] == 2.5 and d["rsi_threshold"] == 22.5
    assert isinstance(d["hold_days"], int) and isinstance(d["rsi_period"], int)


# ---------------------------------------------------------------- v6: Trade Journal
def _journal_row(**over):
    base = dict(signal_date="2026-01-02", ticker="X", order_type="Market@Open",
                entry_mode=0, buy_ref=100.0, sell_tp=105.0, stop_sl=90.0,
                hold_days=5, action="เข้า (TRADE)", status="PENDING",
                fill_price=np.nan, exit_date=np.nan, exit_price=np.nan,
                net_return_pct=np.nan, expected_wr=80.0, expected_net=3.0,
                run_date="2026-01-02")
    return pd.DataFrame([{**base, **over}], columns=sef.JOURNAL_COLUMNS)


def _price_frame(ticker, dates, o, h, l, c):
    return pd.DataFrame({"Ticker": ticker, "Date": pd.to_datetime(dates),
                         "Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000.0})


def test_load_journal_missing_returns_empty_with_columns(tmp_path):
    j = sef.load_journal(str(tmp_path / "nope.csv"))
    assert list(j.columns) == sef.JOURNAL_COLUMNS and len(j) == 0


def test_journal_resolve_market_tp():
    # entry = Open แท่งแรกหลังสัญญาณ (100); D1 High 106 >= TP 105 -> FILLED_TP
    raw = _price_frame("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
                       o=[99, 100, 101], h=[99, 106, 101], l=[99, 98, 100], c=[99, 104, 101])
    j = sef.resolve_journal(_journal_row(), raw)
    r = j.iloc[0]
    assert r["status"] == "FILLED_TP" and r["fill_price"] == 100.0
    assert r["net_return_pct"] == round((105/100 - 1)*100 - sef.FRICTION_PCT, 2)


def test_journal_resolve_limit_not_filled():
    # limit buy_ref 95; D1 Low 96 > 95 -> NOT_FILLED (ยกเลิกฟรี)
    raw = _price_frame("X", ["2026-01-02", "2026-01-05"],
                       o=[99, 100], h=[99, 101], l=[99, 96], c=[99, 100])
    j = sef.resolve_journal(_journal_row(entry_mode=2, buy_ref=95.0), raw)
    assert j.iloc[0]["status"] == "NOT_FILLED"


def test_journal_limit_skips_tp_on_fill_day_then_time():
    # D1: Low 90 ติด limit 95, High 200 (ห้ามนับ TP วันติด); D2-D5 ไม่ชนอะไร -> FILLED_TIME
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    raw = _price_frame("X", dates,
                       o=[99, 96, 96, 96, 96, 96], h=[99, 200, 97, 97, 97, 97],
                       l=[99, 90, 95.5, 95.5, 95.5, 95.5], c=[99, 96, 96, 96, 96, 97])
    j = sef.resolve_journal(_journal_row(entry_mode=2, buy_ref=95.0, sell_tp=103.0, stop_sl=80.0), raw)
    r = j.iloc[0]
    assert r["status"] == "FILLED_TIME"
    assert r["exit_price"] == 97.0  # ปิดแท่งที่ 5 หลังสัญญาณ
    assert r["fill_price"] == 95.0


def test_journal_pending_when_week_incomplete():
    # มีแค่ 2 แท่งหลังสัญญาณ (hold=5) และยังไม่ชน TP/SL -> คง PENDING
    raw = _price_frame("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
                       o=[99, 100, 100], h=[99, 101, 101], l=[99, 99, 99], c=[99, 100, 100])
    j = sef.resolve_journal(_journal_row(sell_tp=110.0, stop_sl=80.0), raw)
    assert j.iloc[0]["status"] == "PENDING"


def test_journal_no_data_ticker():
    raw = _price_frame("OTHER", ["2026-01-05"], o=[10], h=[10], l=[10], c=[10])
    j = sef.resolve_journal(_journal_row(ticker="GONE"), raw)
    assert j.iloc[0]["status"] == "NO_DATA"


def test_append_new_verdicts_dedup():
    v = sef.TickerVerdict(ticker="X", action="เข้า (TRADE)", agree_count=5, of_k=5,
                          order_type="Limit -2% (ตั้งซื้อ)", buy_at=9.8, sell_tp=10.29,
                          stop_sl=8.53, lots=10, budget_ok=True, min_oos_wilson_lb=55.0,
                          expected_oos_net=3.1, expected_oos_wr=80.0, reasons="-",
                          hold_days=10, entry_mode=2)
    vr = sef.VerdictReport(overall="เข้า 1 ตัว", k_used=5, verdicts=(v,))
    j0 = pd.DataFrame(columns=sef.JOURNAL_COLUMNS)
    j1 = sef.append_new_verdicts(j0, vr, run_date="2026-01-02")
    j2 = sef.append_new_verdicts(j1, vr, run_date="2026-01-02")
    assert len(j1) == 1 and len(j2) == 1  # idempotent
    # [regression บั๊กกลาง] hold_days ต้องมาจากสมการจริง ไม่ใช่ตอกตาย 5
    assert j1.iloc[0]["hold_days"] == 10
    assert j1.iloc[0]["entry_mode"] == 2 and j1.iloc[0]["expected_net"] == 3.1


def test_journal_stats_math():
    rows = pd.concat([
        _journal_row(status="FILLED_TP", net_return_pct=4.49, expected_net=3.0),
        _journal_row(ticker="B", status="FILLED_TP", net_return_pct=4.49, expected_net=3.0),
        _journal_row(ticker="C", status="FILLED_SL", net_return_pct=-10.51, expected_net=3.0),
        _journal_row(ticker="D", status="FILLED_TIME", net_return_pct=0.5, expected_net=3.0),
        _journal_row(ticker="E", status="NOT_FILLED"),
        _journal_row(ticker="F", status="PENDING"),
    ], ignore_index=True)
    s = sef.journal_stats(rows)
    assert s["n_orders"] == 6 and s["n_pending"] == 1 and s["n_not_filled"] == 1
    assert s["n_resolved"] == 3 and s["wins"] == 2
    assert s["realized_wr"] == round(2/3*100, 2)
    import numpy as _np
    assert s["realized_avg_net"] == round(_np.mean([4.49, 4.49, -10.51, 0.5]), 2)
    assert s["expected_avg_net"] == 3.0 and s["gap"] == round(s["realized_avg_net"] - 3.0, 2)


# ---------------------------------------------------------------- v7: Dashboard + regressions
def _mk_verdict(**over):
    base = dict(ticker="DEMO", action="เข้า (TRADE)", agree_count=5, of_k=5,
                order_type="Limit -2% (ตั้งซื้อ)", buy_at=9.8, sell_tp=10.29,
                stop_sl=8.53, lots=10, budget_ok=True, min_oos_wilson_lb=55.0,
                expected_oos_net=3.1, expected_oos_wr=80.0, reasons="-",
                hold_days=5, entry_mode=2)
    base.update(over)
    return sef.TickerVerdict(**base)


def _run_info():
    return dict(run_ts="2026-07-03 18:30", last_bar="2026-07-03", friday_ok=True,
                universe="QUALITY19", n_tickers=19, wr_min=70.0, net_min=3.0,
                n_target=3_000_000)


def test_verdict_carries_hold_days_and_entry_mode():
    # [regression บั๊กกลาง] ค่าจากสมการจริงต้องไหลถึง verdict
    confirmed = pd.DataFrame([_confirmed_row(hold_days=10, entry_mode=3) for _ in range(5)])
    vr = sef.VerdictAgent().decide(_verdict_raw(), confirmed)
    v = vr.verdicts[0]
    assert v.hold_days == 10 and v.entry_mode == 3


def test_resolve_honors_strategy_hold_days():
    # TP โผล่ที่แท่งที่ 7: hold=5 -> FILLED_TIME, hold=10 -> FILLED_TP
    dates = pd.date_range("2026-01-02", periods=12, freq="B")
    h = [99.0] + [101.0]*6 + [106.0] + [101.0]*4          # TP 105 ชนที่ future-bar ที่ 7
    raw = _price_frame("X", dates, o=[99]+[100]*11, h=h, l=[99]+[98]*11, c=[99]+[100]*11)
    j5 = sef.resolve_journal(_journal_row(hold_days=5, sell_tp=105.0, stop_sl=80.0), raw)
    j10 = sef.resolve_journal(_journal_row(hold_days=10, sell_tp=105.0, stop_sl=80.0), raw)
    assert j5.iloc[0]["status"] == "FILLED_TIME"
    assert j10.iloc[0]["status"] == "FILLED_TP"


def test_dashboard_returns_html_with_claude_theme():
    vr = sef.VerdictReport(overall="เข้า 1 ตัว", k_used=5, verdicts=(_mk_verdict(),))
    j = _journal_row(status="FILLED_TP", net_return_pct=4.49, exit_date="2026-07-02")
    html = sef.generate_dashboard(_run_info(), sef.journal_stats(j), j, vr, pd.DataFrame())
    assert html.startswith("<!DOCTYPE html")
    assert "#D97757" in html and "#FAF9F5" in html          # ธีม Claude
    assert "DEMO" in html and "เข้า 1 ตัว" in html


def test_dashboard_empty_state_no_crash():
    vr = sef.VerdictReport(overall="ไม่เข้า (NO_TRADE)", k_used=0, verdicts=tuple())
    empty = pd.DataFrame(columns=sef.JOURNAL_COLUMNS)
    html = sef.generate_dashboard(_run_info(), sef.journal_stats(empty), empty, vr, pd.DataFrame())
    assert "ยังไม่มีประวัติ" in html and "สมุดบันทึกว่าง" in html
    assert "ยังไม่มีไม้ที่จบ" in html and "chart.js" not in html.lower()


def test_dashboard_status_pills_and_net_colors():
    j = pd.concat([
        _journal_row(status="FILLED_TP", net_return_pct=4.49, exit_date="2026-07-01"),
        _journal_row(ticker="B", status="PENDING"),
    ], ignore_index=True)
    vr = sef.VerdictReport(overall="-", k_used=0, verdicts=tuple())
    html = sef.generate_dashboard(_run_info(), sef.journal_stats(j), j, vr, pd.DataFrame())
    assert "ชนะ (TP)" in html and "รอผล" in html
    assert 'class="pos"' in html


def test_dashboard_cumulative_chart_values():
    j = pd.concat([
        _journal_row(status="FILLED_TP", net_return_pct=4.49, exit_date="2026-07-01"),
        _journal_row(ticker="B", status="FILLED_SL", net_return_pct=-10.51, exit_date="2026-07-02"),
    ], ignore_index=True)
    vr = sef.VerdictReport(overall="-", k_used=0, verdicts=tuple())
    html = sef.generate_dashboard(_run_info(), sef.journal_stats(j), j, vr, pd.DataFrame())
    assert "4.49" in html and "-6.02" in html               # cumulative: 4.49, -6.02
    assert "chart.js" in html.lower()


def test_dashboard_friday_warning_chip():
    ri = _run_info(); ri["friday_ok"] = False
    vr = sef.VerdictReport(overall="-", k_used=0, verdicts=tuple())
    empty = pd.DataFrame(columns=sef.JOURNAL_COLUMNS)
    html = sef.generate_dashboard(ri, sef.journal_stats(empty), empty, vr, pd.DataFrame())
    assert "ไม่ใช่ศุกร์" in html


# ---------------------------------------------------------------- v8: new families 4/5/6
def _p(fam, **o):
    """param tuple builder ตาม SPACE order (21 มิติ) ค่า default ยิงง่าย."""
    d = dict(entry_family=fam, rsi_period=14, rsi_threshold=45, bb_period=10, bb_std=1.5,
             donchian_n=10, ema_fast=10, ema_slow=50, exit_mode=0, tp_val=3, sl_val=13,
             atr_period=14, hold_days=5, adx_min=0, vol_filter=0, stoch_period=14,
             stoch_th=25, gap_pct=2.0, vol_mult=1.5, entry_mode=0, regime_filter=0)
    d.update(o)
    return tuple(d[k] for k in sef.PARAM_KEYS)


def test_stochastic_family_fires_on_oversold():
    # ราคาไหลลงต่อเนื่อง -> %K ต่ำ -> fam4 ต้องยิงสัญญาณ
    closes = list(np.linspace(120, 80, 40)) + list(np.linspace(80, 95, 40))
    raw = _ticker("X", closes)
    data = sef.precompute(raw); cache = sef.build_cache(data)
    r = sef.evaluate(cache, _p(4, stoch_th=25))
    assert r is not None and r["n_signals"] >= 1
    assert r["entry_family"] == 4


def test_gap_down_reversal_family():
    # สร้าง gap ลง >2% แล้วปิดเหนือ open ที่แท่งหนึ่ง
    n = 80
    close = list(np.linspace(100, 100, n))
    raw = _ticker("X", close)
    # แท่ง i=60: prev close 100, open 97 (gap -3%), close 99 (>open) -> ฟื้น
    raw.loc[59, "Close"] = 100.0
    raw.loc[60, "Open"] = 97.0
    raw.loc[60, "Close"] = 99.0
    raw.loc[60, "High"] = 99.5
    raw.loc[60, "Low"] = 96.5
    # entry = open แท่งถัดไป (idx61=100); ให้ราคาไต่ขึ้นทะลุ TP 3% เพื่อให้ resolvable
    for j in range(61, 68):
        raw.loc[j, ["Open", "High", "Low", "Close"]] = [100 + (j - 60), 105 + (j - 60), 99, 104 + (j - 60)]
    data = sef.precompute(raw); cache = sef.build_cache(data)
    r = sef.evaluate(cache, _p(5, gap_pct=2.0))
    assert r is not None and r["n_signals"] >= 1
    assert r["entry_family"] == 5


def test_volspike_breakout_family():
    # ปิด new high พร้อมวอลุ่มพุ่ง >= 2x SMA20
    n = 80
    close = list(np.linspace(90, 100, n))
    raw = _ticker("X", close)
    raw["Volume"] = 1000.0
    raw.loc[70, "Volume"] = 5000.0            # spike
    raw.loc[70, "Close"] = raw["Close"].iloc[:70].max() + 5  # new high
    raw.loc[70, "High"] = raw.loc[70, "Close"] + 1
    # entry = open idx71; ให้ราคาไต่ทะลุ TP 3%
    base = float(raw.loc[70, "Close"])
    for j in range(71, 78):
        raw.loc[j, ["Open", "High", "Low", "Close"]] = [base, base * 1.05, base * 0.99, base * 1.04]
    data = sef.precompute(raw); cache = sef.build_cache(data)
    r = sef.evaluate(cache, _p(6, donchian_n=10, vol_mult=2.0))
    assert r is not None and r["n_signals"] >= 1
    assert r["entry_family"] == 6


def test_all_seven_families_run_without_error():
    raw = _multi(5, 200, seed=17)
    data = sef.precompute(raw); cache = sef.build_cache(data)
    for fam in range(7):
        r = sef.evaluate(cache, _p(fam))
        # ต้องไม่ throw; ผลอาจ None (ไม่มีสัญญาณ) หรือ dict สถิติ
        assert r is None or (0 <= r["win_rate"] <= 100)


def test_new_families_have_names():
    for fam in range(7):
        assert fam in sef.FAMILY_NAME
    assert sef.FAMILY_NAME[4] == "STOCH_OVERSOLD"
    assert sef.FAMILY_NAME[5] == "GAP_DOWN_REVERSAL"
    assert sef.FAMILY_NAME[6] == "VOLSPIKE_BREAKOUT"


def test_latest_bar_signal_new_families(monkeypatch):
    # fam4/5/6 ต้องถูกจดจำใน _latest_bar_signal (ใช้โดย verdict/report) ไม่ throw
    raw = _multi(3, 150, seed=4)
    breadth = sef.compute_breadth(raw)
    for fam in (4, 5, 6):
        row = pd.Series(_confirmed_row(entry_family=fam))
        for tk, g in raw.groupby("Ticker", sort=False):
            g = g.sort_values("Date").reset_index(drop=True)
            out = sef._latest_bar_signal(g, row, breadth)
            assert out is None or "buy_at" in out


# ---------------------------------------------------------------- v9: bug/edge hardening
def test_simulate_tie_break_sl_wins_by_default():
    # แท่งเดียวชนทั้ง TP(102) และ SL(97): default = แพ้ (ซื่อสัตย์), flip = ชนะ
    entry = np.array([100.0]); atr0 = np.zeros(1)
    h = {1: np.array([101.0]), 2: np.array([103.0]), 3: np.array([100.0])}
    l = {1: np.array([99.0]),  2: np.array([96.0]),  3: np.array([100.0])}
    c = {1: np.array([100.0]), 2: np.array([100.0]), 3: np.array([100.0])}
    old = sef.TIE_BREAK_SL_WINS
    try:
        sef.TIE_BREAK_SL_WINS = True
        o, ep = sef._simulate(entry, atr0, h, l, c, 0, 2, 3, 3)
        assert o[0] == -1 and ep[0] == 97.0           # SL wins -> loss
        sef.TIE_BREAK_SL_WINS = False
        o, ep = sef._simulate(entry, atr0, h, l, c, 0, 2, 3, 3)
        assert o[0] == 1 and ep[0] == 102.0           # optimistic path still available
    finally:
        sef.TIE_BREAK_SL_WINS = old


def test_simulate_non_tie_unaffected_by_policy():
    # แท่งที่ชนแค่ TP อย่างเดียว: นโยบาย tie ต้องไม่เปลี่ยนผล
    entry = np.array([100.0])
    h = {1: np.array([101.0]), 2: np.array([103.0])}
    l = {1: np.array([99.0]),  2: np.array([99.0])}
    c = {1: np.array([100.0]), 2: np.array([100.0])}
    for policy in (True, False):
        old = sef.TIE_BREAK_SL_WINS
        try:
            sef.TIE_BREAK_SL_WINS = policy
            o, _ = sef._simulate(entry, np.zeros(1), h, l, c, 0, 2, 3, 2)
            assert o[0] == 1
        finally:
            sef.TIE_BREAK_SL_WINS = old


def test_zero_price_entry_does_not_corrupt_stats():
    # bar ราคา 0 (tick เสีย) ตามหลังสัญญาณ -> entry=0 เดิมทำให้ inf; ต้องถูก guard ทิ้ง
    import warnings
    closes = [100.0] * 30 + [95.0] + [0.0] + [100.0] * 8      # zero-open bar at idx31
    o = list(closes); h = [x + 2 for x in closes]; l = [x - 2 for x in closes]
    raw = _ticker("BADTICK", closes)
    raw["Open"] = o; raw["High"] = h; raw["Low"] = l; raw["Close"] = closes
    cache = sef.build_cache(sef.precompute(raw))
    p = (0, 7, 45, 10, 1.5, 20, 10, 50, 0, 3, 13, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")                        # no divide-by-zero RuntimeWarning
        r = sef.evaluate(cache, p)
    assert r is None or (np.isfinite(r["avg_net"]) and np.isfinite(r["median_net"]))


def test_gap_pct_zero_prev_close_no_inf():
    # prev close = 0 ต้องไม่ทำให้ GapPct = inf (fam5 พึ่ง gap)
    closes = [100.0] * 20 + [0.0] + [100.0] * 20
    raw = _ticker("Z", closes)
    raw["Close"] = closes; raw["Open"] = closes
    data = sef.precompute(raw)
    assert np.isfinite(data["GapPct"].replace([np.inf, -np.inf], np.nan).dropna()).all()
    assert not np.isinf(data["GapPct"]).any()


def test_resolve_journal_same_bar_tie_is_loss():
    # market: entry=Open(100); D1 ชนทั้ง TP(102) และ SL(97) -> conservative = FILLED_SL
    raw = _price_frame("X", ["2026-01-02", "2026-01-05"],
                       o=[99, 100], h=[99, 103], l=[99, 96], c=[99, 100])
    old = sef.TIE_BREAK_SL_WINS
    try:
        sef.TIE_BREAK_SL_WINS = True
        j = sef.resolve_journal(_journal_row(sell_tp=102.0, stop_sl=97.0), raw)
        assert j.iloc[0]["status"] == "FILLED_SL"
    finally:
        sef.TIE_BREAK_SL_WINS = old


def test_atr_exit_zero_volatility_no_fake_win():
    # ราคานิ่งสนิท -> ATR=0 -> exit_mode=1 ต้องไม่สร้าง "ชนะทันที" จอมปลอม (guard ATR>0)
    cache = sef.build_cache(sef.precompute(_ticker("FLAT", [100.0] * 80)))
    p = (0, 14, 45, 10, 1.5, 20, 10, 50, 1, 2, 3, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
    r = sef.evaluate(cache, p)
    assert r is None                                          # no resolvable trade from zero ATR


def test_tie_policy_config_default_is_honest():
    assert sef.TIE_BREAK_SL_WINS is True                      # ค่าเริ่มต้นต้องเป็นแบบซื่อสัตย์


def test_safe_int_handles_nan_and_junk():
    assert sef._safe_int(np.nan, default=5) == 5
    assert sef._safe_int(None, default=7) == 7
    assert sef._safe_int("bad", default=3) == 3
    assert sef._safe_int(10.0, default=0) == 10
    assert sef._safe_int(np.inf, default=5) == 5


def test_safe_float_handles_junk():
    assert sef._safe_float("bad") != sef._safe_float("bad")   # NaN != NaN
    assert sef._safe_float(2.5) == 2.5


def test_resolve_journal_legacy_missing_cols_no_crash():
    # journal เก่าที่ขาด entry_mode/hold_days -> load เติม NaN -> เดิม int(NaN) crash
    row = _journal_row()
    row.loc[0, "entry_mode"] = np.nan
    row.loc[0, "hold_days"] = np.nan
    raw = _price_frame("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
                       o=[99, 100, 101], h=[99, 106, 101], l=[99, 98, 100], c=[99, 104, 101])
    j = sef.resolve_journal(row, raw)          # ต้องไม่ throw
    assert j.iloc[0]["status"] == "FILLED_TP"  # default entry_mode=0 (market) -> resolvable


def test_resolve_journal_broken_tp_sl_stays_pending():
    # sell_tp/stop_sl เสีย (NaN) -> ตัดสินไม่ได้ ต้องคง PENDING (ไม่เดา/ไม่ crash)
    row = _journal_row(sell_tp=np.nan, stop_sl=np.nan)
    raw = _price_frame("X", ["2026-01-02", "2026-01-05"],
                       o=[99, 100], h=[99, 106], l=[99, 98], c=[99, 104])
    j = sef.resolve_journal(row, raw)
    assert j.iloc[0]["status"] == "PENDING"


def test_iter_combos_mixed_radix_valid_across_space():
    # ทุกค่าที่ถอดรหัสต้องอยู่ใน SPACE จริง (บิเจกชันถูกต้อง ไม่หลุดขอบ)
    keys = list(sef.SPACE.keys())
    for combo in sef.iter_combos(1500, seed=9):
        assert len(combo) == len(keys)
        for k, v in zip(keys, combo):
            assert v in sef.SPACE[k]


def test_to_naive_datetime_tz_aware_and_naive():
    aware = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("Asia/Bangkok"))
    naive = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]))
    for s in (aware, naive):
        out = sef._to_naive_datetime(s)
        assert getattr(out.dt, "tz", None) is None    # ต้องได้ naive เสมอ ไม่ crash


def test_strictly_non_repainting_all_families():
    # ข้อกำหนดหลัก: สัญญาณที่แท่ง t ต้องไม่เปลี่ยนเมื่อมีข้อมูลอนาคตมาต่อ.
    # พิสูจน์: signal(prefix[0..t]).last == signal(full)[t] สำหรับทุก family.
    rng = np.random.default_rng(42)
    n = 160
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    raw = pd.DataFrame({"Ticker": "X", "Date": pd.date_range("2021-01-01", periods=n, freq="B"),
                        "Open": close, "High": close + np.abs(rng.normal(0, 0.5, n)),
                        "Low": close - np.abs(rng.normal(0, 0.5, n)), "Close": close,
                        "Volume": rng.integers(500, 5000, n).astype(float)})
    full_cache = sef.build_cache(sef.precompute(raw))
    for fam in range(7):
        p = (fam, 14, 45, 20, 2.0, 20, 10, 50, 0, 3, 13, 14, 5, 0, 0, 14, 20, 2.0, 2.0, 0, 0)
        full = sef._entry_signal(full_cache, p)
        for t in range(110, n):
            pref = raw.iloc[:t + 1].copy()
            s_pref = sef._entry_signal(sef.build_cache(sef.precompute(pref)), p)
            assert bool(s_pref[-1]) == bool(full[t]), f"repaint at fam={fam}, t={t}"
