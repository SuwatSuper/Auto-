# รายงานรีรีเช็คบั๊กทั้งระบบ — pukpui v9.3.4 (รายแรง / กลาง / ต่ำ)

วันที่: 2026-06-21 · ขอบเขต: ทั้งระบบ (parser / rules / validators / reporting / agents+concurrency / core)
วิธีตรวจ: รีวิวอิสระ + 5 ผู้ล่าบั๊กขนาน (1 subsystem/ตัว) — **ทุกบั๊กยืนยันด้วยการรันจริง (reproduce)** ไม่เชื่อคอมเมนต์/เอกสารเดิม

> **สภาพแวดล้อมที่รีเช็ค**: Python 3.11 / numpy 2.2.6 (ระบบล็อก 3.12 / numpy 2.2). version_gate เตือนถูกต้อง
> และ **ผ่อนผันด้วย `PUOPUY_ALLOW_VERSION_MISMATCH=1`**. แม้คนละ minor — fixture hash ตรง `b5c415bb…` เป๊ะ
> และ real_cases digest ตรง `95852c68…` เป๊ะ จึงใช้เป็น oracle ก่อน/หลังแก้ได้จริง.

---

## 0) สรุปผู้บริหาร (สิ่งสำคัญที่สุด)

**ข่าวดี: ไม่พบบั๊ก "รายแรง (HIGH)" ที่ยังมีชีวิตและเข้าถึงได้จากข้อมูลจริง.** บั๊ก HIGH/MED ทุกตัวจากรายงานเก่า
3 ฉบับ (`BUGHUNT_RECHECK`, `BUGFIX_FULL_AUDIT_20260620`, `FIXES_RECHECK`) ถูก reproduce ซ้ำแล้ว **แก้จริงทุกตัว**
(IV ซ้ำข้ามหลัก, `_money_q('1e30')→None`, superscript `²`, 29 ก.พ. พ.ศ., nan/inf, bool-as-int, KeyError hardening,
crash-hardening รายงาน ฯลฯ). 4 ใน 5 subsystem **สะอาด** (rules / validators-core / agents-concurrency / reporting-engine).

สิ่งที่เจอใหม่ทั้งหมดอยู่ระดับ **กลาง/ต่ำ** และส่วนใหญ่เป็น edge-case / unreachable. ผมแก้ **เฉพาะตัวที่ golden-neutral
พิสูจน์ได้** (digest ไม่ขยับ + เทสต์ไม่ตก + ไม่สร้าง false-positive ใหม่) และ **รายงานตัวที่เสี่ยงต่อความนิ่ง 5 ปี
ให้เจ้าของตัดสิน** แทนการแตะเงียบ ๆ (ตามกฎเหล็กข้อ 3: business logic = เจ้าของตัดสิน).

### หลักฐาน golden-neutral (ก่อน vs หลังแก้)
| oracle | ก่อนแก้ | หลังแก้ | ผล |
|---|---|---|---|
| real_cases digest (15 บิล/3 ไฟล์) | `95852c68…` | `95852c68…` | ✅ ไม่ขยับ |
| fixture hash (engine==agent==baseline) | `b5c415bb…` | `b5c415bb…` | ✅ ไม่ขยับ |
| parallel == serial | ✅ | ✅ | ✅ ตรงเป๊ะ |
| determinism (seed 0/1/7/42/99) | ✅ | ✅ | digest เท่ากันทุก seed |
| เทสต์ standalone | 81 ผ่าน / 2 ตก* | **83 ผ่าน / 1 ตก*** | +new pin test, ไม่มี regression |
| e2e `main.py` บน real_cases | EXIT 0 | EXIT 0 | รายงานครบทุกไฟล์ |

\* ตก = เทสต์กำพร้านอก CI `test_cmp004_notepad_visibility` (ดู §3, เป็นการตัดสินใจเชิงนโยบาย) ;
   `test_package_integrity` ที่เคยตก (รันจาก zip) ตอนนี้ **ผ่าน** แล้วเพราะ commit เข้า git repo.

---

## 🔴 รายแรง (HIGH) — เข้าถึงได้จากข้อมูลจริง + กระทบผลตรวจ

**ไม่พบ.** (ทุกตัวที่เคยเป็น HIGH ถูกปิดในรอบก่อน ๆ และผม reproduce ยืนยันว่าแก้จริง)

---

## 🟡 กลาง (MEDIUM)

### M-1 [แก้แล้ว ✅] แถวสรุป/ยอดรวม/ภาษี ถูกนับเป็น "รายการสินค้า" + ฟ้อง ITM016 หลอก  — `parser_p2.py`
- **อาการ (reproduce):** แถวที่ลำดับว่าง แต่ชื่ออยู่คอลัมน์ชื่อเป็น label เช่น `"รวมเป็นเงิน"`, `"จำนวนเงินรวมทั้งสิ้น"`
  + มียอดใน amt_col → ถูก append เป็นรายการสินค้า + ฟ้อง `ITM016` (เลขลำดับหาย) ทุกแถวสรุป
  (เดิมกันแค่ "ยอดเงินเป็นตัวอักษรไทย" ไม่กัน label ยอดรวม).
- **แก้ (golden-neutral):** ในสาขา blank-seq เพิ่มเงื่อนไข `continue` เมื่อชื่อ (lowercase, lstrip) **ขึ้นต้นด้วย**
  label ใน `_LBL_TOTAL + _LBL_SUBTOTAL + _LBL_VAT`. ใช้ `startswith` (ไม่ใช่ substring) เพื่อกันชื่อสินค้าจริง
  ที่บังเอิญมี label เป็นคำย่อยถูกตัดทิ้ง (กัน false-negative). **พิสูจน์:** รายการจริงที่ลืมเลขลำดับ ('ลวดผูกเหล็ก')
  ยังถูกจับ + ยัง ITM016 ; real_cases digest ไม่ขยับ. (pin: `test_recheck_20260621.py`)

### M-2 [รายงาน — ขอเจ้าของรัน regression เต็มก่อน ⚠️] เลขในเซลล์รายการที่มีค่า `0.07` ถูกตีเป็น "แถว VAT" → บิลถูกหั่นเป็น 2 — `parser_p1.py:44` (`_detect_vat_rows`)
- **อาการ (reproduce):** สาขา bare-numeric `abs(float(v)-0.07)<0.001` ไม่มี row-context guard (ต่างจาก marker `'7'/'7.00'`).
  รายการที่ราคา/หน่วย/จำนวน = `0.07` เป๊ะ ถูกนับเป็น vat_row. ถ้าแถวนี้อยู่ร่วมกับ "แถวอัตรา VAT 0.07 จริง"
  (มี ≥2 vat_rows) → `parse_sheet` หั่นบล็อก → **1 บิลกลายเป็น 2** (นับบิลซ้ำ/รายการหาย/subtotal เพี้ยน).
- **ทำไมยังไม่แก้เอง:** เส้นนี้คือ **"การมีอยู่ของบิล" (block splitting)** — จุดที่ golden-sensitive ที่สุด
  (ระบบเคย revert การ optimize ที่ทำบิลร่วง 836→52). คอมเมนต์ระบุ "VAT จริง 684 เซลล์มาทางนี้" — fix ที่ผิดนิด
  เดียวกระทบทุกบิล. real_cases (15 บิล) ไม่มี trigger (0 sheet ที่มี >1 vat-row) จึง **พิสูจน์ neutral บนชุดที่รันได้ไม่พอ**
  สำหรับคอร์ปัสจริง 148 ไฟล์. **เสี่ยงทำระบบเพี้ยนบนข้อมูลที่ผมรันไม่ได้** → ขัดเป้าหมาย "ห้ามเพี้ยน 5 ปี".
- **แนวทางแก้ที่เสนอ (ให้เจ้าของรัน + regression):** ตี `0.07` เป็น VAT เฉพาะเมื่อแถวนั้น **ไม่ใช่แถวรายการสมบูรณ์**
  (มีเลขลำดับ 1-50 + ชื่อสินค้า + ราคา) — แถว VAT-rate จริงไม่เคยมีเลขลำดับสินค้า. หลังแก้ **ต้องรัน
  `PYTHONHASHSEED=0 python3 regression_full.py . <148 ไฟล์จริง>` เทียบ `baseline.json._sha256` (ae84d3f0…)** ;
  ถ้า hash เปลี่ยน = ดู diff ว่าใช่การหั่นบิลผิดที่หายไปเท่านั้นไหม แล้วค่อย rebaseline อย่างตั้งใจ.

### M-3 [รายงาน — การตัดสินใจเชิงนโยบาย 📋] รายงาน `.txt` แสดงช่อง 'ชื่อบจ.' เป็นคำว่า "ตรง" ทั้งที่ CMP004 ฟ้อง — `super_ultra_viewer.py:406`
- **อาการ:** เมื่อชื่อบริษัทในบิลตรง master แต่ "เว้นวรรคเกิน" → `CMP004` ฟ้อง (ERROR) และ **.xlsx + vendor_report.txt
  แสดง "ไม่ตรง" ถูกต้อง** แต่ `company_summary.txt` (Precision Council tier=soft) แสดงช่องเป็นคำว่า **"ตรง"**
  แล้วย้ายไปบรรทัด "ตรวจตาเพิ่ม" แทน. (นี่คืออาการที่ `test_cmp004_notepad_visibility.py` กำพร้าจับได้)
- **ทำไมยังไม่แก้เอง:** เป็น **นโยบาย Precision Council ที่ตั้งใจออกแบบ** และมีเทสต์ใน CI ที่ใช้งานอยู่ (`test_report_c1_c2.py`
  ขั้น `[3w0b]`) **ยืนยันว่า soft-tier ขึ้น "ตรง" ในช่องเป็นเรื่องถูก**. การ "แก้" จะ **ขัดเทสต์ CI ที่ active**
  = เปลี่ยนพฤติกรรมระบบ. ตามกฎเหล็กข้อ 3 (display/business policy = เจ้าของตัดสิน) → **ขอให้เจ้าของเลือก** (ดู §3).

---

## 🟢 ต่ำ (LOW)

| # | สถานะ | ไฟล์ | สรุป |
|---|---|---|---|
| L-1 | **แก้แล้ว ✅** | `validators.py` (`apply_sheet_date_crosscheck`) | **V-F3**: ชื่อชีตที่ไม่ใช่ "วัน.เดือน" จริง (`5.2025`=วัน.ปี→เดือน 20, `5.13`, `0.5`) ฟ้อง DOC001 หลอก. เพิ่ม guard `1≤วัน≤31 และ 1≤เดือน≤12` ; "5.6" จริงยังฟ้องปกติ. (pin: `test_recheck_20260621.py`) |
| L-2 | **แก้แล้ว ✅** | `puopuy_units.py:71` | **C-LOW**: คอมเมนต์ `_D` เคลม "กัน 1e999" ทั้งที่ `is_finite()` ไม่กัน (1e999 finite). แก้คอมเมนต์ให้ตรงจริง (ค่ามหึมา-finite ถูกกันที่ `_money_q`/quantize). พฤติกรรมไม่เปลี่ยน (downstream ปลอดภัยอยู่แล้ว). |
| L-3 | รายงาน (คงไว้) | `rules_engine_rules_a.py:561` / `rules_c:407,416` | **R-LOW1**: `r_itm001/018` ข้ามเช็กเลขคณิตเมื่อ `price==0` (truthiness gate). **ไม่แก้:** การ "ยิง" เคส price=0/amount≠0 เสี่ยงสร้าง false-positive ใหม่กับบรรทัดของแถม/ส่วนลด (ราคา 0 ถูกต้อง) — ขัดปรัชญา false-neg > false-pos. |
| L-4 | รายงาน (คงไว้) | `rules_engine_rules_c.py:358` | **R-LOW2**: `r_itm016` ฟ้อง "รายการซ้ำ" กับสินค้าเดิมคนละจำนวน (key=name,unit,price ไม่รวม qty). **ไม่แก้:** เป็น review-lane (เตือนคนดู) — รัด key เสี่ยง miss ของซ้ำจริง (false-neg แย่กว่า). |
| L-5 | รายงาน (เสี่ยง) | `validators.py:343` | **V-F2**: `detect_iv_period_mismatch` ฟ้อง DT004 หลอกกับเลขรันล้วน ≥5 หลักที่บังเอิญขึ้นต้นเป็น YYMM. ทุก period-IV จริงในคอร์ปัส match อยู่แล้ว → fix ต้องรัน regression DT004 (live rule) ก่อน. |
| L-6 | รายงาน (คงไว้) | `validators.py:612` | **V-F4**: `check_duplicate_items` พลาดของซ้ำเมื่อ amount เป็น NaN (`nan!=nan` เป็น key). **unreachable** (parser ไม่ผลิต NaN) → false-negative ล้วน, คงไว้. |
| L-7 | รายงาน (เสี่ยง) | `parser_p1.py:95` / `parser_p0.py` twin | **P-LOW3**: `PRODUCT`/`SUBTOTAL` ใน ANTI_PREFIX เป็น dead code (prefix >5 ตัวไม่เคย match). กระทบ IV selection (golden-sensitive) — แก้แบบ text-context เท่านั้น + ต้อง regression. value ต่ำ. |
| L-8..11 | รายงาน (คงไว้) | `agents/super_agent.py:211`, `notepad_agent.py`, `llm_provider.py`, `offline_guard.py` | LOW/defensive ของชั้น agent: evidence=None (unreachable), advisory `.txt` เขียนไม่ atomic + ชื่อคงที่ทับของเก่า (ไม่กระทบ engine), egress_allowed ขาด "on" (เข้มกว่า ไม่รั่ว), network_allowed case-sensitive (fail-safe). ไม่มีตัวไหน reachable เป็น failure จริง. |

---

## 1) สิ่งที่ "แก้แล้ว" รอบนี้ (golden-neutral พิสูจน์ครบ)

1. **M-1** `parser_p2.py` — กันแถวสรุป/ยอดรวม/ภาษี เป็นรายการสินค้า + ITM016 หลอก (startswith label, conservative)
2. **L-1 (V-F3)** `validators.py` — DOC001 sanity ชื่อชีต `1≤วัน≤31 / 1≤เดือน≤12`
3. **L-2 (C-LOW)** `puopuy_units.py` — แก้คอมเมนต์ `_D` ให้ตรงความจริง (ไม่เปลี่ยนพฤติกรรม)
4. **เพิ่ม pin test** `test_recheck_20260621.py` (10 เคส) + เสียบเข้า `run_ci.sh` ขั้น `[3x14d]` (กันถอยหลัง)

> ทุกข้อ: real_cases `95852c68…` + fixture `b5c415bb…` ไม่ขยับ, parallel==serial, เทสต์ไม่ตกเพิ่ม, ไม่สร้าง false-positive ใหม่.

## 2) ขั้นตอนที่เจ้าของต้องทำเพื่อ "ปิดจบ" บนคอร์ปัสจริง

แม้ผมพิสูจน์ neutral บน real_cases + fixture แล้ว แต่ baseline ทางการทำบน **148 ไฟล์ (`/mnt/project`, Python 3.12/numpy 2.2.6)**
ที่ผมเข้าไม่ถึง. กรุณายืนยันด้วย:
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02
pip install -r requirements.txt -c constraints.txt     # Python 3.12 + numpy 2.2.6 เป๊ะ
python3 regression_full.py . /mnt/project              # ต้องได้ engine==agent==baseline = ae84d3f0…
bash run_ci.sh /mnt/project                            # ด่านครบ + ขั้น [3x14d] ใหม่
```
ถ้า `ae84d3f0…` ยังตรง = การแก้ทั้ง 3 ข้อ neutral บนคอร์ปัสจริง 100% → **ปิดจบ** ได้เลย.
(คาดว่าตรง เพราะ M-1/L-1 ออกแบบให้ยิงเฉพาะ edge ที่ข้อมูลสะอาดไม่มี.)

## 3) การตัดสินใจที่ขอจากเจ้าของ (M-3 / CMP004)
- **ตัวเลือก A (คงตามดีไซน์ปัจจุบัน):** `.txt` ขึ้น "ตรง" สำหรับ soft-tier (ตามที่ `test_report_c1_c2` ยืนยัน) — ไม่ทำอะไร.
- **ตัวเลือก B (เข้มเรื่องความซื่อตรง):** soft-tier ที่มี CMP004 ไม่ขึ้นคำว่า "ตรง" แต่ขึ้น "– ก้ำกึ่ง (ดูตรวจตาเพิ่ม)"
  → ต้องอัป `test_report_c1_c2.py` ให้สอดคล้อง (เปลี่ยนนโยบายการแสดงผล, advisory เท่านั้น — golden hash ไม่ขยับ).

> M-2 (0.07 split): แนะนำทำหลัง M-3 และ **ต้องมากับ regression 148 ไฟล์เสมอ** เพราะกระทบการมีอยู่ของบิล.
