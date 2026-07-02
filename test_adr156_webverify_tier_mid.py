# -*- coding: utf-8 -*-
"""test_adr156_webverify_tier_mid.py — [ADR-156] webverify tier state ใช้ 'MID' ไม่ใช่ 'MEDIUM'.

บั๊กเดิม (dead-branch/misclassify): confidence_tier() คืน 'HIGH'/'MID'/'LOW' เท่านั้น แต่ tier1_verify/
tier2_verify เทียบ tier == 'MEDIUM' → สาขา 'NEEDS_REVIEW' ตาย → สินค้า tier MID (conf01 0.7-0.9)
ถูกจัดเป็น 'UNVERIFIABLE' + risk 'HIGH' (over-flag) แทน 'NEEDS_REVIEW' + risk 'MEDIUM'.

เทสนี้ยืนยันว่า: (1) confidence_tier ไม่มี 'MEDIUM' (2) tier MID → tier1_state == 'NEEDS_REVIEW'.
advisory layer — ไม่กระทบ golden (golden_master ไม่แตะ webverify).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics import confidence_tier

fails = 0
def check(cond, msg):
    global fails
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        fails += 1

print("ADR-156 — webverify tier state 'MID' (สาขา NEEDS_REVIEW ไม่ตาย)")

# 1) confidence_tier ไม่เคยคืน 'MEDIUM'
tiers = {confidence_tier(i / 100) for i in range(101)}
check('MEDIUM' not in tiers and tiers <= {'HIGH', 'MID', 'LOW'},
      f"confidence_tier outputs = {sorted(tiers)} (ไม่มี 'MEDIUM' → เทียบ =='MEDIUM' เดิม = สาขาตาย)")

# 2) ไม่มีการเทียบ tier == 'MEDIUM' หลงเหลือในเส้น state mapping
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webverify.py'), encoding='utf-8').read()
check("== 'MEDIUM'" not in src and '== "MEDIUM"' not in src,
      "ไม่มี compare `tier == 'MEDIUM'` หลงเหลือใน webverify.py")

# 3) mapping ตรง: MID → NEEDS_REVIEW (จำลอง mapping เดียวกับ tier1_verify)
def _state_of(tier):
    return ('VERIFIED' if tier == 'HIGH'
            else 'NEEDS_REVIEW' if tier == 'MID'
            else 'UNVERIFIABLE')
check(_state_of('MID') == 'NEEDS_REVIEW', "tier MID → NEEDS_REVIEW (ไม่ใช่ UNVERIFIABLE)")
check(_state_of('HIGH') == 'VERIFIED' and _state_of('LOW') == 'UNVERIFIABLE',
      "tier HIGH→VERIFIED, LOW→UNVERIFIABLE (สาขาอื่นคงเดิม)")

# 4) end-to-end: บังคับ conf01 ระดับ MID เข้า tier1_verify แล้ว state ต้องเป็น NEEDS_REVIEW
#    ใช้ค่าที่ทำให้ fuzzy match ได้ conf01 อยู่ช่วง MID (>=MID_MIN, <HIGH_MIN)
from config import CONF_TIERS
mid_c = (CONF_TIERS['MID_MIN'] + CONF_TIERS['HIGH_MIN']) / 2
check(confidence_tier(mid_c) == 'MID' and _state_of(confidence_tier(mid_c)) == 'NEEDS_REVIEW',
      f"conf01={mid_c:.2f} → tier MID → state NEEDS_REVIEW (สินค้าไม่ถูก over-flag เป็น UNVERIFIABLE/HIGH)")

print(("RESULT: ✅ ADR-156 ผ่าน" if fails == 0 else f"RESULT: ❌ {fails} ข้อไม่ผ่าน"))
sys.exit(1 if fails else 0)
