# รายงานล่าบั๊ก + Harden — ปุ้มปุ้ย v9.3.1 (รอบ 17.06.2026)

> ภารกิจ: หาบั๊ก 🔴ร้ายแรง / 🟡กลาง / 🟢ต่ำ ให้ครบ แล้ว **แก้เฉพาะบั๊กจริงที่ reproduce ได้
> และปลอดภัยต่อ golden oracle** — ห้ามเพิ่มฟีเจอร์ ห้ามปล่อย golden ดิ้นโดยไม่มี rebaseline

---

## 0) ข้อจำกัดด้านสภาพแวดล้อม (อ่านก่อน — สำคัญต่อการตีความรายงาน)

ระบบนี้ผูกความถูกต้องกับ **golden hash บน corpus จริง 106 ไฟล์ / 834 บิล** (`d6b23d12…8173`)
ซึ่งเป็น **ข้อมูลผู้เสียภาษีออฟไลน์** ที่ **ไม่ได้มากับแพ็กเกจ** (และห้ามออกเครื่องตามกฎเหล็กข้อ 1).
ในกล่องทำงานนี้จึง **ไม่มี corpus จริง** → **ไม่สามารถ reproduce `d6b23d12…` ได้**

สิ่งที่ "มี" และใช้เป็น oracle ได้จริง:
- **fixture oracle ที่ reproduce ได้** : `269ddaed…` (3 บิล) — `engine == agent == baseline` ✅
- **3 ไฟล์ .xls จริง** ใน `tests/real_cases/` (KRR/TKH/STC) + ชุดเทส 76 ไฟล์ + CI 78 ด่าน

**หลักการตัดสินใจที่ใช้ (ยึด GOLDEN-SAFETY PROTOCOL อย่างเคร่งครัด):**
- **แก้ได้** เฉพาะบั๊กที่ **golden-safe** = อยู่บนเส้น error/edge/malformed ที่ corpus สะอาด
  "ไม่เคยเดินผ่าน" หรือ off-audit-path → พิสูจน์ได้ว่า fixture oracle `269ddaed…` ไม่ขยับ
- **บั๊กที่ golden-affecting** (แก้แล้วผลตรวจบน corpus จริงเปลี่ยน) → **รายงานอย่างเดียว ไม่แก้**
  เพราะการแก้ที่ถูกต้องต้องมาพร้อม **rebaseline บน corpus จริง** ซึ่งทำที่นี่ไม่ได้
  (การแก้แล้วเดา hash ใหม่เอง = ผิด protocol). ทำเครื่องหมาย **[ต้อง rebaseline]**

> นี่คือเหตุผลที่บั๊กระดับร้ายแรงบางตัว (เช่น Validators-S1) ถูก **รายงานไว้ ไม่ใช่แก้** — ไม่ใช่เพราะ
> มองข้าม แต่เพราะแก้อย่างปลอดภัยต้องมี corpus จริง + ceremony rebaseline ที่เจ้าของระบบทำเอง

---

## 1) สรุปผล (เขียวครบเท่าที่ทำได้แบบไม่มี corpus)

| ตรวจ | ผล |
|------|----|
| fixture oracle (`engine==agent==baseline`) | ✅ `269ddaed…` (ก่อน=หลังแก้ทุก commit) |
| เทสทั้งหมด `test_*.py` | ✅ **76/76** exit 0 |
| `run_ci.sh` (ไม่รวมด่านที่ต้อง corpus) | ✅ **78 ด่านผ่าน, 0 ล้มเหลว** |
| parallel == serial (บน `tests/real_cases`) | ✅ ตรงกัน (golden `95852c68…`) |
| baseline `d6b23d12…` บน corpus 106 ไฟล์ | ⏸️ **รันไม่ได้ (ไม่มี corpus)** — ต้องรันบนเครื่องเจ้าของ |

**บั๊กที่แก้แล้ว (golden-safe, ทั้งหมด 6 — 1 commit/บั๊ก, gate ผ่านทุก commit):**

| # | ระดับ | บั๊ก | commit | ADR |
|---|------|------|--------|-----|
| Parse-S1 | 🔴 | `_dic_int_run` OverflowError ('inf'/'1e400') ทำบิลทั้งชีตหาย | `aecd960` | 038 |
| Master-S1 | 🔴 | `write_master_file` kill+ทับ backup → master จริงหายถาวร | `a383257` | 039 |
| Parse-M1 | 🟡 | `Decimal.quantize` InvalidOperation (ยอดมหึมา) ทำบิลหาย | `b42ce5b` | 038 |
| Parse-M3 | 🟡 | `_cell_to_num` ปล่อย ±inf หลุดไปคูณ Decimal | `b42ce5b` | 038 |
| Master-M1 | 🟡 | `save_master` เขียนไม่ atomic → master ครึ่ง/ว่าง | `c3f2d57` | 040 |
| Master-M2 | 🟡 | `save_master` `.bak` ถูก save ที่หดทับ | `c3f2d57` | 040 |

**บั๊กที่รายงานอย่างเดียว (golden-affecting / ต้อง rebaseline หรือเป็น advisory ที่เลือกไม่แตะ):** ดูข้อ 3–4

---

## 2) 🔴 ร้ายแรง

### Parse-S1 — `_dic_int_run` ครัช OverflowError → บิล "ทั้งชีต" หายเงียบ — **แก้แล้ว ✅**
- **Current risk:** เซลล์ข้อความ `'inf'/'-inf'/'1e400'/'Infinity'` ในคอลัมน์ใดก็ได้ทำ
  `int(float('inf'))` โยน `OverflowError` (except เดิมครอบแค่ ValueError/TypeError) → `detect_item_columns`
  ครัช → `parse_file` ดักระดับชีต → **ใบกำกับทุกใบในชีตนั้นถูกทิ้ง (SYS001) เงียบ ๆ**
- **Root cause:** `parser_p0a.py:_dic_int_run` except ไม่ครอบ OverflowError
- **Long-term impact:** ไฟล์ผู้ขายที่มี OCR/export เพี้ยน 1 เซลล์ → บิลทั้งชีตหายจากผลตรวจ
  โดยผู้ตรวจไม่รู้ → บัญชีขาดใบ
- **Solution (ทำแล้ว):** เพิ่ม `OverflowError` ใน except ; ค่าเหล่านี้ไม่ใช่ลำดับสินค้า 1..50 อยู่แล้ว
- **Migration risk:** ต่ำมาก (เส้น exception) — fixture oracle ไม่ขยับ
- **Priority:** สูงสุด — **Status: แก้แล้ว** (commit `aecd960`, ADR-038, ตรึง `test_bughunt_hardening.py`)

### Master-S1 — `write_master_file` ทำลาย master จริง + backup ถาวร — **แก้แล้ว ✅**
- **Current risk:** เครื่องมือ golden/verify เขียน stub ทับ `master_companies.json` ในโฟลเดอร์
  โปรเจกต์. เดิม `copy2` ทับ `.user.bak` ไม่มีเงื่อนไข + พึ่ง atexit (ไม่ทำงานบน SIGKILL) →
  รัน 2 รอบที่ถูก kill = **master จริงหายจากทั้ง live และ backup กู้ไม่ได้**
- **Root cause:** `golden_snapshot.py:write_master_file` (backup ไม่มีเงื่อนไข + เขียนไม่ atomic)
- **Long-term impact:** ทะเบียนบริษัทแม่ของผู้ใช้หายถาวร (data loss ระดับร้ายแรงสุดตามนิยามข้อ 4)
- **Solution (ทำแล้ว):** ห้ามทับ backup ที่มีอยู่/เมื่อ live เป็น stub + atomic write (temp+fsync+replace)
  + restore เฉพาะเมื่อ live เป็น stub
- **Migration risk:** ต่ำ (off-audit-path ; พฤติกรรม sandbox เดิมคงไว้)
- **Priority:** สูงสุด — **Status: แก้แล้ว** (commit `a383257`, ADR-039)

### Validators-S1 — leading-zero ยุบ ทำ "เลข IV ซ้ำ/ถอยหลัง" หลุดการตรวจ (FALSE NEGATIVE) — **รายงาน [ต้อง rebaseline]**
- **Current risk:** การ์ด "ฟอร์แมตเดียวกันถึงเทียบกันได้" วัดความยาวจาก **int** ที่ตัด 0 นำหน้าทิ้งแล้ว
  (`len(str(int(...)))`). เลขรันจริงของผู้ขายเดียวกันที่ข้ามหลัก 9→10 / 99→100 (เช่น `IV-009`, `IV-010`
  เป็น 3 ตัวอักษรเท่ากันจริง) ยุบเป็น int `9`,`10` → `{1,2}` → **ข้ามทั้งกลุ่ม** รวมทั้งใบที่ซ้ำ/ถอยหลังจริง
  - reproduce: ผู้ขายเดียว วันเดียว `IV-009,IV-009,IV-010` → **0 issue** (พลาดใบซ้ำ 009 จริง)
  - `_iv_check_ascending`: `IV010` (วัน1) + `IV009` (วัน2, เลขถอย) → **IV004 ไม่ฟ้อง**
- **Root cause:** `validators.py:143-144` (`_iv_check_sequence`) และ `validators.py:228` (`_iv_check_ascending`)
- **Long-term impact:** ผู้ขายที่ใช้เลขรันรีเซ็ตรายเดือน "ไม่ zero-pad" → ตรวจซ้ำ/ลำดับพลาดเงียบ
  (false negative บนของที่เป็นบัญชีจริง — ร้ายแรงที่สุดในเชิงผลตรวจ)
- **Solution (แนะนำ):** วัดความยาวจาก **raw string ของเลข** (ก่อน int) หรือเทียบด้วยเลขล้วน
  ไม่พึ่งความยาว int — แต่ **เปลี่ยน `iv_seq`/`b['issues']` ที่อยู่ใน golden hash**
- **Migration risk:** กลาง — **golden-affecting**: ต้อง (a) เขียน ADR (b) rebaseline บน corpus จริง
  (c) ตรวจ diff ผลตรวจทีละรายการ. fixture/real_cases ใช้เลข zero-pad คงที่ จึงไม่ trigger ที่นี่
- **Priority:** สูง (สำหรับเจ้าของระบบที่มี corpus) — **Status: รายงาน — ห้ามแก้ที่นี่ (ไม่มี corpus ให้ rebaseline)**

---

## 3) 🟡 กลาง

### Parse-M1 — `Decimal.quantize` InvalidOperation (ยอดมหึมา) → บิลหายทั้งชีต/ไฟล์ — **แก้แล้ว ✅**
- **Risk/Root:** subtotal/qty×price ≥ ~1e28 ทำ `quantize` โยน `InvalidOperation` ที่ 3 จุด derive-VAT
  (`parser_p2._pb_finalize_amounts` PATCH-5 ไม่ห่อ, PATCH-6 except แคบ, `parser_p0a` merge) → ครัชหลุด
  ถึง parse → บิลหาย
- **Solution (ทำแล้ว):** ครอบ/เพิ่ม `InvalidOperation` ทั้ง 3 จุด → degrade vat=None
- **Migration risk:** ต่ำ (ยอดจริงเล็กกว่ามาก ; 2500→vat 175.0 เท่าเดิม) — **Status: แก้แล้ว** (`b42ce5b`, ADR-038)

### Parse-M3 — `_cell_to_num` ปล่อย ±inf หลุด (`f!=f` จับแค่ NaN) — **แก้แล้ว ✅**
- **Risk/Root:** `inf == inf` → inf ผ่าน → `_D(inf)*Decimal` ระเบิดปลายน้ำ. ปัจจุบันไม่ reachable จาก
  ไฟล์ Excel ที่ save (latent/defensive)
- **Solution (ทำแล้ว):** ใช้ `math.isfinite` กัน NaN+±inf จุดเดียว — **Status: แก้แล้ว** (`b42ce5b`, ADR-038)

### Master-M1 / M2 — `save_master` เขียนไม่ atomic + `.bak` ถูก save ที่หดทับ — **แก้แล้ว ✅**
- **Risk/Root:** truncate-then-write → kill = master ครึ่ง/ว่าง → `load_master` คืน None เงียบ (ตรวจต่อโดยไม่มี
  master) ; `.bak` generation เดียวถูก save ที่หดทับ → บริษัทหาย
- **Solution (ทำแล้ว):** atomic (temp+fsync+replace) + `.bak` refresh เฉพาะเมื่อ live ครบ ≥ `.bak`
- **Migration risk:** ต่ำ (off-audit-path ; `test_fix_round2` ผ่าน) — **Status: แก้แล้ว** (`c3f2d57`, ADR-040)

### Validators-M1 — `r_dt003` ตีกรอบปีผิด (พ.ศ. บน iv_date ที่เป็น ค.ศ.แล้ว) + ขัด `r_dt004` — **รายงาน**
- `parse_date_any` normalize `iv_date` เป็น **ค.ศ.** เสมอ แต่ `r_dt003` (`rules_engine_rules_a.py:494-517`)
  ยังคิดแบบ พ.ศ.: branch `elif 2500<=yr<=2600` **dead** สำหรับ ค.ศ. จริง และ `current_year_be = year+543`
  เทียบกับ `yr` ค.ศ. → ฟ้อง "ปี ค.ศ./พ.ศ.?" ผิดบนปี ค.ศ. 2031-2034 และขัดกับ `r_dt004` (rules_c) ที่ถูกต้อง
- **golden-safe** (corpus 2023-2026 ไม่แตะช่วงนั้น) แต่ logic เพี้ยน/ซ้ำซ้อน
- **Solution:** ยุบให้ `r_dt004` เป็นกฎเดียว หรือแก้ frame ของ `r_dt003` — **Status: รายงาน** (แตะ logic วันที่
  โดยไม่มี corpus ยืนยัน = เสี่ยง ; ให้เจ้าของระบบแก้พร้อม rebaseline ถ้าตั้งใจ)

### Validators-M2 — `r_vat004` (VAT004 "ปัดเศษ") เป็น dead code ฟ้องไม่ได้เลย — **รายงาน [ต้อง rebaseline ถ้าจะเปิด]**
- `rules_engine_rules_b.py:367-383`: `round(fv,2)` → format `:.2f` → `rstrip('0')` → `len(dec_str) > 2`
  **เป็นไปไม่ได้เชิงโครงสร้าง** (เศษมีได้ ≤2 หลัก) → กฎไม่เคย emit. คอมเมนต์ v5.8q ใส่ `round()` กัน FP
  แต่ฆ่ากฎทั้งตัว
- **golden-safe ตอนนี้** (กฎไม่ emit = ไม่เข้ารายงาน/hash) แต่เป็นกฎ "active" ที่จริง ๆ no-op:
  ยอดที่มีทศนิยม >2 ตำแหน่งไม่เคยถูกจับ
- **Solution:** ตรวจทศนิยมจาก **ค่าดิบก่อน round** — แต่ทำให้กฎเริ่ม emit = **golden-affecting** →
  **Status: รายงาน [ต้อง rebaseline]**

### Validators-M3 — "IV ถอยหลังในวันเดียวกัน" ขึ้นกับลำดับแถว ไม่ใช่ค่าเลข — **รายงาน**
- `validators.py:160-169`: สแกน group ตามลำดับแถวชีต (ไม่ sort ตาม seq) แล้ว flag `s<prev` →
  `[5,3]`→flag, `[3,5]`→ไม่ flag. นิยาม "ถอยหลังในวันเดียว" คลุมเครือเมื่อใบในวันเดียวไม่มีลำดับ canonical
- **golden-safe** (deterministic ต่อ input ที่ตรึง) แต่ semantic ไม่ชัด — **Status: รายงาน**

### Validators-M4 — `compute_bill_confidence` เช็ค checksum บน tax_id ที่ยังไม่ clean (ต่างจาก `r_tax006`) — **รายงาน**
- `analytics.py:81-87` ใช้ `tid` ดิบ (มี `-`/ช่องว่าง) → `_taxid_checksum_ok` คืน True ให้ทุกค่าที่ไม่ใช่ 13
  หลักล้วน → เลขที่มีตัวคั่นเลี่ยง penalty ; ขณะที่ `r_tax006` clean ก่อน → ปฏิบัติต่างกันข้ามโมดูล
- **golden-affecting ถ้า tax_id ใน corpus มีตัวคั่น** (`parse_confidence` อยู่ใน hash) → **Status: รายงาน [ต้อง rebaseline]**

### Parse-M2 — `parse_date_any` มองไม่เห็นวันที่ตัวเลขที่มี label นำ ("วันที่ 05/05/2569") — **รายงาน [ต้อง rebaseline]**
- `puopuy_dates.py:54,66-71` ใช้ regex anchored ต้นสตริง/`s[:10]` → เห็นเฉพาะวันที่ที่อยู่ต้นเซลล์
  (`'วันที่ 05/05/2569'`→None, `'05/05/2569'`→OK). สาขาเดือนไทยใช้ unanchored จึงรอด
- **golden-safe ตอนนี้** (real_cases เก็บวันที่เป็น datetime จริง) แต่เป็นช่องโหว่ความทนทานจริง
  สำหรับใบที่เก็บวันที่เป็นข้อความมี label → แก้แล้ว parse เปลี่ยน = **golden-affecting** → **Status: รายงาน**

### Parse-M4 — ชีต < 5 แถวถูกข้ามเงียบ ไม่มี SYS warning — **รายงาน**
- `parser_p2.py:560` `if df.empty or df.shape[0]<5: continue` รันก่อน SYS003 check → บิลกะทัดรัด (≤4 แถว)
  หายโดยไม่มี log. **golden-safe** (corpus บิลใหญ่กว่า) แต่เป็น silent skip
- **Solution (แนะนำ, golden-safe):** ยิง SYS003 เมื่อชีตชื่อ "เหมือนบิล" ถูกข้ามด้วยเหตุแถวน้อย
  (เป็น observability ล้วน ไม่กระทบ hash) — **Status: รายงาน** (เลือกไม่แตะรอบนี้เพื่อคุมสโคป)

### Agents-M1 / M2 — bare `except: pass` กลืน error เงียบในชั้นรายงาน (FULL mode / vendor report) — **รายงาน**
- `report_agent.py:67-73` (addon-pack FULL mode) และ `super_ultra_viewer.py:284-285` (company unit notes)
  จับ `Exception` กว้างแล้ว `pass` → ถ้าพังกลางคัน เนื้อหารายงานบางส่วนหายเงียบ (false-negative เชิงรายงาน
  ไม่ใช่เชิงผลตรวจ — Excel/golden หลักไม่กระทบ เพราะ golden ใช้ lean mode)
- **Solution (แนะนำ, golden-safe):** แคบชนิด exception + log SYS — **Status: รายงาน** (report layer ถูกล็อกด้วยเทส
  จึงเลือกไม่แตะรอบนี้)

---

## 4) 🟢 ต่ำ

| # | จุด | อาการ | Status |
|---|-----|------|--------|
| Parse-L1 | `parser_p1.py:57-58` | `return vat_rows` ซ้ำ บรรทัด 58 unreachable (dead) | รายงาน (cosmetic) |
| Parse-L2 | `core_utils.py:108` | `iv_amount_fragment` ใช้ `repr(float)` → เลข ≥1e16 เป็น sci-notation เพี้ยน (false-neg, ไม่ corrupt) | รายงาน |
| Parse-L3 | `parser_p0a.py:155,167` | `parse_filename` ปีเพี้ยนสำหรับเลขนำที่ไม่ใช่ปี (by-design, no-op ปลายน้ำ) | รายงาน |
| Val-L1 | `validators.py:290-291` | `last_num` 4-7 หลักใช้ทั้งเลข, 8+ ใช้ 4 ตัวท้าย (heuristic ไม่สม่ำเสมอ) | รายงาน |
| Val-L2 | `validators.py:105-108` | ชีตชื่อ "100" ถูกตีเป็นวันที่ 100 (ขึ้นกับ convention ชื่อชีต) | รายงาน |
| Val-L3 | `validators.py:428-455` | `check_product_typos` 2 เส้นที่ขอบ 500 ชื่อ ให้ผลต่างได้ (golden-affecting ถ้าคร่อม 500 พอดี) | รายงาน |
| Agents-L1 | `super_ultra_viewer.py:391-393` | float format ไม่สม่ำเสมอ (`5,990,004` vs `…004.00`) — report only | รายงาน |
| Agents-L2 | `super_ultra_viewer.py:164` | `.most_common(1)[0][0]` จะ IndexError บน group ว่าง (ปัจจุบัน unreachable) | รายงาน |
| Agents-L3 | reporting*.py | `datetime.now()` ในข้อความรายงาน → ข้อความต่างต่อรอบ (ตั้งใจ, ไม่อยู่ใน golden) | รายงาน (by-design) |
| Maint-L1 | `parser_p2.py` | อยู่ที่เพดาน 600 LOC พอดี ไม่มี headroom → ควรพิจารณาซอยในอนาคต | รายงาน |

---

## 5) Tier ที่ตรวจแล้ว "สะอาด" (พร้อมหลักฐาน — ไม่แต่งบั๊ก)

- **offline/network:** `offline_guard.py` เป็น single-source ; `webverify`/`llm_provider` คืน None/NullProvider
  ก่อนสร้าง request เว้นตั้งใจเปิด `PUOPUY_ALLOW_NETWORK=1`. `test_offline_audit.py` ดัก urlopen/socket = 0 calls.
  **ไม่มี outbound บนเส้น audit** ✅
- **file_guard:** คุมขนาดไฟล์/zip-bomb/อัตราขยาย/จำนวน entry, fail-open ปลอดภัย — ไฟล์ขยะ/ใหญ่ไม่ครัช batch ✅
- **hashseed/parallel:** `parallel_audit` fail-hard ถ้าไม่ได้ตั้ง `PYTHONHASHSEED=0` (เช็ค `sys.flags`),
  pin fork, merge ตามลำดับ chunk ด้วย key จริง. **parallel == serial** ยืนยันบน real_cases ✅
- **reset_run_state:** ล้าง state.py caches ครบ (พิสูจน์ 2 รอบในโปรเซสเดียว ผลเท่ากัน — `test_reset_completeness`) ✅
- **engine == agent (mesh ไม่เปลี่ยนผลตรวจ):** golden hash คำนวณจาก engine output ล้วน
  (`golden_snapshot.build_snapshot`) ; agent layer read-only ไม่ mutate bills. agent_hash นิ่งข้ามรอบ ✅
- **VAT tolerance math / `_ivp_year2/4_to_ce` / DOC001 dual-source:** ตรวจแล้วถูกต้อง (Decimal+HALF_UP,
  ช่วงกำกวม 40-57 คืน None โดยตั้งใจ, dedup exact-dict) ✅

---

## 6) สิ่งที่ "ไม่ได้ทำ" โดยตั้งใจ (ตามกฎ)
- ❌ ไม่แก้บั๊ก golden-affecting (Validators-S1/M2/M4, Parse-M2 ฯลฯ) เพราะ rebaseline ต้องใช้ corpus จริง
  ที่ไม่มีในกล่องนี้ — แก้แล้วเดา hash เอง = ผิด protocol
- ❌ ไม่แตะ report format ที่ล็อกด้วยเทส / business logic ที่ corpus พิสูจน์แล้ว
- ❌ ไม่เพิ่มฟีเจอร์ใด ๆ
- ✅ ทุก commit ผ่าน fixture oracle (`269ddaed…`) + 76 เทส + CI 78 ด่าน
