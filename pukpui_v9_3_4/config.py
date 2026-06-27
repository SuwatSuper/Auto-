# -*- coding: utf-8 -*-
"""config.py — static configuration & domain constants (ส่วนต่อจาก config_base).

[F4 split] ซอยจาก config.py เดิม (739 LOC) แบบ "คัดลอกเป๊ะทุกตัวอักษร" — NO logic/values changed.
โครง: config_base (imports + VERSION/CFG/CONF_TIERS/หน่วย/คำผิด/CONSTRUCTION_DICT)
      ← [config.py ไฟล์นี้: address/master/prefix/style constants + audit_today]
ชื่อทั้งหมดจาก config_base ดึงผ่าน `import *`; `__all__` ด้านล่าง (เดิม ไม่เปลี่ยน) คุม public surface
ที่ผู้บริโภคทั้งระบบใช้ผ่าน `from config import *` (รวม underscore: _LOCKED, _PP20_LABELS ฯลฯ).
Mutable runtime state + RULES dispatch table ยังอยู่ใน main module เหมือนเดิม.
"""
from config_base import (   # [F3 de-star] explicit (เดิม `from config_base import *`)
    ANALYTICS_CFG, APP_VERSION, Alignment, BRAND_BLACKLIST,
    Border, CFG, COLORS, CONF_TIERS,
    CONSTRUCTION_DICT, EXPLAIN_CFG, FORMAL_CFG, Font,
    LEAN_REPORT, OCR_CFG, OCR_SUSPICIOUS, PRODUCT_CATEGORIES,
    PYTHAINLP_WHITELIST, PatternFill, SEVERITY_ICON, SEVERITY_ORDER,
    SOURCE_TRUST, SPELLING_PATTERNS, Side, THAI_MONTHS,
    THAI_TYPO_PATTERNS, UNIT_HINT_PATTERNS, UNIT_RULES, VAGUE_KEYWORDS,
    VERIFY_CFG, WEB_GOV, _LOCKED, re,
)

# 🆕 compute_bill_confidence (additive)
#  อ่านบิลที่ parse เสร็จแล้ว → ให้คะแนน ไม่แตะ logic parse
# ============================================================
_ADDR_MANDATORY = {'house_no', 'subdistrict', 'district', 'province'}

# ============================================================
# 🆕 v5.8p PATCH — Safe Tax ID extraction (additive)
#  กันที่อยู่ที่มีตัวเลขเยอะ ถูกอ่านเป็นเลขภาษีผิด
# ============================================================
_TAXID_KW = ['เลขประจำตัวผู้เสียภาษี','เลขประจําตัวผู้เสียภาษี','ภาษีอากร',
             'tax id','taxid','เลขผู้เสียภาษี',
             # v9.3.3 [FIX-TAX-LABEL]: ฟอร์ม "เลขที่ประจำตัว..." (มี 'ที่') ของผู้ขายบางราย (เช่น HSH)
             #   path A ใน _extract_taxid_safe เป็น grouping-agnostic (ตัด non-digit แล้วเช็ค 13 หลัก)
             #   จึงรองรับเลขภาษีจัดกลุ่มผิดแบบ (เช่น 1-5-4-2-1) ได้ทันทีเมื่อ label ตรง
             'เลขที่ประจำตัวผู้เสียภาษี','เลขที่ประจําตัวผู้เสียภาษี']

# ============================================================
# 🆕 v5.8n PATCH — Label-based amount fallback (additive)
#  ทำงานเฉพาะเมื่อ logic 0.07 เดิมหา subtotal/vat/total ไม่เจอ
#  ไม่ลบ regex เดิม / ไม่แตะ schema / ไม่เพิ่ม dependency
# ============================================================
_LBL_SUBTOTAL = ['ยอดรวมก่อนภาษี','รวมก่อนภาษี','ยอดก่อนภาษี','รวมเป็นเงิน',
                 'รวมเงิน','รวมราคา','มูลค่าสินค้า','ราคาสินค้า','sub total','subtotal']

_LBL_VAT = ['ภาษีมูลค่าเพิ่ม','ภาษีมูลค่า','vat','ภ.พ.']

_LBL_TOTAL = ['จำนวนเงินรวมทั้งสิ้น','จำนวนเงินทั้งสิ้น','รวมเงินทั้งสิ้น','รวมทั้งสิ้น',
              'ยอดรวมสุทธิ','ยอดสุทธิ','ยอดชำระ','grand total','total amount','net total']

_MAX_TEXT_NUM_RECOVERIES = 20000

_TAX_CONTEXT_KEYWORDS = (
    'ผู้เสียภาษี', 'เลขประจำตัวผู้เสีย', 'เลขประจำตัวผู้',
    'ภาษีอากร',
    'tax id', 'tax no', 'tax number', 'taxid', 'taxno', 'tin',
)

_ADDRESS_HINT_KEYWORDS = (
    'อาคาร', 'ชั้นที่', 'ห้องเลขที่',
    'ถนน', 'แขวง', 'เขต', 'ตำบล', 'อำเภอ', 'จังหวัด',
    'หมู่ที่', 'ซอย', 'ตรอก',
)

# ============================================================
# 🏢 MASTER DATA
# ============================================================
# === v5.8q PATCH 7: ล้างที่อยู่ที่ก๊อปจากเว็บ ภ.พ.20 (ตัด label เปล่า) ===
_PP20_LABELS = ['อาคาร','ห้องเลขที่','ชั้นที่','หมู่บ้าน','เลขที่','หมู่ที่',
                'ตรอก/ซอย','ตรอก','ซอย','ถนน','ตำบล','แขวง','อำเภอ','เขต',
                'จังหวัด','รหัสไปรษณีย์']

# === v5.8q PATCH 10: แยก Master Data แบบ Section-based (ทนกว่าเดิม) ===
# คำที่บอกว่า "เริ่มส่วนที่อยู่แล้ว" — ทุกอย่างก่อนหน้านี้ = ส่วนบริษัท
_ADDR_START_KW = ['เลขที่','หมู่ที่','อาคาร','ห้องเลขที่','ชั้นที่','หมู่บ้าน',
                  'ตรอก/ซอย','ตรอก','ซอย','ถนน','ตำบล','แขวง','อำเภอ','เขต','จังหวัด']

# prefix นิติบุคคลที่ถูกต้องตามกฎหมายไทย — แยกเป็น global constant
COMPANY_PREFIXES: tuple = (
    'บริษัท',
    'ห้างหุ้นส่วนจำกัด',
    'ห้างหุ้นส่วนสามัญ',
    'บจก.', 'บจก',
    'บมจ.', 'บมจ',
    'หจก.', 'หจก',
    'กิจการร่วมค้า',
    # v8.1: เพิ่มคำนำหน้าองค์กรอื่น
    'ร้าน',
    'มูลนิธิ',
    'สมาคม',
    'องค์กร',
    'สหกรณ์',
    'ฯพณฯ',
    'วิสาหกิจชุมชน',
    'กองทุน',
)

# v8.1: คำนำหน้าที่พิมพ์ผิดบ่อย (typo prefixes)
# หมายเหตุ: ใช้เชิง membership/startswith เท่านั้น → ลำดับ/ตัวซ้ำไม่มีผลต่อผลตรวจ
#   (เดิมมี 'บริษัส' ซ้ำ 2 ครั้ง — ตัดตัวซ้ำออก ผลเหมือนเดิมทุกประการ)
COMPANY_TYPO_PREFIXES: tuple = ('บริษัส', 'บริสัท', 'บริษาท', 'บรืษัท', 'บรัษัท',
                                'บริษ้ท', 'บิรษัท', 'บริัษท', 'บรืษัธ', 'บริษัธ', 'บรษัท')

# pre-compiled regex: ขึ้นต้นด้วย prefix ตัวใดตัวหนึ่ง
# - เรียงจากยาวไปสั้น กัน 'บจก' แย่ง match ก่อน 'บจก.'
# - (?:\s*) รองรับทั้งมีและไม่มีช่องว่างหลัง prefix
# - re.escape กัน '.' ใน 'บจก.' ถูกตีความเป็น regex metachar
_PREFIX_SORTED: list = sorted(COMPANY_PREFIXES, key=len, reverse=True)

_PREFIX_PATTERN: str = r'^(?:' + '|'.join(re.escape(p) for p in _PREFIX_SORTED) + r')\s*'

COMPANY_PREFIX_RE = re.compile(_PREFIX_PATTERN)

# v8.6 [FIX-ITM015]: กลุ่มหน่วยที่ใช้แทนกันได้ (ชุดเดียวกับ ITM005) — ใช้ยุบหน่วยพ้องก่อนเทียบ ITM015
_UNIT_SYNONYM_GROUPS = [
    {'แกลลอน','กระป๋อง','ถัง','ปี๊บ','กล.'},
    {'ลิตร','มล.','ล.','cc'},
    {'กก.','กิโล','กิโลกรัม','ก.ก.','kg'},
    {'แผ่น','ผืน','บาน'},
    {'ม้วน','โรล','roll'},
    {'ชุด','เซ็ต','set','คู่'},
    {'เส้น','ท่อน','อัน'},
    {'ก้อน','ลูก','ตัว'},
    {'ถุง','กระสอบ','แพ็ค','พาเลท','กล่อง','ลัง'},
]

_AMBIG_SHORT_KW = {'สี', 'สาย', 'หิน', 'ปูน', 'อิฐ', 'ไม้', 'กาว', 'ท่อ', 'ทราย'}

_THAI_MARKS = set('่้๊๋ัิีึืุูำ็์ะาๅ')  # สระ/วรรณยุกต์ที่ตามหลังแล้วทำให้กลายเป็นคำอื่น

# [F1/ADR-087] คำบอก "สีล้วน/ผิว" ที่ตามหลัง 'สี' (ขึ้นต้นคำ) แล้วทำให้ 'สี' กลายเป็น
#   "คำขยายบอกสีของสินค้า" ไม่ใช่สินค้า "สีทาบ้าน" → ITM005 ต้องไม่คาดหน่วยแกลลอน.
#   ตั้งใจ "ไม่" ใส่ token 'น้ำ' (เพื่อให้ สีน้ำ/สีน้ำมัน = สีจริง ยัง match) — ใช้ 'น้ำเงิน'/
#   'น้ำตาล' (ยาวกว่า) แทน. ไม่มี token ใดเป็น prefix ของคำ paint-type (สีรองพื้น/สีย้อม/
#   สีอะคริลิค/สีกันสนิม/สีสเปรย์…) → สีจริงไม่หลุด (recall คงเดิม). พิสูจน์ระดับเซลล์ใน ADR-087.
_SI_COLOR_ADJ = (
    'ขาว', 'ดำ', 'แดง', 'เขียว', 'ฟ้า', 'เหลือง', 'น้ำเงิน', 'น้ำตาล', 'เทา',
    'ส้ม', 'ม่วง', 'ชมพู', 'ทอง', 'เงิน', 'ครีม', 'เรียบ', 'อ่อน', 'เข้ม', 'ใส',
    'บรอนซ์', 'เนื้อ', 'รุ้ง', 'ธรรมชาติ', 'อะลูมิเนียม', 'อลูมิเนียม', 'ไอวอรี่', 'เบจ',
)

# threshold สำหรับ ITM012 (สูงกว่า ITM011 เพื่อ suggest เฉพาะที่มั่นใจ)
ITM012_SIM_THRESHOLD = 90   # score ≥ 90 = similar (น่าจะ typo)

ITM012_MIN_WORD_LEN = 4     # คำสั้นกว่านี้ข้าม (กันคำทั่วไป)

# [P0-FIX แดชบอร์ดโชว์ "ตรง" หลอก] FIELD_CODES ต้องครอบคลุม "ทุกรหัสใน RULES" มิฉะนั้น
#   field_status() มองไม่เห็นรหัสที่ขาด → บริษัทที่มี error จริง (เช่น CMP005/DOC003/VAT009)
#   กลับขึ้น "ตรง" สีเขียวในแดชบอร์ดผู้บริหาร. test_field_codes_coverage.py เป็น tripwire กัน drift
#   (ทุกครั้งที่เพิ่มกฎใหม่ใน RULES ต้องมาเพิ่มที่นี่ด้วย ไม่งั้นเทสจะแดง).
FIELD_CODES = [
    ('ชื่อบริษัท', ['CMP001','CMP002','CMP003','CMP004','CMP005','CMP006']),
    ('ที่อยู่', ['ADDR001','ADDR002','ADDR003','ADDR004','ADDR005','ADDR006']),
    ('เลขที่ผู้เสียภาษี', ['TAX001','TAX002','TAX003','TAX004','TAX005','TAX006','TAX007','TAX008','TAX009']),
    ('สาขา/สนญ.', ['BR001','BR002','BR003','BR004']),
    ('เลขที่ IV', ['DOC002','DOC003','IV001','IV002','IV003','IV004','IV005','IV006','IV007']),
    ('วันที่', ['DOC001','DT001','DT002','DT003','DT004','DT005','DT006']),
    ('รายการสินค้า', ['ITM001','ITM002','ITM003','ITM004','ITM005','ITM006','ITM007','ITM008','ITM009','ITM010','ITM011','ITM012','ITM013','ITM014','ITM015','ITM016','ITM017','ITM018','ITM019','ITM020']),
    ('ยอดก่อน VAT', ['VAT001','VAT005','VAT006','VAT009']),
    ('ยอดหลัง VAT', ['VAT002','VAT003','VAT004','VAT007','VAT008','VAT010','VAT011']),
]

# ============================================================
# 💾 EXCEL EXPORT + STYLING
# ============================================================
_STY_HEADER_FILL = PatternFill('solid', fgColor='1E40AF')

_STY_HEADER_FONT = Font(color='FFFFFF', bold=True, size=11)

_STY_HEADER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)

_STY_THIN = Side(style='thin', color='D1D5DB')

_STY_BORDER = Border(left=_STY_THIN, right=_STY_THIN, top=_STY_THIN, bottom=_STY_THIN)

_STY_SEV_FILLS = {'CRITICAL':PatternFill('solid', fgColor='FEE2E2'),
                  'ERROR':PatternFill('solid', fgColor='FED7AA'),
                  'WARNING':PatternFill('solid', fgColor='FEF3C7'),
                  'INFO':PatternFill('solid', fgColor='DBEAFE')}

_STY_ZEBRA = PatternFill('solid', fgColor='F9FAFB')

# ============================================================
# 🆕 v8.5 [FIX-LANE] — แยก "ข้อสรุปที่ยืนยันแล้ว (finding)" ออกจาก
#    "ข้อแนะนำ/ต้องคนตรวจ (review)" ในชั้นรายงาน (ไม่แตะ business logic / ผลตรวจ)
#    เป้าหมาย: ลด False positive ที่ "ตาเห็น" ในชีต Error Report โดยไม่ลบของชิ้นใดเลย
#    หลักการ: re-tier (จัดเลน) ไม่ใช่ suppress (ลบ) → recall เท่าเดิม, traceability ครบ
# ============================================================
# รหัสกฎที่เป็น "คำแนะนำ/ข้อสังเกต" โดยธรรมชาติ (ไม่ใช่ข้อผิดพลาดยืนยัน)
#   ปรับรายการนี้ได้จากผลนับ FP จริง (เฟส 1) — ค่าตั้งต้นจาก audit โค้ด v8.4
REVIEW_CODES: frozenset = frozenset({
    'ITM004',  # คำสะกด pattern (INFO)
    'ITM005',  # หน่วย keyword (INFO / soft)
    'ITM007',  # [FP-FIX] ชื่อสินค้าสั้น เช่น "Jumper" = ชื่อจริง ไม่ใช่ truncate — ให้ตรงกับ issue_consolidator.REVIEW_ONLY ที่มี ITM007 อยู่แล้ว
    'ITM009',  # alias mapping (INFO)
    'ITM012',  # suggestion ชื่อสินค้า (INFO)
    'ITM015',  # [FP-FIX] ชื่อเดียวกันใช้หลายหน่วย (PCS./เส้น, คิว/ตัน) = ผู้ขายใช้ปกติ ไม่ใช่ error คำนวณ → ข้อสังเกต ไม่ใช่ต้องแก้
    'VAT008',  # VAT เป็นศูนย์ (INFO — ปกติในบางกรณี)
    'VAT011',  # [BS-2] ใบมียอดแต่ VAT=0 (ยกเว้นจริง/ลืมคิด?) — ข้อสังเกต ไม่ใช่ must-fix
    'IV001',   # IV prefix (WARNING — ข้อสังเกต)
})

# ============================================================
# 🚀 MAIN
# ============================================================
# ============================================================
# 🎨 CLEAN EXECUTIVE REPORT — โหมดรายงานคลีน (ฝังเพิ่ม)
# ============================================================
# 🎨 CLEAN EXECUTIVE REPORT (Minimal v6.4 — few sheets, full data)
#   โทนถ่านสุภาพ + เส้นทองบางๆ + ใช้สีเฉพาะระดับความรุนแรง (เรียบหรู สมผู้บริหาร)
# ============================================================
CLEAN = {
    # 🎨 v6.4 MINIMAL EXECUTIVE PALETTE — เรียบหรู สุขุม สมผู้บริหาร
    #   เปลี่ยนจากธีมดำ+แดงสด (Tesla) เป็นโทนถ่านสุภาพ + เส้นทองบางๆ (ใช้สีอย่างจำกัด)
    #   หลักการ: chrome เป็นโทนเทา/ถ่าน, ใส่สีเฉพาะ "ระดับความรุนแรง" เท่านั้น
    'INK':      '1F2A37',   # ถ่านสเลตเข้ม (สุภาพกว่าดำสนิท) — หัวตาราง/แถบไตเติล
    'INK2':     '3F4A5A',   # ตัวอักษรเนื้อหา (สเลตอ่อน อ่านสบายตา)
    'RED':      'B42318',   # แดงอิฐสุขุม — เฉพาะ CRITICAL
    'AMBER':    'B54708',   # ส้มเอิร์ธโทน — ERROR
    'GREEN':    '15803D',   # เขียวสุขุม — ปกติ
    'BLUE':     '175CD3',   # น้ำเงินสุขุม — INFO / กราฟ
    'GRAY':     '8A94A6',   # เทาคูล — ซับไตเติล/ข้อความรอง
    'LINE':     'E6E9EE',   # เส้นบางมาก (hairline)
    'BAND':     'F8F9FB',   # แถบสลับสีจางมาก
    'CARD':     'F4F6F9',   # พื้นการ์ด KPI จางๆ
    'WHITE':    'FFFFFF',
    'ACCENT':   'B08D57',   # ทองหม่น — เส้น accent บางๆ จุดเดียว (พรีเมียม ไม่ฉูดฉาด)
    'FONT':     'Tahoma',   # เรนเดอร์ไทยได้ทุกเครื่อง Windows
}

# [P-DAG พาส3b] openpyxl style constants (ย้ายมาจาก main) — ใช้โดย reporting และ main
#   อยู่ที่ config เพราะเป็น "ค่าคงที่สไตล์" ฐานราก; reporting/main รับผ่าน `from config import *` ที่มีอยู่แล้ว
thin = Side(style='thin', color=CLEAN['LINE'])
bottom_only = Border(bottom=thin)

# ============================================================
# CONFIG — ปรับค่าได้ตามต้องการ
# ============================================================
ADDON_CFG = {
    # DUP001 — บิลซ้ำ
    'DUP_AMOUNT_TOLERANCE': 0.01,      # ยอดเท่ากันถือว่าซ้ำ
    'DUP_CHECK_FIELDS': ['tax_id', 'iv_date', 'total'],  # field ที่ใช้เทียบ

    # WHT001 — Withholding Tax
    'WHT_RATE': 0.03,                  # อัตรา หัก ณ ที่จ่าย 3%
    'WHT_THRESHOLD': 1000,             # ยอดขั้นต่ำที่ต้องหัก (บาท)
    'WHT_SERVICE_KEYWORDS': [          # คำที่บ่งบอกว่าเป็น "ค่าบริการ"
        'ค่าบริการ', 'ค่าจ้าง', 'ค่าแรง', 'ค่าออกแบบ', 'ค่าที่ปรึกษา',
        'ค่าซ่อม', 'ค่าติดตั้ง', 'ค่าขนส่ง', 'ค่าเช่า', 'ค่าทำ',
        'service', 'consulting', 'installation', 'rental',
    ],

    # RND001 — Round Number
    'RND_MIN_AMOUNT': 1000,            # ตรวจเฉพาะยอด ≥ 1000
    'RND_SUSPICIOUS_ENDINGS': [        # ลงท้ายแบบที่น่าสงสัย
        '000.00', '500.00', '0000.00',
    ],
    'RND_MAX_PERCENT': 0.30,           # ถ้า bills > 30% เป็น round = ผิดปกติ

    # PER001 — Period Coverage
    'PER_EXPECTED_DAYS_PER_MONTH': 20, # ขั้นต่ำที่คาดว่ามีบิลต่อเดือน

    # BNF001 — Benford's Law
    'BNF_MIN_SAMPLES': 30,             # ต้องมีตัวอย่าง ≥ 30 ถึงจะวิเคราะห์
    'BNF_CHI_SQUARE_THRESHOLD': 15.5,  # p<0.05 ที่ df=8 ≈ 15.5
    'BNF_EXPECTED': {                  # Benford expected distribution
        1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097, 5: 0.079,
        6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
    },
}


# ============================================================
# 🕒 AUDIT REFERENCE DATE — นาฬิกาที่ "ฉีดเข้าได้" (injectable clock)
#   ปัญหาเดิม (วิกฤต-Reproducibility): กฎ r_dt002 (future date) / r_dt003 (year sanity)
#   เทียบกับ datetime.now() ตรง ๆ → ผลตรวจ "ขึ้นกับวันที่รัน" → golden hash อาจขยับเงียบ
#   เมื่อเวลาเปลี่ยน (เช่น บิลปลายปีเปลี่ยนจาก future→past ข้ามปี).
#
#   วิธีแก้: ทุกกฎที่ต้องรู้ "วันนี้" เรียก audit_today() แทน datetime.now()
#     • ปกติ (production): คืนวันนี้ตามเวลาไทย (UTC+7) — พฤติกรรมเดิมทุกประการ
#     • ถ้าตั้ง env PUOPUY_AUDIT_DATE=YYYY-MM-DD: ใช้ค่านั้น → ผลตรวจ "นิ่งตามเวลา"
#       (ใช้ทำ golden master/regression/CI ให้ reproduce ได้ไม่ว่ารันวันไหน)
# ============================================================
import os as _os
from datetime import datetime as _dt, timezone as _tz, timedelta as _td


def audit_today():
    """วันที่อ้างอิงของงานตรวจ (datetime.date).

    default = วันนี้เวลาไทย (UTC+7). override ได้ด้วย env PUOPUY_AUDIT_DATE=YYYY-MM-DD
    เพื่อให้ผลตรวจ reproducible (กัน golden hash ขยับตามเวลา).
    """
    pinned = (_os.environ.get('PUOPUY_AUDIT_DATE', '') or '').strip()
    if pinned:
        try:
            return _dt.strptime(pinned, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass   # รูปแบบผิด → ตกไปใช้เวลาจริง (ปลอดภัย ไม่ crash)
    try:
        return (_dt.now(_tz.utc) + _td(hours=7)).date()
    except Exception:
        return _dt.now().date()


__all__ = [
    # [P-DAG พาส3b] openpyxl style constants (ย้ายมาจาก main)
    'APP_VERSION',
    'thin', 'bottom_only',
    'audit_today',
    'ADDON_CFG', 'ANALYTICS_CFG', 'BRAND_BLACKLIST', 'CFG',
    'CLEAN', 'COLORS', 'COMPANY_PREFIXES', 'COMPANY_PREFIX_RE',
    'COMPANY_TYPO_PREFIXES', 'CONF_TIERS', 'CONSTRUCTION_DICT', 'EXPLAIN_CFG',
    'FIELD_CODES', 'FORMAL_CFG', 'ITM012_MIN_WORD_LEN', 'ITM012_SIM_THRESHOLD',
    'LEAN_REPORT', 'OCR_CFG', 'OCR_SUSPICIOUS', 'PRODUCT_CATEGORIES',
    'PYTHAINLP_WHITELIST', 'REVIEW_CODES', 'SEVERITY_ICON', 'SEVERITY_ORDER',
    'SOURCE_TRUST', 'SPELLING_PATTERNS', 'THAI_MONTHS', 'THAI_TYPO_PATTERNS',
    'UNIT_HINT_PATTERNS', 'UNIT_RULES', 'VAGUE_KEYWORDS', 'VERIFY_CFG',
    'WEB_GOV', '_ADDRESS_HINT_KEYWORDS', '_ADDR_MANDATORY', '_ADDR_START_KW',
    '_AMBIG_SHORT_KW', '_LBL_SUBTOTAL', '_LBL_TOTAL', '_LBL_VAT',
    '_LOCKED', '_MAX_TEXT_NUM_RECOVERIES', '_PP20_LABELS', '_PREFIX_PATTERN',
    '_PREFIX_SORTED', '_STY_BORDER', '_STY_HEADER_ALIGN', '_STY_HEADER_FILL',
    '_STY_HEADER_FONT', '_STY_SEV_FILLS', '_STY_THIN', '_STY_ZEBRA',
    '_TAXID_KW', '_TAX_CONTEXT_KEYWORDS', '_THAI_MARKS', '_UNIT_SYNONYM_GROUPS',
]
