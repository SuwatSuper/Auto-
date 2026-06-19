# Layer 1 — Domain (analytics/swarm_methods)
"""Pure chart-analysis methods for the agent swarm — no I/O, Decimal math.

Every function takes an oldest→newest list of :class:`Candle` (real OHLC bars
resampled from the live tick stream) and returns an :class:`AnalysisRead`
(direction + strength + a short human label). Insufficient data yields a NEUTRAL
"warming up" read — never a fabricated signal.

These are the building blocks the historical-chart, live-price and
entry-hunter swarms run across timeframes (1s / 1m / 1h / 1d) and methods.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from domain.analytics.indicators import ema, macd, rsi_wilder

BULL = "BULL"
BEAR = "BEAR"
NEUTRAL = "NEUTRAL"

_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(frozen=True)
class Candle:
    """One OHLC bar (Decimal prices, epoch-ms open time)."""

    ts_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "ts_ms": self.ts_ms,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
        }


@dataclass(frozen=True)
class AnalysisRead:
    """A method's verdict: direction, strength in [0,1], short label."""

    direction: str
    strength: Decimal
    label: str

    @staticmethod
    def neutral(label: str = "—") -> AnalysisRead:
        return AnalysisRead(NEUTRAL, _ZERO, label)


# ── helpers ──────────────────────────────────────────────────────────
def _clamp01(x: Decimal) -> Decimal:
    if x < _ZERO:
        return _ZERO
    if x > _ONE:
        return _ONE
    return x


def _closes(candles: Sequence[Candle]) -> list[Decimal]:
    return [c.close for c in candles]


def _mean(seq: Sequence[Decimal]) -> Decimal:
    return sum(seq, _ZERO) / Decimal(len(seq)) if seq else _ZERO


def _stdev(seq: Sequence[Decimal], mean: Decimal) -> Decimal:
    if len(seq) < 2:
        return _ZERO
    var = sum(((x - mean) ** 2 for x in seq), _ZERO) / Decimal(len(seq))
    return var.sqrt()


def _read(direction: str, strength: Decimal, label: str) -> AnalysisRead:
    return AnalysisRead(direction, _clamp01(strength), label)


# ── methods ──────────────────────────────────────────────────────────
def ema_cross(candles: Sequence[Candle], fast: int = 12, slow: int = 26) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < slow + 1:
        return AnalysisRead.neutral(f"อุ่นเครื่อง EMA ({len(closes)}/{slow + 1})")
    f = ema(closes, fast)[-1]
    s = ema(closes, slow)[-1]
    if s <= 0:
        return AnalysisRead.neutral("EMA")
    gap = (f - s) / s
    strength = abs(gap) * Decimal(25)
    direction = BULL if f > s else BEAR if f < s else NEUTRAL
    return _read(direction, strength, f"EMA{fast}/{slow} gap {gap * 100:.2f}%")


def rsi_signal(candles: Sequence[Candle], period: int = 14) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < period + 1:
        return AnalysisRead.neutral(f"อุ่นเครื่อง RSI ({len(closes)}/{period + 1})")
    r = rsi_wilder(closes, period)[-1]
    if r.is_nan():
        return AnalysisRead.neutral("RSI")
    if r <= Decimal(30):
        return _read(BULL, (Decimal(30) - r) / Decimal(30), f"RSI {r:.0f} oversold")
    if r >= Decimal(70):
        return _read(BEAR, (r - Decimal(70)) / Decimal(30), f"RSI {r:.0f} overbought")
    return _read(NEUTRAL, abs(r - Decimal(50)) / Decimal(20), f"RSI {r:.0f} กลาง")


def macd_signal(candles: Sequence[Candle]) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < 35:
        return AnalysisRead.neutral(f"อุ่นเครื่อง MACD ({len(closes)}/35)")
    _line, _sig, hist = macd(closes)
    h = hist[-1]
    ref = closes[-1] if closes[-1] > 0 else _ONE
    strength = abs(h) / ref * Decimal(400)
    direction = BULL if h > 0 else BEAR if h < 0 else NEUTRAL
    return _read(direction, strength, f"MACD hist {h:.0f}")


def bollinger(candles: Sequence[Candle], n: int = 20) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < n:
        return AnalysisRead.neutral(f"อุ่นเครื่อง BB ({len(closes)}/{n})")
    window = closes[-n:]
    mean = _mean(window)
    sd = _stdev(window, mean)
    if sd <= 0:
        return AnalysisRead.neutral("BB flat")
    price = closes[-1]
    upper = mean + 2 * sd
    lower = mean - 2 * sd
    if price < lower:
        return _read(BULL, (lower - price) / (2 * sd), f"BB ต่ำกว่ากรอบล่าง {price:.0f}")
    if price > upper:
        return _read(BEAR, (price - upper) / (2 * sd), f"BB สูงกว่ากรอบบน {price:.0f}")
    return _read(NEUTRAL, abs(price - mean) / (2 * sd), "BB ในกรอบ")


def donchian(candles: Sequence[Candle], n: int = 20) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < n + 1:
        return AnalysisRead.neutral(f"อุ่นเครื่อง Donchian ({len(closes)}/{n + 1})")
    window = closes[-(n + 1):-1]
    hi, lo = max(window), min(window)
    price = closes[-1]
    if hi > 0 and price > hi:
        return _read(BULL, (price - hi) / hi * Decimal(50), f"ทะลุกรอบบน {hi:.0f}")
    if lo > 0 and price < lo:
        return _read(BEAR, (lo - price) / lo * Decimal(50), f"หลุดกรอบล่าง {lo:.0f}")
    return _read(NEUTRAL, _ZERO, f"ในกรอบ {lo:.0f}-{hi:.0f}")


def momentum(candles: Sequence[Candle], n: int = 10) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < n + 1:
        return AnalysisRead.neutral(f"อุ่นเครื่อง ROC ({len(closes)}/{n + 1})")
    base = closes[-1 - n]
    if base <= 0:
        return AnalysisRead.neutral("ROC")
    roc = (closes[-1] - base) / base
    direction = BULL if roc > 0 else BEAR if roc < 0 else NEUTRAL
    return _read(direction, abs(roc) * Decimal(20), f"โมเมนตัม {roc * 100:+.2f}%")


def sma_slope(candles: Sequence[Candle], n: int = 20, look: int = 5) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < n + look:
        return AnalysisRead.neutral(f"อุ่นเครื่อง SMA ({len(closes)}/{n + look})")
    now = _mean(closes[-n:])
    prev = _mean(closes[-n - look:-look])
    if prev <= 0:
        return AnalysisRead.neutral("SMA")
    slope = (now - prev) / prev
    direction = BULL if slope > 0 else BEAR if slope < 0 else NEUTRAL
    return _read(direction, abs(slope) * Decimal(40), f"ความชัน SMA {slope * 100:+.2f}%")


def stochastic(candles: Sequence[Candle], n: int = 14) -> AnalysisRead:
    if len(candles) < n:
        return AnalysisRead.neutral(f"อุ่นเครื่อง Stoch ({len(candles)}/{n})")
    window = candles[-n:]
    hh = max(c.high for c in window)
    ll = min(c.low for c in window)
    c = candles[-1].close
    if hh <= ll:
        return AnalysisRead.neutral("Stoch flat")
    k = (c - ll) / (hh - ll) * Decimal(100)
    if k <= Decimal(20):
        return _read(BULL, (Decimal(20) - k) / Decimal(20), f"Stoch {k:.0f} oversold")
    if k >= Decimal(80):
        return _read(BEAR, (k - Decimal(80)) / Decimal(20), f"Stoch {k:.0f} overbought")
    return _read(NEUTRAL, abs(k - Decimal(50)) / Decimal(30), f"Stoch {k:.0f}")


def atr_regime(candles: Sequence[Candle], n: int = 14) -> AnalysisRead:
    if len(candles) < n + 1:
        return AnalysisRead.neutral(f"อุ่นเครื่อง ATR ({len(candles)}/{n + 1})")
    trs: list[Decimal] = []
    for i in range(1, len(candles)):
        cur, prev = candles[i], candles[i - 1]
        tr = max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))
        trs.append(tr)
    atr = _mean(trs[-n:])
    close = candles[-1].close
    if close <= 0:
        return AnalysisRead.neutral("ATR")
    atr_pct = atr / close * Decimal(100)
    sma = _mean([c.close for c in candles[-n:]])
    direction = BULL if close > sma else BEAR if close < sma else NEUTRAL
    return _read(direction, atr_pct * Decimal(20), f"ATR {atr_pct:.2f}% ผันผวน")


def hh_ll_trend(candles: Sequence[Candle], n: int = 20) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < n:
        return AnalysisRead.neutral(f"อุ่นเครื่อง HH/LL ({len(closes)}/{n})")
    w = closes[-n:]
    half = n // 2
    first, second = w[:half], w[half:]
    f_hi, f_lo = max(first), min(first)
    s_hi, s_lo = max(second), min(second)
    fm, sm = _mean(first), _mean(second)
    strength = abs(sm - fm) / fm * Decimal(30) if fm > 0 else _ZERO
    if s_hi > f_hi and s_lo > f_lo:
        return _read(BULL, strength, "ยอด/ฐานยกสูงขึ้น")
    if s_hi < f_hi and s_lo < f_lo:
        return _read(BEAR, strength, "ยอด/ฐานต่ำลง")
    return _read(NEUTRAL, _ZERO, "ไร้ทิศชัด")


def double_top_bottom(candles: Sequence[Candle], n: int = 30) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < n:
        return AnalysisRead.neutral(f"อุ่นเครื่อง pattern ({len(closes)}/{n})")
    w = closes[-n:]
    third = max(1, n // 3)
    left, mid, right = w[:third], w[third:2 * third], w[2 * third:]
    ll, rl, mm = min(left), min(right), max(mid)
    lh, rh, mlo = max(left), max(right), min(mid)
    if ll > 0 and rl > 0 and abs(ll - rl) / ((ll + rl) / 2) < Decimal("0.01") and mm > max(ll, rl):
        return _read(BULL, Decimal("0.6"), "double bottom (กลับขึ้น)")
    if lh > 0 and rh > 0 and abs(lh - rh) / ((lh + rh) / 2) < Decimal("0.01") and mlo < min(lh, rh):
        return _read(BEAR, Decimal("0.6"), "double top (กลับลง)")
    return _read(NEUTRAL, _ZERO, "ไม่พบแพตเทิร์น")


def engulfing(candles: Sequence[Candle]) -> AnalysisRead:
    if len(candles) < 2:
        return AnalysisRead.neutral("อุ่นเครื่อง engulfing")
    prev, cur = candles[-2], candles[-1]
    body = abs(cur.close - cur.open)
    ref = cur.close if cur.close > 0 else _ONE
    strength = body / ref * Decimal(50)
    prev_red = prev.close < prev.open
    prev_green = prev.close > prev.open
    cur_green = cur.close > cur.open
    cur_red = cur.close < cur.open
    if prev_red and cur_green and cur.close >= prev.open and cur.open <= prev.close:
        return _read(BULL, strength, "bullish engulfing")
    if prev_green and cur_red and cur.close <= prev.open and cur.open >= prev.close:
        return _read(BEAR, strength, "bearish engulfing")
    return _read(NEUTRAL, _ZERO, "ไม่กลืนแท่ง")


def roc_accel(candles: Sequence[Candle], n: int = 5) -> AnalysisRead:
    closes = _closes(candles)
    if len(closes) < 2 * n + 1:
        return AnalysisRead.neutral(f"อุ่นเครื่อง accel ({len(closes)}/{2 * n + 1})")
    b1, b2 = closes[-1 - n], closes[-1 - 2 * n]
    if b1 <= 0 or b2 <= 0:
        return AnalysisRead.neutral("accel")
    roc1 = (closes[-1] - b1) / b1
    roc2 = (b1 - b2) / b2
    accel = roc1 - roc2
    direction = BULL if accel > 0 else BEAR if accel < 0 else NEUTRAL
    return _read(direction, abs(accel) * Decimal(30), f"เร่งโมเมนตัม {accel * 100:+.2f}%")


# Ordered registry — the swarm spreads these across timeframes.
METHODS: dict[str, Callable[[Sequence[Candle]], AnalysisRead]] = {
    "ema_cross": ema_cross,
    "rsi": rsi_signal,
    "macd": macd_signal,
    "bollinger": bollinger,
    "donchian": donchian,
    "momentum": momentum,
    "sma_slope": sma_slope,
    "stochastic": stochastic,
    "atr_regime": atr_regime,
    "hh_ll_trend": hh_ll_trend,
    "double_top_bottom": double_top_bottom,
    "engulfing": engulfing,
    "roc_accel": roc_accel,
}

METHOD_NAMES: list[str] = list(METHODS)


def run_method(name: str, candles: Sequence[Candle]) -> AnalysisRead:
    """Run a registered method by name (NEUTRAL if the name is unknown)."""
    fn = METHODS.get(name)
    if fn is None:
        return AnalysisRead.neutral(f"unknown:{name}")
    return fn(candles)
