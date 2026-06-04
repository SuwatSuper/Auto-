# -*- coding: utf-8 -*-
"""thai_text.py — THAI TEXT analysis: fuzzy-dict match, PyThaiNLP spell, category, OCR, formality

ย้ายมาจาก monolith แบบ "คัดลอกเป๊ะทุกตัวอักษร" — logic เดิม 100%.
รวมฟังก์ชันด้านภาษาไทย/OCR ที่ทั้ง parser และ rules_engine ใช้ร่วม:
  find_similar_in_thai_dict, pythainlp_spell_check, predict_category,
  detect_ocr_input, normalize_ocr, formal_language_score, gen_explanation

⚠️ cache ที่ใช้ร่วม (_FUZZY_DICT_CACHE / _PYTHAINLP_CACHE) อยู่ใน state.py
   เพื่อให้ reset_run_state() ล้างผ่าน .clear() แล้วทุกโมดูลเห็น dict ตัวเดียวกัน.
   lazy caches (_CONSTRUCTION_DICT_BY_LEN / _PYTHAINLP_STEM_BLOCKLIST) ก็อยู่ state.py.

ตำแหน่งใน DAG:  config + state + diagnostics(_trim_cache)  →  [thai_text]  →  parser / rules / reporting
"""
import re
from collections import defaultdict

from rapidfuzz import fuzz

import state
from config import *
from diagnostics import _trim_cache

# PyThaiNLP เป็น optional dependency — ไม่มีก็รันได้ (degrade graceful) เหมือน main เดิม
try:
    from pythainlp.spell import correct as _pythainlp_correct
    PYTHAINLP_AVAILABLE = True
except ImportError:
    PYTHAINLP_AVAILABLE = False


# v5.7: cache สำหรับ fuzzy match → ย้ายไป state._FUZZY_DICT_CACHE (พาส2b)
# _CONSTRUCTION_DICT_BY_LEN-> moved to state.py

def _build_dict_buckets():
    state._CONSTRUCTION_DICT_BY_LEN = defaultdict(list)
    for w in CONSTRUCTION_DICT:
        state._CONSTRUCTION_DICT_BY_LEN[len(w)].append(w)

def find_similar_in_thai_dict(word, threshold=None):
    """v8.0: tier-based matching + length-ratio guard to cut false positives"""
    if threshold is None: threshold = CFG['FUZZY_THAI_DICT_THRESHOLD']
    if not word: return (None, 0)
    if word in CONSTRUCTION_DICT: return None, 100
    key = (word, threshold)
    if key in state._FUZZY_DICT_CACHE: return state._FUZZY_DICT_CACHE[key]
    if len(state._FUZZY_DICT_CACHE) >= CFG.get('MAX_FUZZY_DICT_CACHE', 50000):
        _trim_cache(state._FUZZY_DICT_CACHE, CFG.get('MAX_FUZZY_DICT_CACHE', 50000) // 2)
    if state._CONSTRUCTION_DICT_BY_LEN is None: _build_dict_buckets()
    L = len(word)
    # v8.0: คำสั้นมาก (≤2 ตัว) — fuzzy ไม่น่าเชื่อถือ ข้าม
    if L <= 2:
        state._FUZZY_DICT_CACHE[key] = (None, 0)
        return (None, 0)
    # v8.0: Tier 1 — bucket ±1 ตัวอักษร (เข้มที่สุด)
    # Tier 2 — bucket ±2 (ถ้า Tier 1 ไม่เจอ)
    candidates_t1 = []
    for dl in range(-1, 2):
        candidates_t1.extend(state._CONSTRUCTION_DICT_BY_LEN.get(L + dl, []))
    candidates_t2 = []
    for dl in [-2, 2]:
        candidates_t2.extend(state._CONSTRUCTION_DICT_BY_LEN.get(L + dl, []))
    if not candidates_t1 and not candidates_t2:
        result = (None, 0)
        state._FUZZY_DICT_CACHE[key] = result
        return result
    def _best_match(candidates, cutoff):
        try:
            from rapidfuzz import process
            best = process.extractOne(word, candidates, scorer=fuzz.ratio,
                                      score_cutoff=cutoff)
            if best and best[1] < 100:
                return (best[0], int(best[1]))
        except Exception as _e:
            best_w, best_s = None, 0
            for c in candidates:
                s = fuzz.ratio(word, c)
                if cutoff <= s < 100 and s > best_s:
                    best_s = s; best_w = c
            if best_w: return (best_w, best_s)
        return (None, 0)
    # Tier 1: tight threshold
    result = _best_match(candidates_t1, threshold)
    # Tier 2: slightly higher threshold (95) to compensate for wider bucket
    if result[0] is None and candidates_t2:
        result = _best_match(candidates_t2, max(threshold, 92))
    # v8.0: length-ratio guard — ถ้าผลต่างความยาวมากกว่า 30% → false positive สูง
    if result[0] is not None:
        match_len = len(result[0])
        if match_len > 0 and (abs(L - match_len) / max(L, match_len)) > 0.35:
            result = (None, 0)
    state._FUZZY_DICT_CACHE[key] = result
    return result


# v5.8 [FIX-5]: stems ที่ถ้าเจอใน orig word → ห้าม PyThaiNLP แก้
# _PYTHAINLP_STEM_BLOCKLIST-> moved to state.py

def _build_pythainlp_stems():
    """v5.8: คำใน CONSTRUCTION_DICT + WHITELIST ที่ยาว ≥ 3 ตัว
    ใช้เป็น 'protected stem' — ถ้าเจอเป็น substring ใน orig word → skip"""
    stems = set()
    for w in PYTHAINLP_WHITELIST:
        if len(w) >= 3: stems.add(w)
    for w in CONSTRUCTION_DICT:
        if len(w) >= 3: stems.add(w)
    state._PYTHAINLP_STEM_BLOCKLIST = stems

# _PYTHAINLP_CACHE → ย้ายไป state._PYTHAINLP_CACHE (พาส2b)

def pythainlp_spell_check(text):
    """v8.0: stronger similarity guard + length-ratio guard + min word length"""
    if not PYTHAINLP_AVAILABLE: return []
    if state._PYTHAINLP_STEM_BLOCKLIST is None: _build_pythainlp_stems()
    if len(state._PYTHAINLP_CACHE) >= CFG.get('MAX_PYTHAINLP_CACHE', 50000):
        _trim_cache(state._PYTHAINLP_CACHE, CFG.get('MAX_PYTHAINLP_CACHE', 50000) // 2)
    out = []
    try:
        # v8.0: ≥5 ตัว (เดิม 4) — คำสั้น 4 ตัวมี false positive สูงมาก
        words = re.findall(r'[ก-๙]{5,}', text)
        for w in words:
            if w in PYTHAINLP_WHITELIST: continue
            if w in CONSTRUCTION_DICT: continue
            if any(stem in w for stem in state._PYTHAINLP_STEM_BLOCKLIST): continue
            if w in state._PYTHAINLP_CACHE:
                cached = state._PYTHAINLP_CACHE[w]
                if cached: out.append((w, cached))
                continue
            try:
                c = _pythainlp_correct(w)
                state._PYTHAINLP_CACHE[w] = None
                if not c or c == w or len(c) < 3: continue
                # v8.0: ความยาวต่างกันไม่เกิน 1 (เดิม 2) — กัน FP เพิ่มเติม
                if abs(len(c) - len(w)) > 1: continue
                sim = fuzz.ratio(w, c)
                # v8.0: เพิ่ม threshold 80→85
                if sim < max(CFG['PYTHAINLP_SIM_THRESHOLD'], 85): continue
                if c in PYTHAINLP_WHITELIST: continue
                if sim == 100: continue
                if any(stem in c for stem in state._PYTHAINLP_STEM_BLOCKLIST): continue
                # v8.0: ตรวจซ้ำว่า correction อยู่ใน CONSTRUCTION_DICT (ห้าม suggest คำ dict)
                if c in CONSTRUCTION_DICT: continue
                state._PYTHAINLP_CACHE[w] = c
                out.append((w, c))
            except Exception: pass
    except Exception: pass
    return out

def predict_category(name):
    scores = {}
    for cat, info in PRODUCT_CATEGORIES.items():
        score = sum(1 for kw in info['keywords'] if kw in name)
        if score > 0: scores[cat] = score
    return max(scores, key=scores.get) if scores else 'ไม่ระบุ'

# ============================================================
# 🆕 v5.4 HELPERS
# ============================================================

def detect_ocr_input(text):
    if not text: return False, 0.0
    hits = 0
    for pat in OCR_CFG['OCR_INDICATORS']:
        if re.search(pat, text): hits += 1
    score = min(1.0, hits / max(1, len(OCR_CFG['OCR_INDICATORS'])))
    is_ocr = OCR_CFG['ASSUME_OCR_INPUT'] or (OCR_CFG['AUTO_DETECT'] and hits >= 2)
    return is_ocr, score

def normalize_ocr(text):
    if not text: return text
    out = str(text)
    for wrong, right in OCR_CFG['TH_CONFUSIONS']:
        out = out.replace(wrong, right)
    if OCR_CFG['AGGRESSIVE']:
        for ch, sub in OCR_CFG['EN_CONFUSIONS'].items():
            out = out.replace(ch, sub)
    return out


def formal_language_score(text):
    if not text or len(text.strip()) < 2: return 0.5
    t = str(text); score = 0.5
    informal_hits = sum(1 for w in FORMAL_CFG['INFORMAL_WORDS'] if w in t)
    score -= informal_hits * 0.10
    formal_hits = sum(1 for w in FORMAL_CFG['FORMAL_INDICATORS'] if w in t)
    score += formal_hits * 0.10
    if re.search(FORMAL_CFG['EMOJI_PATTERN'], t): score -= 0.20
    if re.search(FORMAL_CFG['INFORMAL_PUNCT'], t): score -= 0.15
    if re.search(r'\d+\s*(?:กก\.|ก\.ก\.|ลิตร|มล\.|มม\.|ซม\.|ม\.|นิ้ว|วัตต์|แอมป์|โวลต์|W|A|V|kg|ml|cm)', t):
        score += 0.15
    if re.search(r'\d+(?:[/x×]\d+)+', t): score += 0.10
    return max(0.0, min(1.0, score))


def gen_explanation(state, evidence='', action='', tier='', confidence_tier=''):
    parts = []
    state_intro = {
        'VERIFIED': 'ตรวจสอบผ่าน',
        'NEEDS_REVIEW': 'ควรตรวจทาน',
        'UNVERIFIABLE': 'ไม่สามารถยืนยันได้',
        'CONFLICTED': 'ข้อมูลขัดแย้ง',
        'ERROR': 'เกิดข้อผิดพลาด',
    }
    intro = state_intro.get(state, state)
    if tier:
        intro += f' ({tier})'
    if confidence_tier:
        intro += f' [conf={confidence_tier}]'
    if EXPLAIN_CFG['INCLUDE_EVIDENCE'] and evidence:
        parts.append(f"{intro} — {evidence}")
    else:
        parts.append(intro)
    if EXPLAIN_CFG['INCLUDE_ACTION'] and action and len(parts) < EXPLAIN_CFG['MAX_SENTENCES']:
        parts.append(f"แนะนำ: {action}")
    out = ' '.join(parts[:EXPLAIN_CFG['MAX_SENTENCES']])
    return out[:EXPLAIN_CFG['MAX_LENGTH']]


__all__ = ['PYTHAINLP_AVAILABLE', '_build_dict_buckets', 'find_similar_in_thai_dict',
           '_build_pythainlp_stems', 'pythainlp_spell_check', 'predict_category',
           'detect_ocr_input', 'normalize_ocr', 'formal_language_score', 'gen_explanation']
