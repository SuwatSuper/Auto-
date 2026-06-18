# -*- coding: utf-8 -*-
"""diagnostics.py — STRUCTURED SYSTEM-ISSUE LOGGER + cache trim (observability layer)

ย้ายมาจาก monolith แบบ "คัดลอกเป๊ะทุกตัวอักษร" — logic เดิม 100%.
เป้าหมาย (TARGET 2): แทน "except: pass / print เฉย ๆ" ในชั้น parse/rules ด้วย record
ที่ตามรอยได้ โดยไม่แตะ schema ของ bill/รายงานเดิมเลย.

⚠️ state ที่ใช้ร่วม (_SYSTEM_ISSUES / _SYSTEM_ISSUE_SEEN) อยู่ใน state.py
   เพื่อให้ main + reporting + diagnostics เห็น "object เดียวกัน" (อ้าง state.X เสมอ)
   — reset ใช้ .clear() ไม่ใช่ rebind เพื่อคง identity ของ reference ทุกที่.

ตำแหน่งใน DAG:  config + state  →  [diagnostics]  →  parser / rules / reporting / main
"""
import json
from datetime import datetime

import state
from config import CFG, SEVERITY_ICON  # [F3] explicit (เดิม import *)


def system_issues_reset():
    """เรียกตอนเริ่ม main() — เคลียร์ audit trail ของรอบก่อน กัน state bleed ข้ามรอบ"""
    state._SYSTEM_ISSUES.clear()
    state._SYSTEM_ISSUE_SEEN.clear()
    state._SYSTEM_ISSUE_KEYS.clear()   # [ADR-PMERGE] คง 1:1 กับ _SYSTEM_ISSUES (reset พร้อมกันเสมอ)

def log_system_issue(code='SYS001', name='Parsing Failure', detail='',
                     severity='ERROR', category='SYSTEM',
                     file=None, sheet=None, item=None, exc=None, echo=True):
    """บันทึก system-level issue แบบมีโครงสร้าง (audit-traceable).

    คืนค่า dict ในรูปแบบมาตรฐานเดียวกับ issue ของบิล:
        {"code","severity","category","name","detail"}  (+ context keys)
    ออกแบบให้ "ปลอดภัยเสมอ": ไม่ throw, ไม่ทำให้ caller ล้ม
    """
    try:
        ctx = []
        if file:  ctx.append(f'ไฟล์={file}')
        if sheet: ctx.append(f'ชีต={sheet}')
        if item is not None: ctx.append(f'รายการ={item}')
        if exc is not None:
            ctx.append(f'{type(exc).__name__}: {str(exc)[:160]}')
        full_detail = detail
        if ctx:
            full_detail = (detail + ' | ' if detail else '') + ' '.join(ctx)
        issue = {
            'code': code, 'severity': severity, 'category': category,
            'name': name, 'detail': full_detail,
        }
        if file is not None:  issue['file'] = file
        if sheet is not None: issue['sheet'] = sheet
        if item is not None:  issue['item'] = item
        # dedupe: code + file + sheet + ชนิด error (กัน log เดิมซ้ำ ๆ)
        dk = (code, file, sheet, type(exc).__name__ if exc is not None else name)
        if dk in state._SYSTEM_ISSUE_SEEN:
            return issue
        state._SYSTEM_ISSUE_SEEN.add(dk)
        state._SYSTEM_ISSUES.append(issue)
        state._SYSTEM_ISSUE_KEYS.append(dk)   # [ADR-PMERGE] เก็บ key จริง (รวม exc-type) คู่ issue 1:1
        if echo:
            icon = SEVERITY_ICON.get(severity, '⚪')
            print(f'   {icon} [{code}] {name}: {full_detail}')
        return issue
    except Exception:
        # logger ต้องไม่ทำให้งานหลักล้มเด็ดขาด
        return {'code': code, 'severity': severity, 'category': category,
                'name': name, 'detail': str(detail)}

def flush_system_issues_to_disk(path=None):
    """เขียน audit trail ของ parse failure เป็น JSONL ข้าง ๆ รายงาน (sidecar).
    ไม่กระทบไฟล์ Excel/รายงานเดิม — เป็นไฟล์เสริมล้วน ๆ"""
    if not state._SYSTEM_ISSUES:
        return None
    try:
        if path is None:
            path = CFG.get('SYSTEM_ISSUE_LOG', 'audit_system_issues.jsonl')
        stamp = datetime.now().isoformat(timespec='seconds')
        with open(path, 'w', encoding='utf-8') as f:
            for iss in state._SYSTEM_ISSUES:
                rec = dict(iss); rec['logged_at'] = stamp
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        return path
    except Exception as e:
        print(f'   ⚠️ เขียน system-issue log ไม่สำเร็จ: {type(e).__name__}: {e}')
        return None

def _trim_cache(cache, max_size):
    """v6.2 MEMORY: ตัด cache แบบ FIFO เมื่อโตเกินเพดาน — กัน RAM โตไม่จำกัด
    (ตัดแล้ว recompute ได้ → ผลลัพธ์เหมือนเดิม กระทบแค่ความเร็วเล็กน้อย)"""
    try:
        n_remove = len(cache) - max_size
        if n_remove <= 0:
            return
        for k in list(cache.keys())[:n_remove]:
            cache.pop(k, None)
    except Exception:
        pass


def format_sys_summary(issues=None):
    """[A5] สรุป SYS-* 'ท้ายการรัน' ให้ "การข้ามกฎเงียบ" (silent skip) มองเห็นได้เสมอ.

    เมื่อกฎ crash บนบางบิล run_rules route ไป log_system_issue('SYS-<code>') และ "ไม่ใส่" ใน
    bill['issues'] → บิลนั้นข้ามกฎนั้นเงียบจากรายงานหลัก. ฟังก์ชันนี้สรุปจำนวน SYS-* ทั้งหมด
    (รวม rule crash) เป็นบรรทัดท้ายการรัน — อ่าน state อย่างเดียว ไม่เปลี่ยน routing/golden.

    คืนข้อความ (อาจหลายบรรทัด). 0 รายการ → ยืนยันชัดว่า "ไม่มีกฎข้ามเงียบ".
    """
    from collections import Counter
    iss = state._SYSTEM_ISSUES if issues is None else issues
    if not iss:
        return '🩺 สรุป SYS-* ท้ายการรัน: 0 — ไม่มีกฎข้ามเงียบ (ทุกกฎรันครบทุกบิล)'
    # กฎที่ crash ใน run_rules ใช้รหัส 'SYS-<RULECODE>' (มีขีด) ; parse failure ใช้ 'SYS001' ฯลฯ
    rule_skips = [i for i in iss if str(i.get('code', '')).startswith('SYS-')]
    bc = Counter(i.get('code', 'SYS001') for i in iss)
    lines = ['🩺 สรุป SYS-* ท้ายการรัน: %d รายการ (%s)'
             % (len(iss), ', '.join(f'{c}×{n}' for c, n in sorted(bc.items())))]
    if rule_skips:
        skipped_codes = sorted({str(i.get('code', ''))[4:] for i in rule_skips})
        lines.append('   ⚠️ มีกฎข้ามเงียบ (rule crash) %d ครั้ง บนกฎ %s — บิลเหล่านั้น "ไม่ได้ตรวจกฎนั้น" '
                     '(ดู sidecar .jsonl / ชีต System Issues)' % (len(rule_skips), ', '.join(skipped_codes)))
    return '\n'.join(lines)


__all__ = ['system_issues_reset', 'log_system_issue',
           'flush_system_issues_to_disk', 'format_sys_summary', '_trim_cache']
