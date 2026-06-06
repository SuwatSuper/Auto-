# สถานะการกู้ระบบ ปุ้มปุ้ย v9 (REBUILD STATUS)

อัปเดต: 2026-06 · โดย Production Reliability rebuild pass (สามพาส: แก้ไข→เสริม→รีเช็ค→เสริม→เทส→แก้ไข→เพิ่ม→เสริม→เทส→ส่งมอบ)

---

## 0. สรุปผู้บริหาร (อ่าน 30 วินาที)

แพ็กเกจที่ส่งมอบเดิม **รันไม่ได้แม้แต่บรรทัดเดียว** เพราะมีโมดูลหลักหาย/ว่างเปล่า. รอบนี้ **กู้ให้กลับมารันได้จริงและผ่านการทดสอบครบ** บนข้อมูลจริง 81 ไฟล์ (632 บิล).

| การทดสอบ | ผล |
|---|---|
| ตัวเลขผลตรวจทั้งหมด เทียบ baseline ที่บันทึกไว้ในเอกสาร | **ตรงเป๊ะทุกตัว** (632/81/3/1/26/0/34/2) |
| เส้น engine == เส้น agent (ชั้น agent ไม่เปลี่ยนผลตรวจ) | **✅ hash ตรงกัน** (`ec61907f…`) |
| `regression_full.py` (engine+agent+baseline) | **✅ ผ่านทั้งหมด** |
| `test_agents.py` (สัญญาสถาปัตยกรรม) | **✅ 38/38** |
| `smoke_test.py` (ความครบของแพ็กเกจ) | **✅ 26/26** |

> ⚠️ **ความซื่อสัตย์เรื่อง hash:** ต้นฉบับของ 2 โมดูลที่หายนั้น **สูญหายถาวร** (ไม่มีใน ZIP / ไม่มี `.pyc` / ไม่มีสำเนาในโค้ด) จึง **กู้ค่า byte-identical ของเดิม (`7b60b01f…`) ไม่ได้**. ทุกส่วนที่กู้ทำขึ้นจาก "หลักฐานที่ยังเหลือ" และ **ตัวเลขผลตรวจที่ตรวจสอบได้จากภายนอกตรงกับต้นฉบับทุกตัว**. ความต่างของ hash มาจาก field ที่ reconstruct (รายละเอียดข้อ 3).

---

## 1. สิ่งที่พัง (Root cause)

| # | ไฟล์ | อาการจริง | ผลกระทบ |
|---|---|---|---|
| F1 | `puopuy_units.py` | **หายทั้งไฟล์** — ถูก import ที่ parser.py, rules_engine.py, โมดูลหลัก | `ModuleNotFoundError` ตั้งแต่ import → ทั้งระบบล่ม |
| F2 | `analytics.py` | **ถูกส่งมาเป็นไฟล์ว่าง 0 ไบต์** | `from analytics import *` ได้ของว่างเงียบๆ → ฟังก์ชันหายเงียบ → พังตอนรัน |
| (เพิ่ม) | `build_unit_index` | หายไปพร้อม analytics — โมดูลหลักเรียกใน `run_all_rules` | `NameError` กลางการรันกฎ |
| (เพิ่ม) | `addon_check_withholding` | หายไปพร้อม analytics — `wht_agent` ห่อไว้ | WhtAgent = `skipped` (ตรวจ ภงด.53 ไม่ทำงาน) |
| F3 | `verify_golden.py`, `regression_full.py`, `baseline.json` | **หายทั้งหมด** (เอกสารอ้างถึงแต่ไม่มีในแพ็กเกจ) | พิสูจน์ "ผลเหมือนเดิม" ไม่ได้เลย |

---

## 2. สิ่งที่กู้/สร้างใหม่ และความซื่อตรงต่อต้นฉบับ

ทุกจุดในโค้ดติดป้ายไว้ว่า `FAITHFUL` (อิงข้อมูลต้นฉบับที่ยังรอด) หรือ `⚠ APPROX` (ต้นฉบับไม่ทราบค่า — สร้างใหม่แบบโปร่งใส ปรับได้).

### 2.1 `puopuy_units.py` (สร้างใหม่ทั้งไฟล์)

| สัญลักษณ์ | ระดับ | ที่มา |
|---|---|---|
| `_D` | **FAITHFUL** | contract มาตรฐานจาก call sites (None/ว่าง/comma/฿ → Decimal หรือ None) |
| `_unit_canon` | **FAITHFUL** | กลุ่มหน่วยพ้องความหมาย **คัดลอกจาก `rules_engine.r_itm005`** (ข้อมูลต้นฉบับที่ยังรอด) |
| `extract_unit_hint` | **FAITHFUL** | ใช้ regex จริงจาก **`config.UNIT_HINT_PATTERNS`** (ข้อมูลต้นฉบับ) |
| `_vat_tolerance` | **✓ RESTORED** | [OBJ-1A 2026-06] คืนสู่สูตรเดิมที่มีหลักฐาน `0.5 + |subtotal|/100000` (เลิกใช้ค่า reconstructed `max(1.00, 0.5%·subtotal)` ที่หลวมเกินไป) — ดู §2.1.1 |

#### 2.1.1 บันทึกการเปลี่ยน `_vat_tolerance` (OBJ-1A · การเปลี่ยน business logic อย่างตั้งใจ)

| หัวข้อ | รายละเอียด |
|---|---|
| **ค่าเก่า** (reconstructed/APPROX) | `max(1.00, 0.005·|subtotal|)` — เดาขึ้นใหม่ตอนนึกว่าต้นฉบับหาย |
| **ค่าใหม่** (restored/documented) | `0.5 + |subtotal|/100000` — สูตรเดิมที่มีหลักฐานว่าพิสูจน์แล้ว |
| **เหตุผล** | สูตรเก่าหลวมกว่า 83–484 เท่า (ยิ่งบิลใหญ่ยิ่งหลวม) = false-negative landmine สำหรับงาน audit. บิลยอด 1.53M สูตรเก่าปล่อยส่วนต่างได้ถึง 7,651 บาทโดยไม่ฟ้อง VAT001, สูตรใหม่ปล่อยแค่ 15.80 บาท |
| **หลักฐาน (พิสูจน์เชิงประจักษ์)** | ข้อมูลจริง 81 ไฟล์ / 631 บิลที่เข้าเกณฑ์: ทุกบิลกระทบยอดตรงระดับ ≤ 1e-10 → VAT001 ฟ้อง 0 ใบ **ทั้งสองสูตร** → **golden hash ไม่ขยับ (ยังเป็น `ec61907f…`)** → ไม่ต้อง regenerate baseline |
| **การตรึง** | `test_pinned_logic.py` §[1] ฝังค่าจริงของสูตรใหม่เป็น literal — แก้สูตรเงียบ ๆ ภายหลัง = เทสล้ม |
| **ขอบเขตผลกระทบ** | เปลี่ยนแค่ (ก) `r_vat001` (ฟ้อง 0 ทั้งคู่บนข้อมูลนี้) และ (ข) `formula_agent` (advisory, ไม่เข้า hash) |

### 2.2 `analytics.py` (สร้างใหม่ทั้งไฟล์ — เดิม 0 ไบต์)

| สัญลักษณ์ | ระดับ | ที่มา / การตัดสินใจ |
|---|---|---|
| `summarize_by_company` | **FAITHFUL** | **พิสูจน์เชิงประจักษ์**: baseline เดิม `companies=2` → จัดกลุ่มด้วย `master_key` ล้วน (matched + บัคเก็ต "ไม่พบใน master") = 2 พอดี. (ลองแบบ company×period ได้ 21/46 = ไม่ตรง → ตัดทิ้ง) |
| `compute_bill_confidence` | contract **FAITHFUL** / น้ำหนัก **⚠ APPROX** | เขียน `parse_confidence` ('HIGH'/'MID'/'LOW') + `parse_confidence_reasons` ตามที่ `reporting.py` อ่าน; ใช้ `CONF_TIERS` จริง. โมเดลหักคะแนนเป็นแบบโปร่งใส (ต้นฉบับไม่ทราบสูตร) |
| `confidence_tier` | **FAITHFUL** | map ด้วย `CONF_TIERS` จริงจาก config |
| `build_unit_index` | **FAITHFUL** | contract จาก `rules_engine.r_itm015` (name→set(units)) |
| `addon_check_withholding` | contract **FAITHFUL** | ใช้ `ADDON_CFG` จริง (rate 3%, threshold 1000, service keywords); เป็น advisory อ่านบิลอย่างเดียว → **ไม่กระทบ golden hash** |
| full-mode: `load_audit_excel`, `cluster_products`, `detect_price_outliers`, `detect_unit_anomalies`, `build_dashboard_figs` | **RECONSTRUCTED (SIMPLIFIED)** | ใช้เฉพาะโหมด `--full` (ออปชัน, ต้องมี plotly). รักษา contract คอลัมน์/คืนค่าครบ + degrade ถ้าไม่มี plotly. **ไม่กระทบเส้นทาง clean/core เลย** |

---

## 3. ทำไม hash ใหม่ (`ec61907f…`) ≠ hash เดิม (`7b60b01f…`)

ตัวเลขผลตรวจ **ตรงทุกตัว** แต่ hash ของ snapshot เต็มต่างกัน เพราะ snapshot รวม `all_bills` ทั้งหมด ซึ่งตอนนี้มี field ที่ **สร้างใหม่** ฝังอยู่:

1. `compute_bill_confidence` เขียน `parse_confidence` / `parse_confidence_reasons` / `parse_confidence_score` ลงทุกบิล — ค่าจากสูตรที่ reconstruct (ต้นฉบับต่างออกไป) → byte ต่าง
2. `summarize_by_company` เก็บ `period` เป็นสตริงรูปแบบใหม่ (งวดไม่ซ้ำ join ด้วย ', ')

**สรุป:** hash เดิมกู้ไม่ได้ (ต้นฉบับหาย) แต่ **ทุกเมตริกที่ผู้ตรวจเห็นจากรายงานตรงกับต้นฉบับ**. baseline ปัจจุบัน (`baseline.json`, `ec61907f…`) คือ **golden master ใหม่ที่ self-consistent** ใช้กันถอยหลัง (regression) ได้ทันที.

---

## 4. การเสริมความแข็งแรง (hardening) ในรอบนี้

| รหัสในรายงานตรวจ | ไฟล์ | สิ่งที่ทำ | ความเสี่ยง |
|---|---|---|---|
| **F9** | `agents/contracts.py` | `mesh.publish` ที่เคย `except: pass` เงียบ → เพิ่ม log ที่ stderr (ยังไม่ทำให้ pipeline ล้ม) | ต่ำมาก (เฉพาะเส้น error ที่ปกติไม่เกิด) |
| **F10** | `agents/base.py` | ลบ dead assignment `elapsed = …` ใน branch `AgentError` (ไม่เคยถูกใช้ก่อน re-raise) | ต่ำมาก (ลบโค้ดตาย) |
| **F8** | `regression_oracle.py` | **เพิกถอน finding เดิม (false positive)** — โค้ด `os.execv` re-exec interpreter ด้วย `PYTHONHASHSEED=0` เป็น pattern ที่ถูกต้องแล้ว ไม่ต้องแก้ | — |

> ทั้งหมดยืนยันแล้วว่า **ไม่กระทบ** ผล `regression_full` (ec61907f ยังตรง) และ `test_agents` (ยัง 38/38).

> **โดยเจตนา ยังไม่แตะ** `parser.py` (F7: `except Exception: pass` ใน hot-path บางจุด) — ความเสี่ยง regression สูงกว่าและไม่จำเป็นต่อการกู้ระบบ. แนะนำทำแยกเป็น PR ของตัวเอง พร้อม regression ครอบ.

---

## 5. ของใหม่ที่เพิ่มเข้าแพ็กเกจ (เครื่องมือที่หายไป)

| ไฟล์ | หน้าที่ |
|---|---|
| `baseline.json` | golden master snapshot ใหม่ (engine path) — ใช้เป็นจุดอ้างอิง regression |
| `verify_golden.py` | รันเส้น **agent** แล้วเทียบ hash กับ baseline → พิสูจน์ "agent ไม่เปลี่ยนผลตรวจ" |
| `regression_full.py` | รัน **engine + agent** ในโปรเซสแยก แล้วเช็คว่า `engine == agent == baseline` |
| `smoke_test.py` | ด่านกันพังเร็ว: ไม่มี .py 0 ไบต์ + ทุกโมดูล import ได้ + gate symbol ครบ + fixture ผ่าน (**ดักเคส F1/F2 ได้ทันที**) |
| `REBUILD_STATUS_TH.md` | เอกสารฉบับนี้ |

---

## 6. วิธีรัน/ตรวจสอบ (เรียงตามความเร็ว)

```bash
# (เร็วสุด ~วินาที) ด่านกันพัง — ควรรันก่อน commit ทุกครั้ง
PYTHONHASHSEED=0 python3 smoke_test.py

# (กลาง) สัญญาสถาปัตยกรรมของชั้น agent — ต้องได้ 38/38
PYTHONHASHSEED=0 python3 test_agents.py . /mnt/project

# (เต็ม) regression engine+agent+baseline — ต้องขึ้น "ผ่านทั้งหมด"
PYTHONHASHSEED=0 python3 regression_full.py . /mnt/project

# (ถ้าข้อมูลเปลี่ยนโดยตั้งใจ) สร้าง baseline ใหม่
PYTHONHASHSEED=0 python3 golden_master.py . baseline.json /mnt/project
```

> ต้องตั้ง `PYTHONHASHSEED=0` เสมอ และ `MASTER` ใน `golden_master.py`/`verify_golden.py` ต้องเป็นชุดเดียวกัน ผลถึงเทียบกันได้.

---

## 7. ถ้าพบต้นฉบับเดิมใน source control ภายหลัง

1. แทนที่ `puopuy_units.py` และ `analytics.py` ด้วยต้นฉบับ
2. รัน `PYTHONHASHSEED=0 python3 regression_full.py . /mnt/project`
3. ตีความผล:
   - ถ้า **hash เปลี่ยน** = ปกติ/คาดได้ (ต้นฉบับใช้สูตร `compute_bill_confidence` ต่างจากที่ reconstruct) → ให้สร้าง `baseline.json` ใหม่จากต้นฉบับ
   - สิ่งที่ **ต้องไม่เปลี่ยน** คือ **ตัวเลขผลตรวจ** (BILLS/dup/iv_seq/iv_date/typos/companies). ถ้ายังตรง = ปลอดภัย
4. จุดที่ควรเทียบเป็นพิเศษ:
   - `puopuy_units._vat_tolerance` — **✓ RESTORED แล้ว (OBJ-1A)** เป็นสูตรเดิม `0.5 + |sub|/100000`; ถ้าเจอต้นฉบับให้ diff ทับ (คาดว่าตรงกัน)
   - `analytics.compute_bill_confidence` (น้ำหนักการให้คะแนน — **⚠ APPROX, load-bearing: อยู่ใน golden hash**)
   - `analytics.summarize_by_company` (รูปแบบ field `period` — FAITHFUL)

---

## 8. ลำดับความสำคัญถัดไป (ข้อเสนอแนะ, ยังไม่ได้ทำ)

| ลำดับ | งาน | เหตุผล |
|---|---|---|
| P1 | นำ `smoke_test.py` เข้า CI (รันทุก push) | กันเคส "ไฟล์หาย/ว่าง" ไม่ให้หลุดไป production อีก |
| P2 | จัดการ F7 (`except: pass` ใน `parser.py`) แยก PR | ลด silent failure ใน hot-path อย่างปลอดภัย |
| P2 | F5: ลด global mutable state ใน `state.py` ที่ขวางการรันขนาน | ถ้าจะ scale แบบ parallel |
| P3 | ปรับเอกสาร (line number/baseline) ให้ตรงโค้ดจริง | ลด doc drift |

*หลักการตลอดงาน: รักษาฟังก์ชัน/ตรรกะธุรกิจเดิม, แก้แบบ incremental, ลดความเสี่ยง regression, พิสูจน์ได้ทุกขั้นด้วย golden master.*
