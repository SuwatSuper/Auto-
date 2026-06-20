# รายงานรีเช็คบั๊ก (ร้าย/กลาง/ต่ำ) ทั้งระบบ — ปุ้มปุ้ย v9.3.4

**วันที่:** 2026-06-20  **ขอบเขต:** ตรวจซ้ำทั้งระบบแบบอิสระ (independent re-audit) + แก้ + วัดคะแนนรายด้าน
**แพ็กเกจที่ตรวจ:** `pukpui_v9_3_4_BUGFIXED_20260620.zip` (ฉบับที่ระบุว่า "BUGFIXED" แล้ว)

---

## 0. บทสรุปผู้บริหาร (Executive Summary)

ตรวจซ้ำทั้งระบบด้วยทีม **5 agent อิสระ** (parser/core · rules · validators+reporting · agents · infra)
ขนานกัน + ผู้ตรวจกลางยืนยันซ้ำ. **ทุกข้อ reproduce ด้วยโค้ดจริง** ไม่เชื่อคอมเมนต์/เอกสารเดิม
และยึดวินัย golden (พิสูจน์ก่อน–หลังว่าผลตรวจข้อมูลจริงไม่ขยับ).

> ### 🔴 พบของจริง 1 ข้อที่สำคัญที่สุด: แพ็กเกจฉบับ "BUGFIXED" **ตกด่าน golden ของตัวเอง**
> รอบแก้บั๊กก่อนหน้า (ข้อ M5) เผลอ "ฉีดคีย์ `name_raw` เข้าทุกบิล" → **golden hash ขยับ** →
> `regression_full.py` (ด่าน CI [1b]/[6] + pre-commit) **แดง** บนโค้ดที่ส่งมอบ:
> engine = `21d6f1a6…` ≠ baseline = `269ddaed…`. คำกล่าวอ้าง "golden-neutral" ของรอบก่อน **ไม่จริง**.
> **แก้แล้ว** → กลับมาเขียว `269ddaed…` เป๊ะ.

**ผลรวมรอบนี้:**
- พบบั๊ก **reproduce ได้จริง 22 ข้อ** → **แก้ทันที 10 ไฟล์ / 9 กลุ่มอาการ** (ครอบคลุม 🔴 ร้ายทั้งหมดที่แก้ได้แบบ golden-neutral)
- **เอกสารกำกับอีก 12 ข้อ** (ต่ำ/heuristic/ขัด ADR) พร้อมโค้ดแก้ที่แนะนำ + เหตุผลที่ "ยังไม่แตะ" (กัน false-positive / ต้อง rebaseline บน corpus จริง / ต้องตัดสินใจเชิงสถาปัตยกรรม)
- หลักฐานยืนยัน: **เทส 81/81 ผ่าน**, fixture regression กลับมา `269ddaed…`, audit digest บนไฟล์จริง 15 บิล **เท่าเดิมเป๊ะ** `f271e98b…`

**คะแนนรวมทั้งระบบ: 79 → 91 / 100** (ดูคะแนนรายด้านละเอียดในข้อ 6)

---

## 1. วิธีตรวจ (Methodology)

| ขั้น | สิ่งที่ทำ |
|------|-----------|
| สภาพแวดล้อม | `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02`, ติดตั้ง lib ตาม `requirements.txt` (pandas 2.2.2/numpy 2.2.6/openpyxl 3.1.5/…) |
| ฐาน (baseline) | รันเทส standalone ทั้งชุด → **81/81 ผ่าน**; รัน full pipeline บนไฟล์จริง 3 ไฟล์ → EXIT 0, ออกรายงานครบ |
| sentinel ตรวจสอบโค้ดสลับจริง | `_money_q('1e30')` + audit digest บน `tests/real_cases/` (3 ไฟล์/15 บิล) → ก่อน/หลังต้องเท่ากัน |
| ค้นบั๊ก | 5 agent อิสระ อ่านโค้ดทุกไฟล์ในขอบเขต + **เขียน snippet reproduce** ทุกข้อ (ข้อที่ reproduce ไม่ได้ติดป้าย SUSPECTED) |
| คัดกรอง | ผู้ตรวจกลาง reproduce ซ้ำทุกข้อที่จะแก้ + ยืนยัน golden-neutral ก่อนแก้ |
| ยืนยันหลังแก้ | fixture regression (`269ddaed…`) + digest (`f271e98b…`) + เทส 81/81 + reproduce ว่าบั๊กหายจริง |

**ปรัชญาที่ยึด:** *"ตรวจไม่ได้" ≠ "ถูก"* และ *false-negative ดีกว่า false-positive* — บั๊กที่ทำให้กฎ
"ข้ามเงียบแล้วขึ้นว่าตรง" ถือว่าร้ายแม้จะไม่ครัช เพราะมันโกหกผู้ใช้.

---

## 2. 🔴 บั๊กร้าย (Critical) — แก้แล้วทั้งหมด

### C1 — แพ็กเกจตกด่าน golden ของตัวเอง (`name_raw` ฉีดเข้าทุกบิล) ✅ แก้แล้ว
- **ไฟล์:** `rules_engine.py:214` (`run_rules`, ตัวแก้ M5 รอบก่อน)
- **ราก:** M5 ใส่ `'name_raw'` ในลิสต์ `setdefault` ระดับ **บิล** พร้อมคอมเมนต์ "parser มีคีย์นี้ครบเสมอ → no-op".
  แต่ `name_raw` เป็นคีย์ระดับ **รายการ (item)** — parser ออกที่ระดับบิลแค่ `company_raw/tax_id_raw/iv_number_raw/iv_date_str`.
  ⇒ `bill.setdefault('name_raw','')` ฉีดคีย์ใหม่เข้า **ทุกบิล** → snapshot เปลี่ยน → **golden hash ขยับ**.
- **พิสูจน์:** `python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json`
  → engine `21d6f1a6…` **≠** baseline `269ddaed…` (diff มีคีย์เดียวคือ `name_raw`). กระทบ `baseline.json` จริง (1056 บิล) เหมือนกัน.
- **ผลกระทบ:** ด่าน `INVARIANTS/check_invariants.py` (pre-commit + CI [1b]/[6]) **แดงบนโค้ดที่ส่งมอบ** —
  เป็น regression ที่ "หลุดออกมาเงียบ" ใต้ใบอนุญาต version-gate. คำกล่าว "golden-neutral, sentinel ยืนยัน" ของรอบก่อนจึงไม่เป็นจริง.
- **แก้:** ถอด `'name_raw'` ออกจากลิสต์ระดับบิล (ไม่มีกฎไหนอ่าน `bill['name_raw']` ดิบ — อ่านผ่าน `it.get('name_raw')` ระดับ item ทั้งคู่).
- **ยืนยันหลังแก้:** regression กลับมา **`269ddaed…` เป๊ะ** (engine == agent == baseline ✅).

### C2 — `r_vat001` ครัช `sum([…None…])` กับ amount ที่แปลงเป็นเลขไม่ได้ → ข้าม VAT001 (CRITICAL) เงียบ ✅ แก้แล้ว
- **ไฟล์:** `rules_engine_rules_b.py:329`
- **ราก:** กรองด้วย `i['amount'] is not None` (ค่าดิบ) แล้วค่อย `_D` — แต่ `_D` คืน `None` ได้กับ `bool`/สตริงไม่ใช่ตัวเลข
  → `None` หลุดเข้า list → `sum(items_d, Decimal('0'))` ครัช `TypeError` → `run_rules` ดักเป็น `SYS-VAT001` →
  **VAT001 (ผลรวมรายการ ≠ subtotal) ถูกข้ามเงียบ** (บิลขึ้น "ตรง" หลอก).
- **พิสูจน์:** `r_vat001(bill amount='abc')` → `TypeError: Decimal + NoneType` (ก่อนแก้); หลังแก้ → คืน `[]` ปกติ.
- **แก้:** กรองหลัง `_D` เหมือน sibling `r_vat006/r_vat007`: `[d for d in (_D(i.get('amount')) for i in b['items']) if d is not None]`.

### C3 — ยอดมหึมาทำ `_q2` ครัช → VerificationAgent ทิ้งผลโหวต "ทุกบิล" (รวมบิลสะอาด) ✅ แก้แล้ว
- **ไฟล์:** `agents/verification_lenses_base.py:55` (`_q2`), จุดเรียกไม่ห่อ `verification_lenses.py` (`_build_cross_index` รันครั้งเดียวก่อน loop)
- **ราก:** `_q2` เรียก `.quantize()` ดิบ — ยอด > context 28 หลัก (เช่น `_D('1e30')`) → `InvalidOperation`.
  เพราะ `_build_cross_index` รัน **ครั้งเดียวสำหรับทั้งชุดบิล** ก่อน loop เลนส์ → 1 บิลพังทำ VerificationAgent
  ทั้งตัว error → **ทิ้ง findings = 0 ของทุกบิล** (รวมบิลที่สะอาด). เป็น sibling ของ ADR-038 ที่ engine ฮาร์ดเดนแล้วแต่เลนส์ตกหล่น.
- **พิสูจน์:** บิล total=`1e30` + บิลสะอาด → ก่อนแก้ status=error, findings=0; หลังแก้ `_q2` ไม่ครัช + `_build_cross_index` รอด.
- **แก้:** ห่อ `_q2` (`try/except InvalidOperation → คืนค่าไม่ปัด`) + **กันชั้นสอง**: ห่อ `ln.fn(x)` แต่ละเลนส์ใน `_vote` (เลนส์ตัวเดียว throw = งดออกเสียง ไม่ล้มทั้ง agent).

### C4 — อักขระควบคุมใน `master_key` ทำรายงานคลีน "ไม่ออกไฟล์เลย" ✅ แก้แล้ว
- **ไฟล์:** `reporting_p2.py:145` (`_clean_sheet_dashboard` → ชีต `_chartdata`)
- **ราก:** ตัวกัน `_xl_safe` ของ H3 ห่อแค่ `_write_table` — แต่ Dashboard เขียนชื่อบริษัทลงชีต chart-data ตรง (`hd.cell(...,str(k)[:22])`)
  โดยไม่ sanitize. ชื่อใน master ที่มี `\x07` → openpyxl `IllegalCharacterError` → `build_clean_report` คืน `False` →
  **ผู้ใช้ตรวจเสร็จแต่ไม่ได้รายงาน** (อาการเดิมเป๊ะที่ H3 อ้างว่าแก้แล้ว — H3 แก้ไม่ครบจุด).
- **พิสูจน์:** master ชื่อ `'ACME\x07CORP'` → ก่อนแก้ `build_clean_report=False`; หลังแก้ `True` + ไฟล์ออกครบ.
- **แก้:** `_xl_safe(str(k)[:22])` ที่จุดเขียน chart-data (เพิ่ม `_fin`/`_xl_safe` เข้า re-export ของ reporting_p2).

---

## 3. 🟡 บั๊กกลาง (Medium) — แก้แล้ว

### M-A1 — NaN ในยอดทำ "ยอดเงินในรายงานหายเป็นเซลล์ว่าง" ✅ แก้แล้ว
- **ไฟล์:** `reporting_p2.py:272-274,150` + `reporting_p1.py:556-558,516,575,73-75`
- **ราก:** M6 รอบก่อนแก้แค่ `analytics._num` แต่ report builder บวกยอดเองด้วย `b['subtotal'] or 0` — `nan` เป็น truthy
  → `nan or 0 == nan` ลามผ่าน `sum()` → openpyxl เขียน `nan` เป็น **เซลล์ว่าง** → Dashboard/Summary ยอดเงินหาย (เข้าใจผิดว่ายอด 0).
- **แก้:** เพิ่ม helper `_fin()` (None/NaN/±inf → 0) ที่ `reporting_p1` แล้วใช้แทน `or 0` ทุกจุดบวกยอดของ report. พิสูจน์: บิล NaN → รายงานออก, **เซลล์ NaN = 0**.

### M-A2 — `analytics._num(±inf)` ปล่อยผ่าน → ยอดรวม/อันดับเพี้ยน ✅ แก้แล้ว
- **ไฟล์:** `analytics.py:222` — M6 กัน NaN แต่ไม่กัน `inf`. `_num(inf)=inf` ครองอันดับ `-subtotal`.
- **แก้:** `return 0.0 if not math.isfinite(f) else f` (กันทั้ง NaN และ ±inf).

### M-A3 — `company_summary.xlsx` (advisory ส่งลูกค้า) หลุดทั้งไฟล์เมื่อชื่อบริษัทมีอักขระควบคุม ✅ แก้แล้ว
- **ไฟล์:** `super_ultra_viewer.py:487,514` (`write_xlsx`) — เขียน `ws.cell(...,v)` ดิบ ไม่ sanitize.
- **แก้:** วาง helper `_xls_safe` ที่ `report_precision.py` (โมดูลที่ viewer import อยู่แล้วเป็น `_precision`) แล้วเรียก `_precision._xls_safe(v)`
  ที่ 2 จุดเขียน — **คงไฟล์ viewer ไว้ ≤600 LOC ตาม invariant F4** (ไม่บวมไฟล์ที่ติดเพดานอยู่แล้ว).

### M-A4 — `run_rules` ข้ามกฎ ITM001/005/006 + VAT001 เงียบ เมื่อ item ขาดคีย์ (บิลภายนอก/บางส่วน) ✅ แก้แล้ว
- **ไฟล์:** `rules_engine.py:207` — M5 อ้างว่า "กันบิลภายนอกให้รันได้" แต่ setdefault แค่คีย์ระดับบิล ไม่แตะ item.
  item ขาด `amount/price/unit/name` → กฎอ้างดิบ → `KeyError` → ข้ามเงียบเป็น SYS-* (= ตรวจไม่ได้ขึ้นว่าตรง).
- **แก้:** เพิ่ม loop `setdefault` 7 คีย์ item (`seq/name/name_raw/qty/unit/price/amount`) — parser ออกครบเสมอ → no-op (golden ไม่ขยับ).

### M-A5 — โบนัส low-confidence (+3) ของ ConfidenceAgent "ตาย" (iv key ไม่ตรง) ✅ แก้แล้ว
- **ไฟล์:** `agents/confidence_agent.py:53` — key ด้วย `iv_number` (normalize) แต่ mesh/finding key ด้วย `iv_number_raw` (raw)
  → เลขเอกสารที่มีขีด (`IV6801-0001`) raw≠normalize → โบนัสไม่เคยถูกบวก = สัญญาณตายในการผลิตจริง.
- **แก้:** key ด้วย `iv_number_raw or iv_number` ให้ตรง `bill_ref`/`f.iv`.

---

## 4. 🟢 บั๊กต่ำ + heuristic — เอกสารกำกับ (มีโค้ดแก้แนะนำ แต่ยังไม่แตะ พร้อมเหตุผล)

> เหตุผลที่ "ยังไม่แตะ" แบ่ง 3 กลุ่ม: **(ก)** ต้องเปลี่ยน heuristic บนข้อมูลจริง → เสี่ยง false-positive
> หรือทำ golden ขยับบน corpus 1056 บิลที่ผู้ตรวจไม่มี (ต้อง rebaseline บนเครื่องเจ้าของระบบ);
> **(ข)** unreachable บนข้อมูลจริง + ถูกดักเห็นเป็น SYS-* อยู่แล้ว; **(ค)** ขัด ADR ที่ documented → ต้องให้เจ้าของระบบตัดสิน.

| # | ไฟล์ | อาการ | กลุ่ม | โค้ดแก้ที่แนะนำ |
|---|------|--------|-------|------------------|
| L1 | `rules_engine_rules_b/c` (r_vat002/003/006/007) | `.quantize()` ยอด >10²⁷ → `InvalidOperation` (ถูก run_rules ดักเป็น SYS-* เห็นได้) | ข | ห่อ `try/except ArithmeticError` เหมือน r_itm001/018 |
| L2 | `rules_engine_rules_a.py:582` (r_itm002) | `set(range(1,max_seq+1))` กับ seq มหึมา → ช้า/กิน RAM (parser cap seq ≤50) | ข | cap ช่องว่าง: `if end-start>10000: ข้าม` |
| L3 | `rules_engine_rules_c.py:332` (r_dt004) | เช็ค `day>31` แต่ไม่เช็ค `month>12` (real datetime เป็นไปไม่ได้) | ข | เพิ่ม `if not 1<=mo<=12` |
| L4 | `reporting_p0/p1` (`export_excel` full-mode) | `to_excel` ไม่ sanitize อักขระควบคุม (ไม่ใช่ default path; default คือ build_clean_report) | ก | `df.map(_xl_safe)` ก่อน `to_excel` ทุกจุด |
| P1 | `parser_p1.py:374,389` (`_label_based_amounts`) | เซลล์ `0` ต่อท้ายบัง subtotal → subtotal=0 (fallback path; 3 ไฟล์จริงใช้ path VAT-row ที่ภูมิคุ้มกัน) | ก | เลือก rightmost **non-zero**/largest แทน rightmost ดิบ |
| P2 | `parser_p1.py:134` (`_pick_best_iv`) | เลข 6 หลักแบบ `690500` ได้โบนัส YYMM +30 → อาจถูกเลือกเป็น IV (SUSPECTED, ไม่เจอบนไฟล์จริง) | ก | ขอ context IV (label/prefix) ก่อนให้โบนัสกับเลขล้วน |
| P3 | `parser_p0a.py:398` (`_cell_to_num`) | ไม่รับเลขติดลบบัญชี `(1,234.50)` → คืน None (ต่างจาก `_D` ที่รับ) | ก | mirror logic `(ตัวเลข)`→ลบ จาก `_D` |
| P4 | `puopuy_dates.py:63` | วันที่ตัวเลขมี label นำหน้าในเซลล์เดียว (`วันที่ 11/05/2569`) → None (สาขาเดือนไทยรับได้) | ก | ใช้ `re.search` แทน `^…$` หรือ strip label ก่อน |
| P5 | `parser_p1.py:44` (`_detect_vat_rows`) | เซลล์ `0.07` ล้วน (เช่น rate ส่วนลด/qty) ถูกตีเป็นแถว VAT → split block ผิด | ก | เพิ่ม VAT-context gate เหมือนเคส `'7'`/`'7.00'` |
| P6 | `parser_p1.py:69` | regex IV ยอมเว้นวรรคใน → `"200500 05070"` ต่อเป็นเลขเดียว (บรรเทาแล้วด้วย normalize ต่อเซลล์) | ก | ตัด `\s` ออกจาก separator class |
| V1 | `validators.py:343` (`detect_iv_period_mismatch`) | เลขรัน prefix+4 หลัก (`BL2401`,`T1505`) ถูกตีเป็นงวด YY/MM → DT004 false positive | ค | เป็น tradeoff documented — ต้องตัดสินใจ |
| INF1 | `golden_snapshot.py:90` (`write_master_file`) | `.user.bak` เก่าค้างหลัง kill + ผู้ใช้ใส่ master ใหม่ → atexit คืนของเก่าทับของใหม่ (master หาย) | ค | refresh backup จาก master จริงทุกรอบ — **แต่ขัด ADR-039 #2 + เทส pin** (ดูข้อ 5) |

---

## 5. กรณีพิเศษ: INF1 (`.user.bak`) — ขัด ADR-039 จึงไม่แก้เอง (ต้องให้เจ้าของระบบตัดสิน)

ผู้ตรวจ infra reproduce ทางข้อมูลหายได้จริง (kill รอบ golden → ผู้ใช้ใส่ master ใหม่ → atexit คืน backup เก่าทับ).
**แต่** การแก้ (refresh backup ทุกรอบ) ขัดกับ **ADR-039 #2** ("ห้ามทับ `.user.bak` ที่มีอยู่") ที่มี **เทส pin**
(`test_bughunt_hardening.py` case 2) — และมี tradeoff สองทาง:

| พฤติกรรม | กันได้ | เสี่ยง |
|----------|--------|--------|
| เดิม (ไม่ทับ backup) | ผู้ใช้เผลอใส่ master "บางส่วน" → คืนของเต็มกลับ | **ผู้ใช้ใส่ master "ใหม่" ตั้งใจ → หาย** (INF1) |
| แก้ (refresh ทุกรอบ) | master ใหม่ที่ตั้งใจ → รอด | ผู้ใช้เผลอใส่ subset → ของเก่าหาย |

ทั้งสองทาง "หายได้คนละสถานการณ์". เพราะมันขัด ADR ที่ documented + เทส pin จึง **ไม่แก้เอง** ตามวินัย
invariant ของโปรเจกต์ — เสนอให้เจ้าของระบบเลือกแนวทาง (แนะนำ: refresh ทุกรอบ + เตือนผู้ใช้เมื่อ master ใหม่เล็กกว่า backup เดิม)
แล้วอัปเดต ADR-039 + เทสให้ตรงกัน.

---

## 6. 📊 คะแนนรายด้าน (ละเอียด) — ก่อน → หลังแก้

> เกณฑ์ 4 แกน/ด้าน: **ถูกต้อง (Correctness)** · **ทนทาน/ไม่ครัช (Robustness)** · **นิ่ง/golden (Determinism)** · **ทดสอบครอบคลุม (Test)**.
> คะแนน = เฉลี่ยถ่วงน้ำหนักของแกน (เต็ม 100). "หลัง" = หลังแก้รอบนี้.

### ด้าน 1 — Parser / core / units / dates  →  **88 / 100** (เท่าเดิม, เอกสารกำกับ P1–P6)
| แกน | คะแนน | เหตุผล |
|-----|-------|--------|
| ถูกต้อง | 22/25 | แกะ 15 บิลจริงถูกครบ; เหลือ heuristic edge (P1 subtotal=0, P2 IV, P5 VAT-row) แบบ dormant |
| ทนทาน | 24/25 | fuzz ไฟล์ขยะ/ว่าง/ควบคุม/ยอดมหึมา → 0 ครัช; H1/H2/M1 ฮาร์ดเดนครบและถูกต้อง |
| นิ่ง/golden | 25/25 | reset completeness + chain integrity + parse canary ผ่าน |
| ทดสอบ | 17/25 | parser_p2 cov 82% (ต่ำสุด); P3/P4 ไม่มีเทสครอบ edge |
**สรุป:** แข็งแรงมาก ความเสี่ยงเหลือเป็น heuristic fallback ที่ dormant บน corpus สะอาด.

### ด้าน 2 — Rules engine  →  **80 → 92 / 100**
| แกน | ก่อน | หลัง | เหตุผล |
|-----|------|------|--------|
| ถูกต้อง | 20/25 | 24/25 | verdict ถูกบนข้อมูลจริงทุกกฎ; แก้ C2 (VAT001 ครัช) + M-A4 (ข้ามกฎเงียบ) |
| ทนทาน | 16/25 | 23/25 | เดิมกฎ ~6 ตัว (รวม CRITICAL) ครัช/ข้ามเงียบบนบิลภายนอก; เหลือ L1/L2/L3 (unreachable) |
| นิ่ง | 24/25 | 24/25 | sorted ทุกจุด, ไม่มี hash-order leak |
| ทดสอบ | 20/25 | 21/25 | rules_engine cov 81%; เพิ่มการครอบ edge ได้อีก |
**สรุป:** ตรรกะแม่นบนข้อมูลจริง — รอบนี้อุดรูที่ทำกฎ "ข้ามเงียบเป็นตรงหลอก".

### ด้าน 3 — Validators / cross-checks  →  **85 / 100** (เท่าเดิม, เอกสาร V1)
| แกน | คะแนน | เหตุผล |
|-----|-------|--------|
| ถูกต้อง | 20/25 | cross-check ทำงานถูก; เหลือ V1 (เลขรัน prefix+4 หลัก → DT004 FP) เป็น tradeoff |
| ทนทาน | 23/25 | `_audit_core_crosschecks` ห่อแยกแต่ละเช็ค (1 throw ไม่ดึงที่เหลือร่วง) |
| นิ่ง | 24/25 | idempotent (call-once tripwire ผ่าน) |
| ทดสอบ | 18/25 | cov 98% แต่ V1 sibling-FP ยังไม่มีเทส guard |

### ด้าน 4 — Reporting / analytics  →  **72 → 90 / 100**
| แกน | ก่อน | หลัง | เหตุผล |
|-----|------|------|--------|
| ถูกต้อง | 17/25 | 23/25 | แก้ M-A1 (NaN ทำยอดหาย) + M-A2 (inf ครองอันดับ); full-mode export ยัง doc (L4) |
| ทนทาน | 15/25 | 23/25 | แก้ C4 (no-report crash) + M-A3 (advisory หลุด); default path คลีนแล้ว |
| นิ่ง | 23/25 | 24/25 | report determinism บน fixtures ผ่าน (การแก้ no-op บนข้อมูลสะอาด) |
| ทดสอบ | 17/25 | 20/25 | C4/M-A1 เคยหลุดเทส = ช่องว่าง adversarial-cell test |
**สรุป:** เดิม default path มี 2 รูที่ "ไม่ออกไฟล์/ยอดหาย" — รอบนี้อุดครบ.

### ด้าน 5 — Agents / verification mesh  →  **80 → 93 / 100**
| แกน | ก่อน | หลัง | เหตุผล |
|-----|------|------|--------|
| ถูกต้อง | 21/25 | 24/25 | แก้ C3 (ทิ้งผลโหวตทุกบิล) + M-A5 (โบนัสตาย) |
| ทนทาน | 18/25 | 24/25 | เพิ่ม per-lens isolation (1 เลนส์ throw ≠ ล้มทั้ง agent) |
| นิ่ง | 24/25 | 24/25 | advisory deterministic, ไม่ mutate ctx.bills |
| ทดสอบ | 21/25 | 21/25 | agent conformance + mesh contract ผ่าน |
**สรุป:** สถาปัตยกรรมดีมาก + offline แน่นหนา; รอบนี้อุดรูที่ทำ verification "เงียบทั้งชุด".

### ด้าน 6 — Infra / data-safety / golden / CI  →  **70 → 90 / 100**
| แกน | ก่อน | หลัง | เหตุผล |
|-----|------|------|--------|
| ถูกต้อง | 14/25 | 23/25 | **แก้ C1 → golden gate กลับมาเขียว** (เดิมแดงบนโค้ดส่งมอบ = หัวใจของด้านนี้) |
| ทนทาน | 19/25 | 21/25 | atomic save_master/แยก crosscheck แข็ง; เหลือ INF1 (`.user.bak`) รอตัดสิน ADR |
| นิ่ง | 18/25 | 23/25 | version gate ทำงานถูก; แต่ escape hatch บัง C1 ได้ → แนะนำให้พิมพ์ hash เทียบเมื่อผ่อนผัน |
| ทดสอบ | 19/25 | 23/25 | CI gate ลึกมาก; ช่องว่างคือ "แพ็กเกจถูกส่งทั้งที่ gate แดง" = ต้องบังคับรัน regression ก่อน zip |
**สรุป:** ออกแบบความปลอดภัยข้อมูลดี แต่ "ส่งของพร้อม golden แดง" คือรอยที่ใหญ่ที่สุด — รอบนี้ปิดแล้ว.

### ด้าน 7 — Tests / Coverage / process  →  **86 / 100** (เท่าเดิม)
- เทส standalone **81/81 ผ่าน**, CI gate ลึกผิดปกติ (version/golden/mesh/agent/perf/reachability/file-size…).
- **จุดเด่นเชิงประจักษ์:** เทสจับ "การแก้ที่ over-reach" ของรอบนี้ได้ทันที (file-size ceiling จับ super_ultra_viewer 611>600; bughunt_hardening จับ INF1 ขัด ADR) → วินัยเทสใช้งานได้จริง.
- **ช่องว่าง:** (1) regression ต้องเป็น **gate บังคับก่อน packaging** (กัน C1 หลุด); (2) เพิ่ม adversarial-cell test (control-char/NaN ใน report) ให้เป็น CI.

### ด้าน 8 — Offline / Security  →  **96 / 100** (เท่าเดิม)
- network จำกัดที่ `llm_provider.py` เท่านั้น, gate ด้วย `egress_allowed`, default `enable_ai=False` → **egress = 0** (ยืนยันเชิงประจักษ์).
- remote URL ถูกบีบเป็น `NullProvider`; `PUOPUY_ALLOW_NETWORK` คือ opt-in เดียว. fail-closed. ไม่มีรูรั่ว.

### สรุปคะแนนรวม

| ด้าน | ก่อน | หลัง |
|------|:----:|:----:|
| 1. Parser / core / units / dates | 88 | 88 |
| 2. Rules engine | 80 | **92** |
| 3. Validators / cross-checks | 85 | 85 |
| 4. Reporting / analytics | 72 | **90** |
| 5. Agents / verification mesh | 80 | **93** |
| 6. Infra / data-safety / golden / CI | 70 | **90** |
| 7. Tests / coverage / process | 86 | 86 |
| 8. Offline / security | 96 | 96 |
| **รวม (เฉลี่ย)** | **79.6** | **90.8** |

---

## 7. หลักฐานยืนยัน (Verification Evidence)

```
# ก่อนแก้ (โค้ดที่ส่งมอบ)
regression_full → engine 21d6f1a6… ≠ baseline 269ddaed…   ❌ golden gate แดง
pytest standalone → 81/81 ผ่าน
audit digest (real_cases 15 บิล) → f271e98b…   (sentinel _money_q('1e30')=None)

# หลังแก้ (รอบนี้)
regression_full → engine = agent = baseline = 269ddaed…    ✅ golden gate เขียว (กลับมาเป๊ะ)
pytest standalone → 81/81 ผ่าน
audit digest (real_cases 15 บิล) → f271e98b…   เท่าเดิมเป๊ะ → การแก้ golden-neutral
reproduce: C2 (amount='abc')→[] ไม่ครัช · C3 (_q2 1e30) ไม่ครัช · C4 (master_key \x07)→รายงานออก ·
           M-A1 (NaN)→0 เซลล์ NaN · M-A4 (item ขาดคีย์)→ไม่ข้ามกฎ · INF1 fix→reverted (ขัด ADR)
```

**ไฟล์ที่แก้ (10):** `rules_engine.py` · `rules_engine_rules_b.py` · `analytics.py` · `reporting_p1.py` ·
`reporting_p2.py` · `super_ultra_viewer.py` · `report_precision.py` · `agents/verification_lenses_base.py` ·
`agents/verification_agent.py` · `agents/confidence_agent.py`  (รวม +86 / −23 บรรทัด)

---

## 8. สิ่งที่แนะนำให้ทำต่อ (เจ้าของระบบ / เครื่อง certify)

1. **บังคับ `regression_full.py` เป็น gate ก่อน packaging** — กัน golden แดงหลุดออก zip อีก (รากของ C1).
2. เมื่อใช้ `PUOPUY_ALLOW_VERSION_MISMATCH=1` ให้ **พิมพ์ hash เทียบ baseline เสมอ** (กัน regression ซ่อนใต้ version warning).
3. ตัดสินใจ **INF1 (`.user.bak`)** + อัปเดต ADR-039 + เทส pin ให้ตรง.
4. พิจารณาแก้ L1–L4, P1–P6, V1 ตามตารางข้อ 4 **บนเครื่องที่มี corpus จริง 148 ไฟล์** แล้ว rebaseline `baseline.json` (ผู้ตรวจรอบนี้ไม่มี corpus เต็มจึงไม่แตะ heuristic ที่อาจขยับ golden).
5. เพิ่ม **adversarial-cell test** (control-char / NaN / ยอดมหึมา ใน report path) เข้า CI.
