# -*- coding: utf-8 -*-
"""webverify.py — Online Product Verification layer (leaf)

ชั้น "ตรวจสอบสินค้าออนไลน์" (ทางเลือก/ปิดได้) — ย้ายมาจาก main แบบ **คัดลอกเป๊ะ** (logic เดิม 100%).
ครอบคลุม: web governor (_WEB_STATE + circuit breaker), web_request, sqlite cache (init/get/set),
          tier1/tier2 verification (DuckDuckGo/SerpAPI), verify_product, run_product_verification.

⚠️ ไม่ถูกเรียกใน pipeline ตรวจหลัก (golden_master ไม่แตะชั้นนี้) — เป็นส่วนเสริม online เท่านั้น
   reset_run_state() ใน main เรียก web_state_reset() ผ่าน re-export (`from webverify import *`)

ตำแหน่งใน DAG (พึ่งเฉพาะ leaf — ไม่พึ่ง main):
    config + puopuy_core + thai_text  →  [webverify]
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request

try:
    from tqdm import tqdm
except Exception:                      # tqdm เป็น optional — ไม่มีก็ยังรันได้
    def tqdm(x, *a, **k):
        return x

from config import (  # [F3] explicit (เดิม import *)
    CONF_TIERS, CONSTRUCTION_DICT, FORMAL_CFG, PRODUCT_CATEGORIES, SOURCE_TRUST,
    VERIFY_CFG, WEB_GOV)
from puopuy_core import to_conf01
# [OBJ-OFFLINE/bug-fix] confidence_tier ถูกใช้ใน tier1_verify/tier2_verify แต่เดิม "ไม่ได้ import"
#   → ทำให้ tier1 (ชั้นออฟไลน์) NameError มาตลอด (แฝงอยู่เพราะ pipeline หลักไม่เคยเรียก webverify).
#   import จาก analytics (พึ่ง config/puopuy_core เท่านั้น — ไม่ circular) เพื่อให้ "ตัวตรวจออฟไลน์ใช้งานได้จริง".
from analytics import confidence_tier
from thai_text import (predict_category, find_similar_in_thai_dict, pythainlp_spell_check,
                       detect_ocr_input, normalize_ocr, formal_language_score, gen_explanation,
                       PYTHAINLP_AVAILABLE)


_WEB_STATE = {
    'total_requests': 0,
    'total_failures': 0,
    'consecutive_failures': 0,
    'circuit_open': False,
}

def web_state_reset():
    _WEB_STATE.update({'total_requests':0,'total_failures':0,
                       'consecutive_failures':0,'circuit_open':False})

def web_can_request():
    if _WEB_STATE['circuit_open']: return False
    if _WEB_STATE['total_requests'] >= WEB_GOV['MAX_TOTAL_REQUESTS']: return False
    return True

def web_record_success():
    _WEB_STATE['total_requests'] += 1
    _WEB_STATE['consecutive_failures'] = 0

def web_record_failure():
    _WEB_STATE['total_requests'] += 1
    _WEB_STATE['total_failures'] += 1
    _WEB_STATE['consecutive_failures'] += 1
    if _WEB_STATE['consecutive_failures'] >= WEB_GOV['CIRCUIT_BREAKER_FAILS']:
        _WEB_STATE['circuit_open'] = True


# ----------------------------------------------------------------------
# ★ OFFLINE-ONLY (กฎเหล็กข้อ 1) ★
#   ปุ้มปุ้ยทำงานออฟไลน์ล้วน: ข้อมูลใบกำกับ (รวมชื่อสินค้า) ต้องไม่ออกจากเครื่อง.
#   ชั้นนี้มีจุดออกเน็ตจุดเดียวคือ web_request() — บังคับ "ปิดเป็นค่าตั้งต้น"
#   จะเปิด live-fetch ได้เฉพาะ "ตั้งใจ" ผ่าน env  PUOPUY_ALLOW_NETWORK=1  (opt-in)
#   ซึ่งต้องอยู่ "นอกเส้น audit/CI" เสมอ. นโยบายมาจาก offline_guard (จุดเดียวทั้งระบบ).
#   เมื่อปิด: คืน None ทันที (ไม่แตะ urllib/socket) → tier2 ถอยเป็น cache/UNVERIFIABLE
#   อย่างนุ่มนวล (เป็น failure path เดิมอยู่แล้ว) → logic ปลายทางไม่เปลี่ยน.
from offline_guard import network_allowed   # re-export (เทส/เครื่องมือเดิมยังเรียก webverify.network_allowed ได้)


def web_request(url, headers=None):
    # ★ OFFLINE-ONLY: ไม่เปิด socket ใด ๆ เว้นแต่ opt-in ชัดเจน (default = ออฟไลน์)
    if not network_allowed():
        return None
    if not web_can_request(): return None
    try:
        scheme = url.split(':', 1)[0].lower()
        if scheme not in WEB_GOV['ALLOWED_SCHEMES']: return None
    except Exception: return None
    if headers is None:
        headers = {'User-Agent': WEB_GOV['USER_AGENT']}
    last_err = None
    for attempt in range(WEB_GOV['MAX_RETRIES'] + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=WEB_GOV['REQUEST_TIMEOUT']) as r:
                body = r.read().decode('utf-8', errors='ignore')
            web_record_success()
            time.sleep(WEB_GOV['RATE_LIMIT_DELAY'])
            return body
        except Exception as e:
            last_err = e
            if attempt < WEB_GOV['MAX_RETRIES']:
                time.sleep(WEB_GOV['RETRY_DELAY'])
    web_record_failure()
    return None


# ----------------------------------------------------------------------

def init_cache_db():
    conn = sqlite3.connect(VERIFY_CFG['CACHE_DB'])
    conn.execute('CREATE TABLE IF NOT EXISTS search_cache (query TEXT PRIMARY KEY, snippet TEXT, source TEXT, trust INTEGER, ts REAL)')
    conn.commit()
    return conn

def get_cached(conn, key):
    cur = conn.execute('SELECT snippet, source, trust, ts FROM search_cache WHERE query=?', (key,))
    row = cur.fetchone()
    if not row: return None
    snippet, source, trust, ts = row
    if (time.time() - ts) / 86400 > VERIFY_CFG['CACHE_TTL_DAYS']: return None
    return {'snippet': snippet, 'source': source, 'trust': trust}

def set_cached(conn, key, snippet, source, trust):
    conn.execute('INSERT OR REPLACE INTO search_cache VALUES (?, ?, ?, ?, ?)',
                 (key, snippet or '', source or '', trust, time.time()))
    conn.commit()

def tier1_verify(name, unit, category=None):
    out = {'tier1_match': None, 'tier1_confidence': 0, 'tier1_conf01': 0.0,
           'tier1_unit_ok': None, 'tier1_unit_suggest': None,
           'tier1_state': 'UNVERIFIABLE', 'tier1_method': 'none',
           'tier1_tier': 'LOW',
           'ocr_suspected': False, 'ocr_score': 0.0,
           'name_normalized': name, 'formal_score': 0.0, 'formal_ok': True}
    cat = category or predict_category(name)

    is_ocr, ocr_score = detect_ocr_input(name)
    out['ocr_suspected'] = is_ocr; out['ocr_score'] = ocr_score
    norm_name = normalize_ocr(name) if is_ocr else name
    out['name_normalized'] = norm_name

    f_score = formal_language_score(name)
    out['formal_score'] = f_score
    out['formal_ok'] = f_score >= FORMAL_CFG['MIN_FORMAL_SCORE']

    if norm_name in CONSTRUCTION_DICT:
        out.update({'tier1_match': norm_name, 'tier1_confidence': 100,
                   'tier1_conf01': 1.0, 'tier1_method': 'exact_dict'})
    else:
        best, score = find_similar_in_thai_dict(norm_name, threshold=70)
        if best:
            out.update({'tier1_match': best, 'tier1_confidence': score,
                       'tier1_conf01': to_conf01(score), 'tier1_method': 'fuzzy'})
        # [P2-NOTE] ใช้ CONF_TIERS['HIGH_MIN'] เป็น "เกณฑ์ตัดสิน logic" (ไม่ใช่แค่ป้ายแสดงผล):
        #   conf ต่ำกว่า HIGH_MIN → จึงเรียก pythainlp spell-check (แพง) มาช่วยอีกชั้น
        #   ดู note ใน config.py CONF_TIERS — ค่านี้กระทบทั้งพฤติกรรมตรวจและหน้าตารายงาน
        if PYTHAINLP_AVAILABLE and out['tier1_conf01'] < CONF_TIERS['HIGH_MIN']:
            try:
                suggestions = pythainlp_spell_check(norm_name)
                if suggestions and not out['tier1_match']:
                    orig, corrected = suggestions[0]
                    fix = norm_name.replace(orig, corrected)
                    out.update({'tier1_match': fix, 'tier1_confidence': 75,
                               'tier1_conf01': 0.75, 'tier1_method': 'pythainlp'})
            except Exception as _e:
                print(f'⚠️ [tier1 pythainlp] {_e}')  # v5.9 FIX-1

    tier = confidence_tier(out['tier1_conf01'])
    out['tier1_tier'] = tier
    out['tier1_state'] = ('VERIFIED' if tier == 'HIGH'
                          else 'NEEDS_REVIEW' if tier == 'MEDIUM'
                          else 'UNVERIFIABLE')

    if cat in PRODUCT_CATEGORIES:
        expected = PRODUCT_CATEGORIES[cat]['units']
        if unit:
            if any(u in unit for u in expected): out['tier1_unit_ok'] = True
            else:
                out['tier1_unit_ok'] = False
                out['tier1_unit_suggest'] = '/'.join(expected[:3])
    return out


def tier2_duckduckgo(query, conn):
    cached = get_cached(conn, f'ddg:{query}')
    if cached and cached['snippet']: return cached
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    html = web_request(url)
    if html is None: return None
    urls = re.findall(r'<a[^>]*class="result__url"[^>]*>([^<]+)</a>', html)
    urls = [u.strip() for u in urls]
    snippets = re.findall(r'<a[^>]*class="result__a"[^>]*>([^<]+)</a>', html)
    best = None
    for i, u in enumerate(urls[:WEB_GOV['MAX_URLS_PER_QUERY']]):
        for domain, trust in SOURCE_TRUST.items():
            if domain in u:
                snippet = snippets[i] if i < len(snippets) else ''
                if not best or trust > best['trust']:
                    best = {'snippet': snippet[:200], 'source': u, 'trust': trust}
    if best: set_cached(conn, f'ddg:{query}', best['snippet'], best['source'], best['trust'])
    else: set_cached(conn, f'ddg:{query}', '', '', 0)
    return best


def tier2_serpapi(query, conn):
    if not VERIFY_CFG.get('SERPAPI_KEY'): return None
    cached = get_cached(conn, f'serp:{query}')
    if cached and cached['snippet']: return cached
    url = (f"https://serpapi.com/search?q={urllib.parse.quote(query)}"
           f"&hl=th&gl=th&api_key={VERIFY_CFG['SERPAPI_KEY']}")
    body = web_request(url)
    if body is None: return None
    try:
        data = json.loads(body)
        for r in data.get('organic_results', [])[:WEB_GOV['MAX_URLS_PER_QUERY']]:
            link = r.get('link', ''); snip = r.get('snippet', '')
            for domain, trust in SOURCE_TRUST.items():
                if domain in link:
                    set_cached(conn, f'serp:{query}', snip, link, trust)
                    return {'snippet': snip[:200], 'source': link, 'trust': trust}
    except Exception as _e:
        print(f'⚠️ [tier2_serpapi] parse ผลไม่ได้: {_e}')  # v5.9 FIX-1
    return None


def tier2_verify(name, unit, conn):
    if VERIFY_CFG['TIER1_CHECK_ONLY']:
        return {'tier2_state':'SKIPPED','tier2_source':None,'tier2_snippet':None,
                'tier2_trust':0,'tier2_conf01':0.0,'tier2_tier':'LOW'}
    query = f'"{name}" หน่วย'
    result = tier2_duckduckgo(query, conn) or tier2_serpapi(query, conn)
    if not result or not result.get('snippet'):
        return {'tier2_state':'UNVERIFIABLE','tier2_source':None,'tier2_snippet':None,
                'tier2_trust':0,'tier2_conf01':0.0,'tier2_tier':'LOW'}
    conf01 = to_conf01(result['trust'])
    tier = confidence_tier(conf01)
    state = ('VERIFIED' if tier == 'HIGH'
             else 'NEEDS_REVIEW' if tier == 'MEDIUM'
             else 'UNVERIFIABLE')
    return {'tier2_state':state,'tier2_source':result['source'],
            'tier2_snippet':result['snippet'],'tier2_trust':result['trust'],
            'tier2_conf01':conf01,'tier2_tier':tier}


def verify_product(name, unit, category=None, conn=None):
    t1 = tier1_verify(name, unit, category)
    t2 = {'tier2_state':None,'tier2_source':None,'tier2_snippet':None,
          'tier2_trust':0,'tier2_conf01':0.0,'tier2_tier':'LOW'}
    if t1['tier1_state'] in ('UNVERIFIABLE','NEEDS_REVIEW') and conn is not None:
        t2 = tier2_verify(name, unit, conn)

    if t1['tier1_state'] == 'VERIFIED':
        final = 'VERIFIED'
    elif t2['tier2_state'] == 'VERIFIED':
        final = 'CONFLICTED' if (t1.get('tier1_match') and t1['tier1_match'] != name) else 'VERIFIED'
    elif t2['tier2_state'] == 'NEEDS_REVIEW' or t1['tier1_state'] == 'NEEDS_REVIEW':
        final = 'NEEDS_REVIEW'
    else:
        final = 'UNVERIFIABLE'

    risk = ('HIGH' if final in ('UNVERIFIABLE','CONFLICTED')
            else 'MEDIUM' if final == 'NEEDS_REVIEW' else 'LOW')

    evidence_parts = []
    if t1.get('tier1_match') and t1['tier1_match'] != name:
        evidence_parts.append(f'Tier1 พบคำใกล้เคียง "{t1["tier1_match"]}" ({t1["tier1_confidence"]:.0f}%)')
    if t2.get('tier2_source'):
        domain = re.sub(r'^https?://(www\.)?','',t2['tier2_source']).split('/')[0]
        evidence_parts.append(f'Tier2 อ้างอิง {domain} (trust {t2["tier2_trust"]})')
    if t1.get('ocr_suspected'):
        evidence_parts.append('สงสัย OCR error')
    if not t1.get('formal_ok'):
        evidence_parts.append(f'ภาษาไม่ทางการ (score {t1["formal_score"]:.2f})')
    evidence = '; '.join(evidence_parts) if evidence_parts else 'ไม่พบข้อมูลอ้างอิง'

    action = ''
    if final == 'UNVERIFIABLE':
        action = 'ตรวจสอบกับเอกสารต้นทาง / เพิ่ม Master Dict'
    elif final == 'CONFLICTED':
        action = 'ตัดสินใจระหว่างผลออฟไลน์กับออนไลน์'
    elif final == 'NEEDS_REVIEW':
        action = f'ทบทวนชื่อ/หน่วย (conf ระดับ {t1["tier1_tier"]})'
    elif t1.get('tier1_unit_ok') == False:
        action = f'หน่วยควรเป็น {t1.get("tier1_unit_suggest","-")}'

    explanation = gen_explanation(
        subject=final, evidence=evidence, action=action,
        tier=t1.get('tier1_method',''), confidence_tier=t1.get('tier1_tier',''))

    return {'original_name': name, 'original_unit': unit,
            'predicted_category': category or predict_category(name),
            **t1, **t2,
            'final_state': final, 'risk_level': risk,
            'explanation': explanation}


def run_product_verification(all_bills, enable_online=True):
    if not VERIFY_CFG['ENABLE']: return []
    # ★ OFFLINE-ONLY: live-fetch จะเปิดได้ก็ต่อเมื่อ "ขอเปิด" และ env อนุญาตเท่านั้น
    online = bool(enable_online) and network_allowed()
    web_state_reset()
    products = {}
    for b in all_bills:
        for it in b['items']:
            key = (it['name'], it['unit'])
            if key not in products: products[key] = []
            products[key].append((b['file'], b['sheet'], it['seq']))
    print(f'\n🔬 Product Verification: {len(products)} unique items')
    print(f'   Tier 1: offline | Tier 2: {"online (opt-in)" if online else "OFF (ออฟไลน์)"}')
    print(f'   Confidence Tiers: HIGH≥{CONF_TIERS["HIGH_MIN"]} / MID≥{CONF_TIERS["MID_MIN"]} / LOW<{CONF_TIERS["MID_MIN"]}')
    print(f'   Web Gov: max {WEB_GOV["MAX_TOTAL_REQUESTS"]} req, retry {WEB_GOV["MAX_RETRIES"]}x, breaker {WEB_GOV["CIRCUIT_BREAKER_FAILS"]} fails')
    conn = init_cache_db() if online else None
    if not online: VERIFY_CFG['TIER1_CHECK_ONLY'] = True
    results = []
    # [ADR-017 / F9] ห่อ conn ด้วย try/finally — เดิม conn.close() อยู่หลังลูป ถ้า exception หลุด
    #   ก่อนถึงบรรทัดนั้น (เช่นใน tqdm/สร้าง batch) → connection leak. finally ปิดเสมอ.
    try:
        items = list(products.items())
        batches = [items[i:i+VERIFY_CFG['BATCH_SIZE']] for i in range(0, len(items), VERIFY_CFG['BATCH_SIZE'])]
        for bi, batch in enumerate(batches):
            for (name, unit), locations in tqdm(batch, desc=f'Batch {bi+1}/{len(batches)}'):
                try:
                    v = verify_product(name, unit, conn=conn)
                    v['occurrences'] = len(locations)
                    v['locations'] = '; '.join([f"{f}[{s}]#{seq}" for f, s, seq in locations[:3]])
                    if len(locations) > 3: v['locations'] += f' +{len(locations)-3}'
                    results.append(v)
                except Exception as e:
                    results.append({'original_name':name,'original_unit':unit,
                                   'final_state':'ERROR','risk_level':'HIGH',
                                   'explanation':f'เกิดข้อผิดพลาด: {str(e)[:80]}'})
    finally:
        if conn: conn.close()
    print(f'\n✅ VERIFIED: {sum(1 for r in results if r["final_state"]=="VERIFIED")}')
    print(f'⚠️  NEEDS_REVIEW: {sum(1 for r in results if r["final_state"]=="NEEDS_REVIEW")}')
    print(f'❌ UNVERIFIABLE: {sum(1 for r in results if r["final_state"]=="UNVERIFIABLE")}')
    print(f'⚡ CONFLICTED: {sum(1 for r in results if r["final_state"]=="CONFLICTED")}')
    print(f'🌐 Web: {_WEB_STATE["total_requests"]} req, {_WEB_STATE["total_failures"]} fail'
          + (', ⛔ CIRCUIT OPEN' if _WEB_STATE['circuit_open'] else ''))
    return results
