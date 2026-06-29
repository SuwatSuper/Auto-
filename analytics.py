# -*- coding: utf-8 -*-
"""analytics.py — DOMAIN LAYER (pure calculators: per-bill confidence + company rollup)

⚠️ RECONSTRUCTED MODULE (v9-rebuild 2026-06)
   ต้นฉบับเดิมถูกส่งมาเป็นไฟล์ "ว่างเปล่า 0 ไบต์" — ฟังก์ชันหายทั้งหมด.
   สร้างใหม่จาก contract จริงของ downstream (reporting.py) ให้ระบบกลับมารันได้:

   เส้นทางหลัก (clean/core path — ใช้เสมอ):
     • compute_bill_confidence(b)   → set b['parse_confidence'] ('HIGH'|'MID'|'LOW')
                                       + b['parse_confidence_reasons'] (list) + b['parse_confidence_score']
                                       FAITHFUL contract; ⚠ "น้ำหนักการให้คะแนน" เป็นการสร้างใหม่ (โปร่งใส/ปรับได้)
     • summarize_by_company(bills)  → list[{key,period,bill_count,subtotal,vat,total,bills}]
                                       FAITHFUL: key/period จำลอง bill_company_label/_get_p เป๊ะ
     • confidence_tier(score)       → map คะแนน→tier ด้วย CONF_TIERS จริงจาก config

   เส้นทางเต็ม (full mode `--full` เท่านั้น — ออปชัน, plotly อาจไม่มี):
     • load_audit_excel / cluster_products / detect_price_outliers /
       detect_unit_anomalies / build_dashboard_figs
       RECONSTRUCTED (SIMPLIFIED) — รักษา contract คอลัมน์/คืนค่าไว้ครบ + degrade ถ้าไม่มี plotly.
       *ไม่กระทบผลตรวจ/รายงาน clean เลย* (full mode เป็น add-on)

   หมายเหตุ DAG: analytics พึ่ง config + leaf เท่านั้น (ไม่ import main/reporting) → ไม่มี cycle.
"""
from __future__ import annotations

import math
import os

import pandas as pd

from config import CONF_TIERS, ANALYTICS_CFG, PRODUCT_CATEGORIES, ADDON_CFG
from puopuy_core import _taxid_checksum_ok, normalize_text

__all__ = [
    "compute_bill_confidence", "summarize_by_company", "confidence_tier",
    "build_unit_index", "addon_check_withholding",
    "load_audit_excel", "cluster_products",
    "detect_price_outliers", "detect_unit_anomalies", "build_dashboard_figs",
]


# ════════════════════════ confidence tier (FAITHFUL) ════════════════════════
def confidence_tier(score):
    """map คะแนน 0..1 → 'HIGH'|'MID'|'LOW' ตาม CONF_TIERS (ค่าจริงจาก config)."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return 'LOW'
    if s >= CONF_TIERS['HIGH_MIN']:
        return 'HIGH'
    if s >= CONF_TIERS['MID_MIN']:
        return 'MID'
    return 'LOW'


# ═══════════════ per-bill parse confidence (contract FAITHFUL; weights ⚠APPROX) ═══════════════
# โมเดลหักคะแนนแบบโปร่งใส: เริ่ม 1.0 แล้วหักตาม "สัญญาณว่าการ parse อาจไม่น่าเชื่อถือ".
# ⚠ น้ำหนักด้านล่างเป็นการสร้างใหม่ (ต้นฉบับไม่ทราบ) — ปรับได้โดยไม่กระทบ schema/รายงาน.
_W_NO_TAXID = 0.15
_W_BAD_TAXID = 0.10
_W_NO_IV = 0.15
_W_NO_DATE = 0.10
_W_NO_ITEMS = 0.20
_W_MISSING_AMT = 0.08   # ต่อช่อง (subtotal/vat/total) ที่เป็น None
_W_AMOUNT_LOW = 0.15    # parser ตั้ง amount_confidence == 'LOW'
_W_VAT_INCONSISTENT = 0.10


def compute_bill_confidence(b):
    """ให้คะแนนความเชื่อมั่นของการ parse 1 บิล แล้วเขียนผลลงบิล (in-place).

    เขียน 3 คีย์ (reporting อ่าน parse_confidence + parse_confidence_reasons):
      b['parse_confidence']         : 'HIGH' | 'MID' | 'LOW'
      b['parse_confidence_reasons'] : list[str] เหตุผลที่คะแนนลด
      b['parse_confidence_score']   : float 0..1 (ไว้ตามรอย/debug)
    ไม่แตะ logic parse / ไม่เพิ่ม issue / ปลอดภัยเสมอ (try ครอบ — พังไม่ได้).
    """
    reasons = []
    score = 1.0
    try:
        # เลขผู้เสียภาษี
        tid = (b.get('tax_id') or '').strip()
        if not tid:
            score -= _W_NO_TAXID
            reasons.append('ไม่พบเลขผู้เสียภาษี')
        elif not _taxid_checksum_ok(tid):
            score -= _W_BAD_TAXID
            reasons.append('เลขผู้เสียภาษี checksum ไม่ผ่าน')

        # เลขที่ใบกำกับ
        if not ((b.get('iv_number') or '').strip()):
            score -= _W_NO_IV
            reasons.append('ไม่พบเลขที่ใบกำกับ')

        # วันที่
        if not b.get('iv_date'):
            score -= _W_NO_DATE
            reasons.append('ไม่พบวันที่ในเอกสาร')

        # รายการสินค้า
        if not (b.get('items') or []):
            score -= _W_NO_ITEMS
            reasons.append('ไม่พบรายการสินค้า')

        # ยอดเงิน
        miss_amt = sum(1 for k in ('subtotal', 'vat', 'total') if b.get(k) is None)
        if miss_amt:
            score -= _W_MISSING_AMT * miss_amt
            reasons.append(f'ยอดเงินขาด {miss_amt} ช่อง (subtotal/vat/total)')

        # amount_confidence ที่ parser ประเมินไว้
        if str(b.get('amount_confidence', '')).upper() == 'LOW':
            score -= _W_AMOUNT_LOW
            reasons.append('ความเชื่อมั่นการอ่านยอดเงินต่ำ (parser)')

        # ตรวจ VAT ≈ 7% แบบหยาบ (ถ้ามีครบ) — ไม่ตรงนัก = สัญญาณ parse เพี้ยน
        sub, vat = b.get('subtotal'), b.get('vat')
        if sub is not None and vat is not None:
            try:
                fsub, fvat = float(sub), float(vat)
                if fsub > 0 and fvat > 1.0:  # vat>1 = เป็น amount ไม่ใช่ rate
                    if abs(fvat - fsub * 0.07) > max(1.0, fsub * 0.01):
                        score -= _W_VAT_INCONSISTENT
                        reasons.append('VAT ไม่ใกล้ 7% ของยอดก่อนภาษี')
            except (TypeError, ValueError):
                pass
    except Exception:
        # ปลอดภัย: ถ้าประเมินพัง ให้ถือว่าต้องตรวจมือ (LOW) แทนการ crash
        b['parse_confidence_score'] = 0.0
        b['parse_confidence'] = 'LOW'
        b['parse_confidence_reasons'] = ['ประเมิน confidence ไม่สำเร็จ']
        return b

    score = max(0.0, min(1.0, score))
    b['parse_confidence_score'] = round(score, 4)
    b['parse_confidence'] = confidence_tier(score)
    b['parse_confidence_reasons'] = reasons
    return b


# ═══════════════════ unit index (FAITHFUL — contract จาก r_itm015) ═══════════════════
def _safe_items(b):
    """[GAP-B 2026-06-28] คืน list ของ item-dict เสมอ — กัน bill['items'] ที่ "มีอยู่แต่เป็น non-list"
    (None/int/str — บิลภายนอก/บางส่วน/ไฟล์เพี้ยนอนาคต) หรือสมาชิก non-dict ทำ build_unit_index/
    wht_candidates ครัช. ฟังก์ชันชั้น analytics รัน"ก่อน/นอก" run_rules → ไม่มี per-rule try ดัก →
    ครัชจะลามขึ้น. `or []` เดิมกัน None/falsy ได้ แต่ไม่กัน truthy-non-list (เช่น items=5). corpus
    จริงทุกบิล items เป็น list-of-dict → no-op → golden-NEUTRAL คง 23b315e8."""
    its = b.get('items')
    return [it for it in its if isinstance(it, dict)] if isinstance(its, list) else []


def build_unit_index(all_bills):
    """รวม index ของหน่วยที่ใช้ต่อ "ชื่อสินค้า" ข้ามทุกบิล.

    คืน dict: idx[item_name] = set(units).  ใช้โดย rules_engine.r_itm015 เพื่อจับ
    "สินค้าชื่อเดียวกันแต่ใช้หน่วยต่างกลุ่มจริง" (r_itm015 เรียก _unit_canon ต่อเอง).
    """
    from collections import defaultdict
    idx = defaultdict(set)
    for b in (all_bills or []):
        for it in _safe_items(b):
            name = it.get('name')
            unit = it.get('unit')
            # [ADR-139/RB-02] coerce name/unit เป็น str ให้ตรงกับที่ run_rules coerce (rules_engine:289-291)
            #   — build_unit_index รัน "ก่อน" run_rules → ถ้า name เป็น non-str (int รหัสสินค้า) จะ key
            #   ด้วยค่าดิบ แต่ r_itm015 lookup ด้วย name ที่ coerce แล้ว (str) → key ไม่ตรง → ITM015 พลาด
            #   cross-unit conflict (false-negative). corpus ทุก item str → str() no-op → golden-neutral.
            if not isinstance(name, str):
                name = '' if name is None else str(name)
            if not isinstance(unit, str):
                unit = '' if unit is None else str(unit)
            if name and unit:
                idx[name].add(unit)
    return idx


# ═══════════ addon: ภงด.53 withholding candidates (advisory · mesh-only) ═══════════
# ห่อโดย agents/wht_agent.py. เป็น add-on อ่านบิลอย่างเดียว (ไม่แก้บิล/ไม่กระทบ golden hash).
# ค่า rate/threshold/keywords มาจาก ADDON_CFG ใน config.py (ไม่ตั้งใหม่).
def addon_check_withholding(bills):
    """หาบิลที่ "น่าจะต้องหัก ณ ที่จ่าย 3% (ภงด.53)" จากคีย์เวิร์ดค่าบริการ.

    คืน list ของ candidate dict (contract ตรงกับ wht_agent.py):
        {file, sheet, iv, company, service_subtotal, expected_wht_3pct,
         service_items, severity, note}
    เกณฑ์: รวมยอด item ที่ชื่อมีคีย์เวิร์ด 'ค่าบริการ/ค่าจ้าง/...' ≥ WHT_THRESHOLD
           → คาดว่าควรหัก = service_subtotal × WHT_RATE.
    """
    rate = ADDON_CFG.get('WHT_RATE', 0.03)
    threshold = ADDON_CFG.get('WHT_THRESHOLD', 1000)
    keywords = ADDON_CFG.get('WHT_SERVICE_KEYWORDS', [])
    out = []
    for b in (bills or []):
        service_names = []
        service_amt = 0.0
        for it in _safe_items(b):
            nm = normalize_text(it.get('name'))
            if not nm:
                continue
            if any(kw and kw in nm for kw in keywords):
                service_names.append(it.get('name'))
                service_amt += _num(it.get('amount'))
        if service_names and service_amt >= threshold:
            expected = round(service_amt * rate, 2)
            out.append({
                'file': b.get('file', ''),
                'sheet': b.get('sheet', ''),
                'iv': b.get('iv_number_raw') or b.get('iv_number') or '-',  # [DISPLAY-FAITHFUL] เลขดิบตามใบ
                'company': b.get('master_key') or b.get('company', '') or '-',
                'service_subtotal': round(service_amt, 2),
                'expected_wht_3pct': expected,
                'service_items': ', '.join(str(n) for n in service_names[:5]),
                'severity': 'WARNING',
                'note': (f'พบค่าบริการรวม {service_amt:,.2f} บาท '
                         f'— อาจต้องหัก ณ ที่จ่าย 3% = {expected:,.2f} บาท (ภงด.53)'),
            })
    return out


# ════════════ period label (FAITHFUL — จำลอง reporting._get_p เป๊ะ) ════════════
def _period_label(d):
    """= reporting._get_p: พ.ศ. 2 หลัก + เดือน เช่น '68.11' ; ไม่มีวันที่ → '-'."""
    if not d:
        return '-'
    try:
        yr = d.year
        be = yr + 543 if yr < 2500 else yr
        return f"{(be % 100):02d}.{d.month:02d}"
    except Exception:
        return '-'


def _num(x):
    """ตัวเลขปลอดภัยสำหรับการบวกยอด (None/แปลงไม่ได้ → 0.0)."""
    if x is None:
        return 0.0
    try:
        f = float(x)
    except (TypeError, ValueError):
        return 0.0
    # [M6] กัน NaN ลามเข้ายอดรวม/อันดับ (float('nan') แปลงผ่านแต่ != ตัวเอง)
    # [REP-M1 2026-06-20] กัน ±inf ด้วย (พี่น้อง M6) — _num(inf)=inf เคยครองอันดับ -subtotal + ทำยอดรวมเพี้ยน.
    #   ข้อมูลจริง subtotal เป็น float จำกัด|None เสมอ → ผลเท่าเดิม (golden ไม่ขยับ).
    return 0.0 if not math.isfinite(f) else f   # isfinite = False ทั้ง NaN และ ±inf


# ═══════════════════ summarize_by_company (FAITHFUL contract) ═══════════════════
def summarize_by_company(bills):
    """สรุปต่อ "บริษัท" (จัดกลุ่มด้วย master_key — เหมือน reporting High-Risk/Summary).

    หลักฐานเชิงประจักษ์ (baseline เดิม companies=2 บนชุด 81 ไฟล์, master 1 บริษัท):
      → จัดกลุ่มด้วย `b['master_key']` ล้วน (matched + บัคเก็ต '(ไม่พบใน master)') = 2
      → ไม่ใช้ fallback ชื่อไฟล์/company และไม่ split ตามงวด (นั่นทำให้ได้ 21/46 ซึ่งไม่ตรง baseline)

    คืน list ของ dict (เรียง deterministic ตาม key):
        {'key','period','bill_count','subtotal','vat','total','bills'}
    contract ตรงกับ reporting (_xlsx_sheet_summary / _xlsx_sheet_ranking):
      - subtotal/vat/total เป็นตัวเลขเสมอ (None→0) เพราะ ranking sort ด้วย -subtotal
      - bills = บิลในกลุ่ม (reporting นับ issues/critical ต่อจากตรงนี้)
      - period = งวดบัญชีไม่ซ้ำในกลุ่ม เรียงแล้ว join ด้วย ', ' (deterministic; '-' ถ้าไม่มีวันที่)
    """
    groups = {}
    order = []
    for b in (bills or []):
        key = b.get('master_key') or '(ไม่พบใน master)'
        if key not in groups:
            groups[key] = {
                'key': key, 'bill_count': 0,
                'subtotal': 0.0, 'vat': 0.0, 'total': 0.0,
                'bills': [], '_periods': set(),
            }
            order.append(key)
        g = groups[key]
        g['bill_count'] += 1
        g['subtotal'] += _num(b.get('subtotal'))
        g['vat'] += _num(b.get('vat'))
        g['total'] += _num(b.get('total'))
        g['bills'].append(b)
        g['_periods'].add(_period_label(b.get('iv_date')))

    out = []
    for key in sorted(order, key=str):
        g = groups[key]
        periods = sorted(p for p in g.pop('_periods') if p and p != '-')
        g['period'] = ', '.join(periods) if periods else '-'
        out.append(g)
    return out


# ════════════════════════════════════════════════════════════════════════════
# FULL-MODE ANALYTICS (RECONSTRUCTED · SIMPLIFIED) — ออปชัน, ไม่กระทบ clean path
# ════════════════════════════════════════════════════════════════════════════
def load_audit_excel(excel_path):
    """อ่านทุกชีตของไฟล์รายงาน → {sheet_name: DataFrame}. พัง/ไม่มีไฟล์ → {}."""
    try:
        if not excel_path or not os.path.exists(excel_path):
            return {}
        return pd.read_excel(excel_path, sheet_name=None)
    except Exception:
        return {}


def _category_of(name):
    """หา _category จาก PRODUCT_CATEGORIES (keyword match) — ไม่เจอ → 'อื่นๆ'."""
    s = normalize_text(name)
    for cat, spec in PRODUCT_CATEGORIES.items():
        for kw in spec.get('keywords', []):
            if kw and kw in s:
                return cat
    return 'อื่นๆ'


def cluster_products(items_df):
    """[SIMPLIFIED] จัดกลุ่มสินค้าแบบ deterministic ด้วยหมวด (category).

    เพิ่มคอลัมน์ตาม contract ของ run_analytics: '_category', '_cluster_id'.
    ⚠ ต้นฉบับใช้ fuzzy hybrid; เวอร์ชันนี้ใช้ category-based (เสถียร/อ่านง่าย).
    """
    df = items_df.copy()
    name_col = None
    for cand in ('ชื่อสินค้า', 'name', 'รายการ', 'สินค้า'):
        if cand in df.columns:
            name_col = cand
            break
    if name_col is None:
        # ไม่มีคอลัมน์ชื่อ → ทั้งหมดเป็นกลุ่มเดียว
        df['_category'] = 'อื่นๆ'
        df['_cluster_id'] = 0
        return df
    df['_category'] = df[name_col].map(_category_of)
    cats = {c: i for i, c in enumerate(sorted(df['_category'].dropna().unique()))}
    df['_cluster_id'] = df['_category'].map(cats).fillna(-1).astype(int)
    return df


def _price_col(df):
    for cand in ('ราคา/หน่วย', 'ราคาต่อหน่วย', 'ราคา', 'unit_price', 'price'):
        if cand in df.columns:
            return cand
    return None


def detect_price_outliers(df_clustered):
    """[SIMPLIFIED] ตั้งธง '_price_outlier' ด้วย IQR ภายในแต่ละ cluster."""
    df = df_clustered.copy()
    pcol = _price_col(df)
    df['_price_outlier'] = False
    if pcol is None or '_cluster_id' not in df.columns:
        return df
    k = ANALYTICS_CFG.get('PRICE_OUTLIER_IQR', 1.5)
    min_n = ANALYTICS_CFG.get('PRICE_OUTLIER_MIN_SAMPLES', 5)
    prices = pd.to_numeric(df[pcol], errors='coerce')
    for cid, idx in df.groupby('_cluster_id').groups.items():
        sub = prices.loc[idx].dropna()
        if len(sub) < min_n:
            continue
        q1, q3 = sub.quantile(0.25), sub.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - k * iqr, q3 + k * iqr
        mask = (prices.loc[idx] < lo) | (prices.loc[idx] > hi)
        df.loc[mask.index[mask.fillna(False)], '_price_outlier'] = True
    return df


def detect_unit_anomalies(df_clustered):
    """[SIMPLIFIED] ตั้งธง '_unit_rare' = หน่วยที่พบน้อยกว่า threshold ภายใน cluster."""
    df = df_clustered.copy()
    df['_unit_rare'] = False
    ucol = None
    for cand in ('หน่วย', 'unit'):
        if cand in df.columns:
            ucol = cand
            break
    if ucol is None or '_cluster_id' not in df.columns:
        return df
    thr = ANALYTICS_CFG.get('UNIT_RARE_THRESHOLD', 0.10)
    for cid, idx in df.groupby('_cluster_id').groups.items():
        sub = df.loc[idx, ucol].fillna('').astype(str)
        if len(sub) == 0:
            continue
        freq = sub.value_counts(normalize=True)
        rare_units = set(freq[freq < thr].index)
        mask = sub.isin(rare_units) & (sub != '')
        df.loc[mask.index[mask], '_unit_rare'] = True
    return df


def build_dashboard_figs(sheets, df_clustered):
    """[SIMPLIFIED] สร้าง Plotly figures. ไม่มี plotly → คืน [] (degrade graceful)."""
    try:
        import plotly.express as px  # noqa: F401
    except Exception:
        return []
    figs = []
    try:
        if '_category' in df_clustered.columns:
            cat_counts = (df_clustered['_category'].value_counts()
                          .reset_index())
            cat_counts.columns = ['category', 'count']
            figs.append(px.bar(cat_counts, x='category', y='count',
                               title='จำนวนรายการต่อหมวดสินค้า'))
        pcol = _price_col(df_clustered)
        if pcol is not None and '_category' in df_clustered.columns:
            tmp = df_clustered.copy()
            tmp[pcol] = pd.to_numeric(tmp[pcol], errors='coerce')
            figs.append(px.box(tmp.dropna(subset=[pcol]), x='_category', y=pcol,
                               title='การกระจายราคาต่อหมวด (กล่อง)'))
    except Exception:
        pass
    return figs
