# BUGFIX — Full-System Bug Audit & Crash-Hardening (2026-06-20)

ตรวจบั๊กทั้งระบบ (parser / rules / validators / reporting / core+units+dates / agents-IO) แล้วแก้ครบ
ทุกระดับ. ทุกข้อ **reproduce ด้วยโค้ดจริง** ไม่เชื่อคอมเมนต์/เอกสารเดิม.

## หลักฐาน golden-neutral (สำคัญสุด)

ทดสอบ audit digest บน `tests/real_cases/` (3 ไฟล์ / 15 บิล) ก่อน-หลังแก้ โดยมี **sentinel**
`_money_q('1e30')` ยืนยันว่าสลับโค้ดจริง:

| build | sentinel `_money_q('1e30')` | bills | digest |
|-------|------------------------------|-------|--------|
| as-shipped (baseline) | `CRASH: InvalidOperation` | 15 | `61806af2177d584e619a2998…` |
| หลังแก้ (fixed)        | `None`                     | 15 | `61806af2177d584e619a2998…` |

→ ผลตรวจบนข้อมูลจริง **เท่าเดิมเป๊ะ** (golden ไม่ขยับ). การแก้เปลี่ยนพฤติกรรม **เฉพาะ edge/error
case** (ยอดมหึมา, superscript, อักขระควบคุม, detail=None, วันอธิกสุรทิน ฯลฯ) ที่ไม่เกิดในข้อมูลสะอาด.

เทส standalone: **81/81 ผ่าน** (เดิม 79/81 — แพ็ก GOLDEN มี 2 ตัวแดง: ดู M3).

---

## 🔴 รายแรง — crash ที่ทำข้อมูลหายเงียบ / ไม่ได้รายงาน

### H1 — `_money_q` quantize ระเบิด `InvalidOperation` กับยอดมหึมา → บิลทั้งชีตหายเงียบ
- **ไฟล์:** `puopuy_units.py` (`_money_q`)
- **อาการ:** เซลล์เงินที่มีค่ามหึมา (เกิน Decimal context 28 หลัก เช่น `1e30`, เลข ≥27 หลัก) ทำ
  `Decimal.quantize('0.01')` raise `InvalidOperation`. `is_finite()` ดักไม่ได้ (1E+30 finite).
  call site ที่ไม่ห่อ try: `parser_p2:113` (`_reconcile_amounts`), `parser_p2:129` (item_sum),
  `parser_p0a:126` (merge) → `parse_file` ดักระดับชีต → **SYS001 + บิลทั้งชีตหลุดจาก audit**.
- **พิสูจน์ e2e:** ฉีดยอดมหึมาในเซลล์รายการ → บิลตก 3→2 + SYS001. หลังแก้: 3→3, SYS=0.
- **แก้:** ห่อ quantize ใน `_money_q` คืน `None` (ตรงสัญญา `_D`: แปลงเป็นเงินไม่ได้ → None).
  ข้างเคียง (`parser_p2:120-140`, `parser_p0a:130`) ห่อ InvalidOperation อยู่แล้วตาม ADR-038 —
  จุด H1 เป็นรูที่หลุดไป.

### H2 — `str.isdigit()` รับ superscript/เลขในวงกลม ที่ `int()/float()` ระเบิด → บิลทั้งชีตหาย
- **ไฟล์:** `parser_p0a.py:322`, `parser_p2.py:52/196`
- **อาการ:** `'²'.isdigit()`/`'③'.isdigit()` = True แต่ `int('²')` raise ValueError. superscript
  `² ³` พบบ่อยในงานวัสดุก่อสร้าง (m², m³) → ทำ `_dic_item_rows`/`_pb_extract_items`/sheet-day ครัช.
  พี่น้อง `_dic_int_run` ดักไว้แล้ว แต่ 3 จุดนี้ลืม. fuzz: 58/300 รอบล้มจากเหตุนี้.
- **แก้:** `_is_seq_token()` ใช้ `.isdecimal()` (กัน superscript, เก็บเลขไทย ๕/อารบิก) + รับ `'1.00'`.
  วาง helper ไว้ที่ `parser_p0a` (ตัวเดียว) แล้ว re-export chain ส่งต่อให้ `parser_p2`
  (รักษา identity ตาม `test_parser_chain_integrity`).

### H3 — อักขระควบคุมในเซลล์ → openpyxl `IllegalCharacterError` → ไม่ได้รายงานเลย
- **ไฟล์:** `reporting_p1.py` (`_write_table`)
- **อาการ:** เซลล์ที่มีอักขระควบคุม (เช่น `\x07`) — โดยเฉพาะ `detail`/`name_raw`/ชื่อไฟล์-ชีต
  ที่ไม่ผ่าน `normalize_text` — ทำ `ws.cell()` raise → `build_clean_report` คืน False →
  **ผู้ใช้รันจบทั้งรอบแต่ไม่ได้ไฟล์รายงาน**.
- **แก้:** `_xl_safe()` (ใช้ `openpyxl.cell.cell.ILLEGAL_CHARACTERS_RE`) sanitize ก่อนเขียนเซลล์.

---

## 🟡 กลาง

| # | ไฟล์ | สรุป |
|---|------|------|
| M1 | `puopuy_dates.py:29` | `datetime(2568,2,29).replace(year=2025)` ระเบิด (พ.ศ.อธิก, ค.ศ.ไม่อธิก) → ไฟล์หาย. ห่อ `safe()` → None |
| M2 | `pukpui_modular_funcs.py` + `parser_guards.py` | `get_files_via_drive` ข้าม `ตรวจแล้ว_*`/`company_summary*` (กันตรวจ output ตัวเองซ้ำ); `_move_processed_files` ย้ายไฟล์ในซับโฟลเดอร์ด้วย (เดิมไม่ย้าย → ตรวจซ้ำทุกครั้ง) |
| M3 | `test_parser_helpers.py`, `test_file_size_ceiling.py` | แพ็ก GOLDEN CI แดง: อัป assert `KRR_69_012→month 1` (ตาม FIX-MONTH012); whitelist `parser_p2.py` (602 LOC) พร้อมแผนซอย `_pb_*`→`parser_p3` |
| M4 | `reporting_p0/p1/p2.py` | `detail=None` บน issue CRITICAL → `None[:80]` ครัชรายงาน+dashboard. coerce None (`setdefault` ไม่ทับ None); read site None-safe; +กัน KeyError `master_key` |
| M5 | `rules_engine.py:207` | `run_rules` setdefault แค่ 4 คีย์ แล้วอ้าง `bill['company']/['sheet']` ดิบ → บิลภายนอกครัช/ข้ามกฎเงียบ. setdefault คีย์ที่อ้างให้ครบ |
| M6 | `analytics.py:214` | `_num(NaN)` คืน NaN (docstring บอกควร 0.0) → ยอดรวม/อันดับเพี้ยน. เพิ่ม `if f != f: return 0.0` |

---

## 🟢 ต่ำ + architectural

| # | ไฟล์ | สรุป |
|---|------|------|
| L2 | `puopuy_units.py` | `_D('(1,234.56)')` → -1234.56 (เลขติดลบบัญชี เดิมคืน None ทิ้งค่า) — เฉพาะ `(ตัวเลขล้วน)` |
| L3 | `config_base.py` + `pukpui_modular_consts.py` | ย้าย enrichment `CONSTRUCTION_DICT` (160 คำ) ไปไว้ที่เจ้าของข้อมูล → 263 คำทุกเส้น import (เดิม enrich เฉพาะผ่าน modular_base) |
| L4 | `rules_engine_rules_a.py:540` | `r_itm001` ห่อ quantize (`ArithmeticError`) เหมือน `r_itm018` |
| L5 | `rules_engine_rules_b.py:42` | `r_itm014` กรอง seq int แท้เหมือน `r_itm013` (กัน `sorted([...None])` TypeError) |
| L6 | `validators.py` | `detect_iv_period_mismatch` ไม่ตีเลขรัน 4 หลักล้วน (ไม่มี prefix) เป็นงวด → กัน DT004 false positive |
| L7 | `rules_engine_rules_c.py:350` | `r_itm016` ข้าม dedup เมื่อ `price=None` (กัน flag ซ้ำหลอก) |
| L8 | `parser_p0a/p2` | รับ seq text `'1.00'/'1.0'` (เดิม `removesuffix('.0')` พลาด) — รวมใน `_is_seq_token` |
| L9 | `puopuy_dates.py:58` | วันที่ปี 2 หลัก + เวลา (`'5/5/69 10:00:00'`) → ไม่ตก None |
| L-T | `pukpui_modular_funcs.py` | `done_dir` +PID กันชื่อโฟลเดอร์ชนเมื่อรัน 2 รอบในวินาทีเดียว |
| ARCH | `pukpui_modular_funcs.py:317` | `_audit_core_crosschecks` ห่อแต่ละ crosscheck แยกกัน (เดิมตัวเดียว throw ดึงที่เหลือร่วงหมด) |

---

## ❌ สิ่งที่ "ไม่แก้" โดยเจตนา (และเหตุผล)

- **L1 — `thai_postal` prefix จังหวัด (agent เสนอให้ตัดให้แคบ)**: **ไม่ใช่บั๊ก**. ตารางนี้ derive จากชุด
  ข้อมูล geography จริง (7,436 ตำบล) และมี **pinned test** `test_addr006.py:43` ยืนยัน
  `เชียงใหม่ + 58130 → เงียบ` (อำเภอชายแดนใช้ prefix ข้ามจังหวัดจริง). การ "แก้" จะทำเทสแดง +
  เสี่ยง false-positive กับที่อยู่จริง — ขัดปรัชญา "false-negative ดีกว่า false-positive". จึงคงไว้.

---

## ตรวจการแก้ (verification)

- `python3 -m compileall` ผ่าน (ไม่มี syntax error)
- spot-check: H1 `_money_q('1e30')=None` & `_money_q('8742.125')=8742.13`; H2 `_is_seq('²')=False`,
  `_is_seq('๕')=True`; M1 `parse_date_any(datetime(2568,2,29))=None`; L3 `config.CONSTRUCTION_DICT` 263 คำ
- e2e: `parse_file` กับยอดมหึมา → ไม่หายบิล; superscript → SYS003 (graceful) ไม่ใช่ SYS001 (crash)
- e2e: `build_clean_report` กับ control-char & `detail=None` → ออกไฟล์รายงานได้ (เดิมครัช)
- full pipeline `main.py` บน real_cases → EXIT 0, รายงานครบ 7 ชีต + company_summary + ultra
- **digest real_cases เท่าเดิมเป๊ะ** ก่อน/หลังแก้ (golden-neutral, sentinel ยืนยัน)
- pytest standalone **81/81 ผ่าน**
