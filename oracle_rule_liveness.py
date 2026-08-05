# -*- coding: utf-8 -*-
"""oracle_rule_liveness.py — ORACLE §3.2: "รหัสกฎที่ฟ้อง 0 ครั้ง — เพราะข้อมูลสะอาด หรือเพราะกฎพัง"

หลักการ: ยิงบิลที่ "จงใจผิด" ครอบทุกตระกูลข้อบกพร่อง (รวม master + ข้ามบิล) แล้วดูว่ากฎไหน
**ไม่ฟ้องเลยแม้แต่ครั้งเดียว** → กฎนั้นอาจ
  (ก) ต้องการเงื่อนไขที่ generator ยังไม่ครอบ  (ข) เป็นข้อจำกัดโครงสร้าง  (ค) พัง/fail-open

ต่างจาก test_rules_coverage.py: ตัวนั้นพิสูจน์ "ไม่ครัช" — ตัวนี้พิสูจน์ "ยังจับได้จริง"

รัน:  python3 oracle_rule_liveness.py
"""
import datetime as dt
import io
import contextlib
from collections import Counter

import rules_engine as RE

MASTER = {
    "ทดสอบ มาสเตอร์": {
        "name": "บริษัท ทดสอบ มาสเตอร์ จำกัด",
        "tax_id": "0105556123456",
        "branch": "สำนักงานใหญ่",
        "branch_no": "00000",
        "address": "1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110",
    },
}

BASE = {
    'file': 'a.xls', 'sheet': '1', 'block_idx': 0,
    'company': 'บริษัท ทดสอบ มาสเตอร์ จำกัด', 'company_raw': 'บริษัท ทดสอบ มาสเตอร์ จำกัด',
    'tax_id': '0105556123456', 'tax_id_raw': '0105556123456',
    'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
    'address': '1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    'address_raw': '1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    'iv_number': 'IV69050001', 'iv_number_raw': 'IV-69050001',
    'iv_date': dt.datetime(2026, 5, 5), 'iv_date_str': '05/05/2026',
    'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
    'amount_source': {'subtotal': 'ocr', 'vat': 'ocr', 'total': 'ocr'},
    'items': [], 'issues': [],
}


def item(seq=1, name='ท่อพีวีซี ชั้น 5', qty=2.0, unit='เส้น', price=500.0,
         amount=1000.0, discount=None):
    return {'seq': seq, 'name': name, 'name_raw': name, 'qty': qty, 'unit': unit,
            'price': price, 'amount': amount, 'discount': discount}


def bill(**kw):
    b = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
         for k, v in BASE.items()}
    b['items'] = [item()]
    b['issues'] = []
    b.update(kw)
    return b


# ── ชุดบิลที่ "จงใจผิด" ครอบทุกตระกูล ──────────────────────────────
CASES = {
    # บริษัท / ชื่อ
    'ชื่อต่างจาก master': bill(company='บริษัท คนละชื่อ ไม่เหมือน จำกัด'),
    'ไม่มีคำนำหน้านิติบุคคล': bill(company='ทดสอบ มาสเตอร์'),
    'คำนำหน้าพิมพ์ผิด': bill(company='บริษัท์ ทดสอบ มาสเตอร์ จำกัด'),
    'ชื่อว่าง': bill(company=''),
    'ชื่อมีอักขระซ่อน': bill(company='บริษัท ทดสอบ​ มาสเตอร์ จำกัด',
                              company_raw='บริษัท ทดสอบ​ มาสเตอร์ จำกัด'),
    'ชื่อสั้นผิดปกติ': bill(company='บ'),
    # เลขภาษี
    'เลขภาษีไม่ครบ 13': bill(tax_id='01055561234', tax_id_raw='01055561234'),
    'เลขภาษี checksum ผิด': bill(tax_id='0105556123457', tax_id_raw='0105556123457'),
    'เลขภาษีต่างจาก master': bill(tax_id='0994000123456', tax_id_raw='0994000123456'),
    'เลขภาษีว่าง': bill(tax_id='', tax_id_raw=''),
    'เลขภาษี full-width': bill(tax_id='０１０５５５６１２３４５６',
                                tax_id_raw='０１０５５５６１２３４５６'),
    'เลขภาษีมีตัวอักษร': bill(tax_id='01055561234AB', tax_id_raw='01055561234AB'),
    # ที่อยู่
    'ที่อยู่ต่างจาก master': bill(address='999 ถนนอื่น แขวงอื่น เขตอื่น เชียงใหม่ 50000'),
    'ที่อยู่ว่าง': bill(address='', address_raw=''),
    'ไปรษณีย์ไม่ตรงจังหวัด': bill(address='1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย เชียงใหม่ 10110'),
    'จังหวัดปลอม': bill(address='1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย จังหวัดไม่มีจริง 10110'),
    'ไม่มีรหัสไปรษณีย์': bill(address='1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร'),
    'ที่อยู่สั้นมาก': bill(address='1'),
    # สาขา
    'สาขาต่างจาก master': bill(branch='สาขาที่ 7', branch_no='00007'),
    'สาขาว่าง': bill(branch='', branch_no=''),
    'เลขสาขาไม่ใช่ตัวเลข': bill(branch_no='ABCDE'),
    # เลขที่เอกสาร / วันที่
    'เลขเอกสารว่าง': bill(iv_number='', iv_number_raw=''),
    'เลขเอกสารขยะ': bill(iv_number='###', iv_number_raw='###'),
    'เลขเอกสารสั้น': bill(iv_number='1', iv_number_raw='1'),
    'วันที่ปี 1970': bill(iv_date=dt.datetime(1970, 1, 1), iv_date_str='01/01/1970'),
    'วันที่อนาคตไกล': bill(iv_date=dt.datetime(2090, 1, 1), iv_date_str='01/01/2090'),
    'วันที่ พ.ศ. digit swap': bill(iv_date_str='05/05/2658'),
    'วันที่ไม่มีจริง': bill(iv_date_str='31/02/2569'),
    'วันที่ว่าง': bill(iv_date=None, iv_date_str=''),
    # ยอดเงิน / VAT
    'VAT ไม่ใช่ 7%': bill(subtotal=1000.0, vat=50.0, total=1050.0),
    'total ไม่เท่า sub+vat': bill(subtotal=1000.0, vat=70.0, total=9999.0),
    'VAT=0 ทั้งที่มียอด': bill(subtotal=1000.0, vat=0.0, total=1000.0),
    'ยอดติดลบ': bill(subtotal=-1000.0, vat=-70.0, total=-1070.0),
    'subtotal ไม่เท่าผลรวมรายการ': bill(subtotal=5000.0, vat=350.0, total=5350.0),
    'ยอดว่างทั้งหมด': bill(subtotal=None, vat=None, total=None),
    'ยอดใหญ่ผิดปกติ': bill(subtotal=1e12, vat=7e10, total=1.07e12),
    # รายการ
    'รายการว่าง': bill(items=[]),
    'qty×price≠amount': bill(items=[item(amount=999.0)]),
    'รายการซ้ำทุกค่า': bill(items=[item(seq=1), item(seq=2)],
                              subtotal=2000.0, vat=140.0, total=2140.0),
    'ลำดับข้าม': bill(items=[item(seq=1), item(seq=5, amount=1000.0)],
                       subtotal=2000.0, vat=140.0, total=2140.0),
    'ลำดับซ้ำ': bill(items=[item(seq=1), item(seq=1, name='อื่น', amount=1000.0)],
                      subtotal=2000.0, vat=140.0, total=2140.0),
    'ไม่มีหน่วย': bill(items=[item(unit='')]),
    'หน่วยแปลก': bill(items=[item(unit='ZZZ')]),
    'ชื่อสินค้าว่าง': bill(items=[item(name='')]),
    'ชื่อสินค้าสั้น': bill(items=[item(name='x')]),
    'ชื่อสินค้าพิมพ์ผิด': bill(items=[item(name='ท่อพีวีซี ชั้ล 5 ฟีา')]),
    'ชื่อสินค้ามีอักขระซ่อน': bill(items=[item(name='ท่อ​พีวีซี')]),
    'qty=0 amount≠0': bill(items=[item(qty=0.0)]),
    'price=0 amount≠0': bill(items=[item(price=0.0)]),
    'amount=0 qty×price≠0': bill(items=[item(amount=0.0)]),
    'qty กลมใหญ่': bill(items=[item(qty=999999.0, amount=499999500.0)],
                         subtotal=499999500.0, vat=34999965.0, total=534999465.0),
    'ราคา outlier': bill(items=[item(seq=i, price=(500.0 if i < 5 else 900000.0),
                                     amount=(1000.0 if i < 5 else 1800000.0))
                                for i in range(1, 7)]),
    'ส่วนลดไม่ลงตัว': bill(items=[item(amount=700.0, discount=0.10)]),
}

# บิลข้ามใบ (cross-bill) — DOC003 / TAX008 / TAX009 / IV ซ้ำ
XB = [
    bill(file='a.xls', sheet='1', iv_number='IVDUP', iv_number_raw='IVDUP'),
    bill(file='b.xls', sheet='1', iv_number='IVDUP', iv_number_raw='IVDUP'),
    bill(file='a.xls', sheet='2', company='บริษัท ชื่อหนึ่ง จำกัด'),
    bill(file='a.xls', sheet='3', company='บริษัท ชื่อสอง จำกัด'),   # เลขภาษีเดียว ชื่อต่าง
    bill(file='a.xls', sheet='4', tax_id='0105556999999',
         tax_id_raw='0105556999999'),                                # ชื่อเดียว เลขต่าง
]

fire = Counter()
enabled = [c for c, r in RE.RULES.items() if r.get('enabled')]


def run_all(bills, master):
    for b in bills:
        with contextlib.redirect_stdout(io.StringIO()):
            RE.run_rules(b, master, {'month': 5, 'month_end': dt.datetime(2026, 5, 31)},
                         all_bills_ref=bills)
        for i in b.get('issues') or []:
            if isinstance(i, dict) and i.get('code'):
                fire[i['code']] += 1


# รันทั้งแบบ "มี master" และ "ไม่มี master" (ครอบทั้งสองโหมด)
for master in (MASTER, {}):
    for name, b in CASES.items():
        run_all([b], master)
    run_all([dict(x, issues=[]) for x in XB], master)

never = [c for c in enabled if fire[c] == 0]

print("=" * 74)
print("ORACLE RULE LIVENESS — กฎที่ 'ไม่เคยฟ้องเลย' แม้ยิงบิลผิดครบทุกตระกูล")
print("=" * 74)
print(f"กฎที่เปิดใช้ {len(enabled)} · ยิง {len(CASES)} เคส × 2 โหมด master + cross-bill {len(XB)} ใบ")
print(f"\nฟ้องอย่างน้อย 1 ครั้ง : {len(enabled)-len(never)}")
print(f"ไม่เคยฟ้องเลย         : {len(never)}")
if never:
    print("\n── กฎที่เงียบสนิท (ต้องจำแนกทีละตัว: ข้อมูลไม่ถึง / ข้อจำกัดโครงสร้าง / พัง) ──")
    for c in never:
        r = RE.RULES[c]
        print(f"  {c:10s} {str(r.get('name'))[:60]}")
print("\n── อันดับกฎที่ฟ้องบ่อย (sanity) ──")
for c, n in fire.most_common(12):
    print(f"  {c:10s} {n}")
disabled = [c for c, r in RE.RULES.items() if not r.get('enabled')]
print(f"\nกฎที่ปิดไว้ ({len(disabled)}): {', '.join(disabled)}")
