# -*- coding: utf-8 -*-
"""test_match_guard.py — กัน fuzzy ผูกข้ามบริษัท (MATCH-GUARD ใน run_rules)

เหตุการณ์จริง (มิ.ย. 2026, corpus 106 ไฟล์ + master จริง 1 บริษัท): partial_ratio ให้คะแนน
75-80 จากคำอุตสาหกรรมร่วม ("...คอนสตรัคชั่น จำกัด") → บิลของ 4 บริษัทคนละนิติบุคคล
(เลขภาษีต่างชัด) ถูกผูกกับ master ฉีอัน แล้วโดน CMP001/TAX003("อันตราย")/ADDR001
= false positive 81 บิล ที่จะหลุดเข้ารายงานลูกค้า.

Guard: เลขภาษีบิลครบ 13 หลัก + ต่างจาก master + ชื่อแค่คล้าย (score<90) → ไม่ผูก
ชื่อเหมือนมาก (≥90/exact) + เลขต่าง → คงผูก เพื่อให้ TAX003 จับเคสสวมเลข (คลาสฉีหยวน).

self-contained: บิลสังเคราะห์ ไม่พึ่ง /mnt/project
"""
import sys

PASS = True


def _check(label, cond):
    global PASS
    print(f"  {'✅' if cond else '❌'} {label}")
    if not cond:
        PASS = False


def _bill(company, tax):
    return {
        'company': company, 'company_raw': company, 'tax_id': tax,
        'sheet': '1', 'file': 'GUARD_69_01.xls', 'items': [],
        'subtotal': None, 'vat': None, 'total': None, 'issues': [],
        'iv_number': 'IV6901000001', 'iv_number_raw': 'IV6901000001',
        'iv_date': None, 'iv_date_str': '', 'branch_no': '00000',
        'address': 'เลขที่ 99 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110', 'amount_source': {},
    }


def main():
    import rules_engine as RE

    MASTER = {
        'ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์)': {
            'name': 'บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์) จำกัด',
            'name_alt': 'บริษัทฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์) จำกัด',
            'tax_id': '0105566206726', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        }
    }
    NOT_FOUND = '(ไม่พบใน master)'

    def run(b):
        RE.run_rules(b, MASTER, {}, unit_index=None, all_bills_ref=[b])
        codes = {i['code'] for i in b['issues']}
        return b, codes

    # 1) คนละนิติบุคคล ชื่อคล้ายจากคำอุตสาหกรรม (FP คลาสจริงจาก corpus) → ต้องไม่ผูก
    b, codes = run(_bill('บริษัท ที บีท คอนสตรัคชั่น จำกัด', '0105557042091'))
    _check("ชื่อคล้าย(<90)+เลขภาษีต่าง → ไม่ผูก master", b['master_key'] == NOT_FOUND)
    _check("  → ไม่มี CMP001/TAX003/ADDR001 (FP หาย)",
           not ({'CMP001', 'TAX003', 'ADDR001'} & codes))

    # 2) ชื่อเป๊ะ master แต่เลขภาษีต่าง (สวมเลข/พิมพ์เลขผิด) → ต้อง "คงผูก" + TAX003 จับ
    b, codes = run(_bill('บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์) จำกัด', '0105557042091'))
    _check("ชื่อเป๊ะ+เลขต่าง → คงผูก (จับสวมเลข)", b['master_key'] != NOT_FOUND)
    _check("  → TAX003 ยิง", 'TAX003' in codes)

    # 3) ชื่อเป๊ะ + เลขตรง → ผูกปกติ ไม่มี master-mismatch
    b, codes = run(_bill('บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์) จำกัด', '0105566206726'))
    _check("ชื่อเป๊ะ+เลขตรง → ผูก + สะอาด",
           b['master_key'] != NOT_FOUND and not ({'CMP001', 'TAX003'} & codes))

    # 4) ชื่อใกล้มาก (typo เล็ก ≥90 — คลาสฉีหยวน) + เลขต่าง → คงผูก + TAX003
    b, codes = run(_bill('บริษัท ฉี อัน คอนสตรัคชัน กรุ๊ป(ไทยแลนด์) จำกัด', '0105557042091'))
    _check("ชื่อใกล้มาก(≥90)+เลขต่าง → คงผูก + TAX003 (คลาสฉีหยวน)",
           b['master_key'] != NOT_FOUND and 'TAX003' in codes)

    # 5) เลขภาษีบิลอ่านไม่ได้ → conservative: พฤติกรรมเดิม (fuzzy ≥75 ยังผูกได้)
    b, codes = run(_bill('บริษัท ที บีท คอนสตรัคชั่น จำกัด', ''))
    _check("เลขบิลอ่านไม่ได้ → คงพฤติกรรมเดิม (ผูกตาม fuzzy)", b['master_key'] != NOT_FOUND)

    # 6) master ว่าง → ไม่ผูก (พฤติกรรมเดิม)
    b2 = _bill('บริษัท ที บีท คอนสตรัคชั่น จำกัด', '0105557042091')
    RE.run_rules(b2, {}, {}, unit_index=None, all_bills_ref=[b2])
    _check("master ว่าง → ไม่ผูก", b2['master_key'] == NOT_FOUND)

    print()
    if PASS:
        print("RESULT: ✅ MATCH-GUARD — FP ข้ามบริษัทหาย / การจับสวมเลข (≥90) คงเดิม")
        return 0
    print("RESULT: ❌ MATCH-GUARD มีเคสไม่ผ่าน")
    return 1


if __name__ == "__main__":
    sys.exit(main())
