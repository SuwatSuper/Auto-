# Layer 1 — Domain (analytics/indicator_catalog)
"""The analyst agent's *declarative* knowledge base of indicator lines (ความรู้).

Where :mod:`domain.analytics.indicator_lines` holds the maths, this module holds
the **knowledge about** each of the 45 standard indicator lines an analyst reads —
its English and Thai names, which of the nine families it belongs to, what price
series it consumes, the name of the function that computes it, and a short Thai
description. It lets an agent *enumerate and explain* its vocabulary (for the
dashboard, logs or a "what do you know?" introspection) rather than only compute
blindly. Pure data + lookup helpers — no I/O, no framework imports.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Thai display name for each of the nine indicator-line families.
GROUP_NAMES_TH: dict[int, str] = {
    1: "เส้นค่าเฉลี่ยเคลื่อนที่ (Moving Average Lines)",
    2: "เส้นในกลุ่ม MACD (Moving Average Convergence Divergence)",
    3: "เส้นในกลุ่ม Bollinger Bands (BB)",
    4: "เส้นในกลุ่ม Oscillator (RSI, Stochastic, CCI, Williams %R)",
    5: "เส้นระบบเมฆอิชิโมกุ (Ichimoku Cloud)",
    6: "เส้นวัดความแข็งแกร่งของเทรนด์ (DMI & ADX)",
    7: "เส้นขอบเขตราคาและแนวรับแนวต้าน (Channels & Envelopes)",
    8: "เส้นระดับราคาทางคณิตศาสตร์และสถิติ (Fibonacci & Pivot)",
    9: "เส้นราคาหยุดและกลับตัว (Trailing Stop Lines)",
}

# Indicator categories (machine-readable roles).
TREND = "trend"
MOMENTUM = "momentum"
VOLATILITY = "volatility"
VOLUME = "volume"
SUPPORT_RESISTANCE = "support_resistance"
TRAILING_STOP = "trailing_stop"


@dataclass(frozen=True)
class IndicatorLine:
    """One entry of indicator knowledge.

    ``inputs`` lists the price series the line consumes (``close``/``high``/``low``/
    ``volume``/``level`` — ``level`` meaning a single prior H/L/C or swing point).
    ``compute`` names the callable in :mod:`domain.analytics.indicator_lines` (or
    ``indicators``) that produces it, or is empty for a fixed reference line.
    """

    number: int
    key: str
    name_en: str
    name_th: str
    group: int
    category: str
    inputs: tuple[str, ...]
    compute: str
    description_th: str

    @property
    def group_name_th(self) -> str:
        return GROUP_NAMES_TH[self.group]


INDICATOR_LINES: tuple[IndicatorLine, ...] = (
    # --- Group 1: Moving-average lines -------------------------------------
    IndicatorLine(
        1, "sma", "SMA Line", "เส้นค่าเฉลี่ยเคลื่อนที่อย่างง่าย",
        1, TREND, ("close",), "sma",
        "เส้นค่าเฉลี่ยเลขคณิตพื้นฐานของราคา N แท่งย้อนหลัง ให้น้ำหนักทุกแท่งเท่ากัน",
    ),
    IndicatorLine(
        2, "ema", "EMA Line", "เส้นค่าเฉลี่ยถ่วงน้ำหนักแบบเอ็กซ์โพเนนเชียล",
        1, TREND, ("close",), "ema",
        "ถ่วงน้ำหนักให้ความสำคัญกับราคาล่าสุดมากกว่า จึงตอบสนองต่อราคาไวกว่า SMA",
    ),
    IndicatorLine(
        3, "wma", "WMA Line", "เส้นค่าเฉลี่ยถ่วงน้ำหนักตามลำดับเวลา",
        1, TREND, ("close",), "wma",
        "ถ่วงน้ำหนักแบบลดหลั่นเชิงเส้นตามลำดับเวลา แท่งล่าสุดได้น้ำหนักสูงสุด",
    ),
    IndicatorLine(
        4, "hma", "HMA Line", "เส้นค่าเฉลี่ยแบบฮัลล์",
        1, TREND, ("close",), "hma",
        "เส้นค่าเฉลี่ยที่ลดความล่าช้า (lag) ได้มากที่สุด ขยับตามราคาได้เร็ว",
    ),
    IndicatorLine(
        5, "smma", "SMMA Line", "เส้นค่าเฉลี่ยแบบปรับเรียบ",
        1, TREND, ("close",), "smma",
        "เส้นค่าเฉลี่ยปรับความเรียบ (Wilder) เหมาะกับการมองแนวโน้มระยะยาว",
    ),
    IndicatorLine(
        6, "cma", "CMA Line", "เส้นค่าเฉลี่ยสะสม",
        1, TREND, ("close",), "cma",
        "เส้นค่าเฉลี่ยสะสมข้อมูลตั้งแต่อดีตจนถึงปัจจุบัน",
    ),
    IndicatorLine(
        7, "vwap", "VWAP Line", "ราคาเฉลี่ยถ่วงน้ำหนักด้วยปริมาณ",
        1, VOLUME, ("high", "low", "close", "volume"), "vwap",
        "ค่าเฉลี่ยราคาที่ถ่วงน้ำหนักด้วยปริมาณการซื้อขาย นิยมใช้ในสัญญาระหว่างวัน",
    ),
    # --- Group 2: MACD -----------------------------------------------------
    IndicatorLine(
        8, "macd_line", "MACD Line", "เส้น MACD",
        2, MOMENTUM, ("close",), "macd",
        "ผลต่างระหว่าง EMA ระยะสั้น (12) และ EMA ระยะยาว (26)",
    ),
    IndicatorLine(
        9, "macd_signal", "Signal Line (MACD)", "เส้นสัญญาณ MACD",
        2, MOMENTUM, ("close",), "macd",
        "เส้นค่าเฉลี่ย EMA 9 ของเส้น MACD ใช้ดูจุดตัดซื้อ/ขาย",
    ),
    IndicatorLine(
        10, "macd_zero", "Zero Line (Center Line)", "เส้นศูนย์ (แกนกลาง)",
        2, MOMENTUM, (), "MACD_ZERO_LINE",
        "เส้นระดับ 0 แกนกลางที่ใช้วัดว่าตลาดเป็นขาขึ้น (เหนือ 0) หรือขาลง (ใต้ 0)",
    ),
    # --- Group 3: Bollinger Bands -----------------------------------------
    IndicatorLine(
        11, "bb_upper", "Upper Band", "เส้นขอบบน Bollinger",
        3, VOLATILITY, ("close",), "bollinger_bands",
        "แนวต้าน คำนวณจากเส้นกลางบวกค่าเบี่ยงเบนมาตรฐาน",
    ),
    IndicatorLine(
        12, "bb_middle", "Middle Band", "เส้นกลาง Bollinger",
        3, VOLATILITY, ("close",), "bollinger_bands",
        "เส้นแกนกลาง โดยทั่วไปคือ SMA 20 วัน",
    ),
    IndicatorLine(
        13, "bb_lower", "Lower Band", "เส้นขอบล่าง Bollinger",
        3, VOLATILITY, ("close",), "bollinger_bands",
        "แนวรับ คำนวณจากเส้นกลางลบค่าเบี่ยงเบนมาตรฐาน",
    ),
    # --- Group 4: Oscillators ---------------------------------------------
    IndicatorLine(
        14, "rsi", "RSI Line", "เส้น RSI",
        4, MOMENTUM, ("close",), "rsi_wilder",
        "เส้นหลักของ Relative Strength Index วิ่งระหว่าง 0-100",
    ),
    IndicatorLine(
        15, "rsi_overbought", "Overbought Line (RSI)", "เส้นซื้อมากเกินไป",
        4, MOMENTUM, (), "RSI_OVERBOUGHT",
        "เส้นระบุขอบเขตการซื้อมากเกินไป มักตั้งไว้ที่ 70 หรือ 80",
    ),
    IndicatorLine(
        16, "rsi_oversold", "Oversold Line (RSI)", "เส้นขายมากเกินไป",
        4, MOMENTUM, (), "RSI_OVERSOLD",
        "เส้นระบุขอบเขตการขายมากเกินไป มักตั้งไว้ที่ 30 หรือ 20",
    ),
    IndicatorLine(
        17, "rsi_ma", "RSI-based MA Line", "เส้นค่าเฉลี่ยของ RSI",
        4, MOMENTUM, ("close",), "rsi_based_ma",
        "เส้นค่าเฉลี่ยเคลื่อนที่ของเส้น RSI อีกชั้นหนึ่ง",
    ),
    IndicatorLine(
        18, "stoch_k", "%K Line", "เส้น %K (Stochastic)",
        4, MOMENTUM, ("high", "low", "close"), "stochastic",
        "เส้นหลักของ Stochastic ที่ตอบสนองต่อราคาอย่างรวดเร็ว",
    ),
    IndicatorLine(
        19, "stoch_d", "%D Line", "เส้น %D (Stochastic)",
        4, MOMENTUM, ("high", "low", "close"), "stochastic",
        "เส้นสัญญาณของ Stochastic เป็น SMA ของ %K",
    ),
    IndicatorLine(
        20, "cci", "CCI Line", "เส้น CCI",
        4, MOMENTUM, ("high", "low", "close"), "cci",
        "Commodity Channel Index วัดการเบี่ยงเบนของราคากับค่าเฉลี่ย",
    ),
    IndicatorLine(
        21, "williams_r", "Williams %R Line", "เส้น Williams %R",
        4, MOMENTUM, ("high", "low", "close"), "williams_r",
        "วัดราคาปิดเทียบกับช่วงสูงสุด-ต่ำสุดในอดีต วิ่งระหว่าง 0 ถึง -100",
    ),
    # --- Group 5: Ichimoku -------------------------------------------------
    IndicatorLine(
        22, "tenkan", "Tenkan-sen (Conversion Line)", "เส้นเทนคัน",
        5, TREND, ("high", "low"), "ichimoku",
        "เส้นสัญญาณระยะสั้น ค่าเฉลี่ยสูงสุด-ต่ำสุดใน 9 วัน",
    ),
    IndicatorLine(
        23, "kijun", "Kijun-sen (Base Line)", "เส้นคิจุน",
        5, TREND, ("high", "low"), "ichimoku",
        "เส้นแนวโน้มระยะกลาง ค่าเฉลี่ยสูงสุด-ต่ำสุดใน 26 วัน",
    ),
    IndicatorLine(
        24, "chikou", "Chikou Span (Lagging Span)", "เส้นชิโคว",
        5, TREND, ("close",), "ichimoku",
        "ราคาปิดปัจจุบันที่วาดเยื้องถอยหลังไปในอดีต 26 วัน",
    ),
    IndicatorLine(
        25, "senkou_a", "Senkou Span A (Leading Span A)", "เส้นเซนโกว A",
        5, TREND, ("high", "low"), "ichimoku",
        "ขอบเมฆฝั่งหนึ่ง = (Tenkan+Kijun)/2 พล็อตล่วงหน้า 26 วัน",
    ),
    IndicatorLine(
        26, "senkou_b", "Senkou Span B (Leading Span B)", "เส้นเซนโกว B",
        5, TREND, ("high", "low"), "ichimoku",
        "ขอบเมฆอีกฝั่ง = ค่าเฉลี่ย 52 วัน พล็อตล่วงหน้า 26 วัน",
    ),
    # --- Group 6: DMI / ADX -----------------------------------------------
    IndicatorLine(
        27, "plus_di", "+DI Line", "เส้น +DI",
        6, TREND, ("high", "low", "close"), "dmi_adx",
        "Plus Directional Indicator แสดงแรงซื้อ (ทิศทางขาขึ้น)",
    ),
    IndicatorLine(
        28, "minus_di", "-DI Line", "เส้น -DI",
        6, TREND, ("high", "low", "close"), "dmi_adx",
        "Minus Directional Indicator แสดงแรงขาย (ทิศทางขาลง)",
    ),
    IndicatorLine(
        29, "adx", "ADX Line", "เส้น ADX",
        6, TREND, ("high", "low", "close"), "dmi_adx",
        "Average Directional Index บอกความแรงของเทรนด์ ยิ่งสูงเทรนด์ยิ่งแรง",
    ),
    IndicatorLine(
        30, "adx_threshold", "ADX Threshold Line", "เส้นเกณฑ์ ADX",
        6, TREND, (), "ADX_TREND_THRESHOLD",
        "เส้นระดับคงที่ มักตั้งที่ 20 หรือ 25 เพื่อยืนยันว่าตลาดเริ่มมีเทรนด์ชัดเจน",
    ),
    # --- Group 7: Channels / Envelopes ------------------------------------
    IndicatorLine(
        31, "keltner_upper", "Keltner Channels Upper Band", "เส้นขอบบน Keltner",
        7, VOLATILITY, ("high", "low", "close"), "keltner_channels",
        "ขอบบน คำนวณจาก EMA ร่วมกับค่า ATR (Average True Range)",
    ),
    IndicatorLine(
        32, "keltner_lower", "Keltner Channels Lower Band", "เส้นขอบล่าง Keltner",
        7, VOLATILITY, ("high", "low", "close"), "keltner_channels",
        "ขอบล่างของ Keltner คำนวณจาก EMA ลบด้วยตัวคูณ ATR",
    ),
    IndicatorLine(
        33, "donchian_upper", "Donchian Channels Upper Band", "เส้นขอบบน Donchian",
        7, SUPPORT_RESISTANCE, ("high",), "donchian_channels",
        "ขอบบน คำนวณจากราคาสูงสุดในรอบ N วัน",
    ),
    IndicatorLine(
        34, "donchian_lower", "Donchian Channels Lower Band", "เส้นขอบล่าง Donchian",
        7, SUPPORT_RESISTANCE, ("low",), "donchian_channels",
        "ขอบล่าง คำนวณจากราคาต่ำสุดในรอบ N วัน",
    ),
    IndicatorLine(
        35, "donchian_middle", "Donchian Channels Middle Band", "เส้นกลาง Donchian",
        7, SUPPORT_RESISTANCE, ("high", "low"), "donchian_channels",
        "เส้นกลาง = (ขอบบน + ขอบล่าง) / 2",
    ),
    IndicatorLine(
        36, "envelope_upper", "Envelopes Upper Band", "เส้นขอบบน Envelope",
        7, VOLATILITY, ("close",), "envelopes",
        "ขอบบนที่เบี่ยงเบนเป็นเปอร์เซ็นต์คงที่จากเส้นค่าเฉลี่ย",
    ),
    IndicatorLine(
        37, "envelope_lower", "Envelopes Lower Band", "เส้นขอบล่าง Envelope",
        7, VOLATILITY, ("close",), "envelopes",
        "ขอบล่างที่เบี่ยงเบนเป็นเปอร์เซ็นต์คงที่จากเส้นค่าเฉลี่ย",
    ),
    # --- Group 8: Fibonacci / Pivot ---------------------------------------
    IndicatorLine(
        38, "pivot_p", "Pivot Point Line (P)", "เส้น Pivot Point (P)",
        8, SUPPORT_RESISTANCE, ("level",), "pivot_points",
        "เส้นแกนกลางราคาสมดุลประจำวัน/สัปดาห์/เดือน",
    ),
    IndicatorLine(
        39, "pivot_resistance", "Resistance Lines (R1-R5)", "เส้นแนวต้าน R1-R5",
        8, SUPPORT_RESISTANCE, ("level",), "pivot_points",
        "เส้นแนวต้านระดับต่างๆ ของ Pivot Points (R1 ถึง R5)",
    ),
    IndicatorLine(
        40, "pivot_support", "Support Lines (S1-S5)", "เส้นแนวรับ S1-S5",
        8, SUPPORT_RESISTANCE, ("level",), "pivot_points",
        "เส้นแนวรับระดับต่างๆ ของ Pivot Points (S1 ถึง S5)",
    ),
    IndicatorLine(
        41, "fib_retracement", "Fibonacci Retracement Lines", "เส้น Fibonacci Retracement",
        8, SUPPORT_RESISTANCE, ("level",), "fibonacci_retracement",
        "เส้นแนวนอนตามอัตราส่วนทองคำ (0/23.6/38.2/50/61.8/78.6/100%) หาจุดย่อตัว",
    ),
    IndicatorLine(
        42, "fib_extension", "Fibonacci Extension Lines", "เส้น Fibonacci Extension",
        8, SUPPORT_RESISTANCE, ("level",), "fibonacci_extension",
        "เส้นแนวนอนหาเป้าหมายราคาทำกำไร (161.8/261.8/423.6%)",
    ),
    # --- Group 9: Trailing-stop lines -------------------------------------
    IndicatorLine(
        43, "parabolic_sar", "Parabolic SAR Dots/Line", "จุด/เส้น Parabolic SAR",
        9, TRAILING_STOP, ("high", "low"), "parabolic_sar",
        "จุดไข่ปลาวิ่งตามราคา เมื่อราคาตัดทะลุ จุดจะย้ายฝั่งทันที (จุดกลับตัว)",
    ),
    IndicatorLine(
        44, "chandelier_exit", "Chandelier Exit Line", "เส้น Chandelier Exit",
        9, TRAILING_STOP, ("high", "low", "close"), "chandelier_exit",
        "Trailing Stop คำนวณจากราคาสูงสุดลบด้วยค่าความผันผวน ATR",
    ),
    IndicatorLine(
        45, "supertrend", "Supertrend Line", "เส้น Supertrend",
        9, TRAILING_STOP, ("high", "low", "close"), "supertrend",
        "เส้นแบ่งแนวโน้มและจุดหยุดขาดทุน เปลี่ยนสีตามทิศทาง (เขียว=ขาขึ้น แดง=ขาลง)",
    ),
)

# Build a key→line index once at import time (data is immutable).
_BY_KEY: dict[str, IndicatorLine] = {line.key: line for line in INDICATOR_LINES}


def all_lines() -> tuple[IndicatorLine, ...]:
    """Return every catalogued indicator line (the full 45-line vocabulary)."""
    return INDICATOR_LINES


def by_key(key: str) -> IndicatorLine:
    """Look up one indicator line by its stable key. Raises ``KeyError`` if absent."""
    return _BY_KEY[key]


def by_group(group: int) -> tuple[IndicatorLine, ...]:
    """Return all indicator lines belonging to a family (1–9)."""
    return tuple(line for line in INDICATOR_LINES if line.group == group)


def by_category(category: str) -> tuple[IndicatorLine, ...]:
    """Return all indicator lines sharing a category (e.g. ``"momentum"``)."""
    return tuple(line for line in INDICATOR_LINES if line.category == category)


def keys() -> tuple[str, ...]:
    """Return the stable keys of every indicator line, in catalogue order."""
    return tuple(line.key for line in INDICATOR_LINES)
