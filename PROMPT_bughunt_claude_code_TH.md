# พรอมท์ตรวจหาบั๊กสำหรับ Claude Code — ระบบ ปุ้มปุ้ย (Puopuy) v9.3.4

> วิธีใช้: เปิด Claude Code ที่ root ของโปรเจค (โฟลเดอร์ที่มี `golden_master.py`, `baseline.json`, `INVARIANTS/DECISIONS.md`) แล้ววางข้อความทั้งหมดด้านล่างนี้เป็นพรอมท์แรก. พรอมท์นี้ self-contained — อธิบายระบบ/กติกา/วิธีตรวจครบ เพราะ Claude Code ไม่มี context จากที่อื่น.

---

คุณคือ Principal Software Architect + Production Reliability Engineer + Code Auditor ของระบบนี้ ภารกิจ: **หาบั๊ก (ร้ายแรง/กลาง/ต่ำ) แล้วแก้แบบ surgical โดยห้ามทำให้ผลตรวจเปลี่ยน** สื่อสารภาษาไทย (ศัพท์เทคนิคอังกฤษได้).

## ระบบนี้คืออะไร
ปุ้มปุ้ย = ระบบตรวจใบกำกับภาษี/VAT แบบ offline (Python 3.12). อ่านไฟล์ผู้ขาย `.xls/.xlsx` (เซลล์ภาษาไทย) → parse เป็น "บิล" (มี: บริษัท/เลขภาษี/ที่อยู่/สาขา/เลขที่เอกสาร/เลขใบกำกับ iv/วันที่/รายการสินค้า/ยอดก่อน VAT/VAT/ยอดรวม) → ตรวจ ~56 กฎ → ออกรายงาน. คลังจริง: 148 ไฟล์ / 1,056 บิล.

## 🔑 กติกาเหล็ก (ละเมิดไม่ได้)

1. **Golden hash = ความจริงเดียวของผลตรวจ.** `baseline.json` มีคีย์ `_sha256` (ค่าปัจจุบันต้องตรงกับที่อยู่ในไฟล์). โค้ดที่ถูกต้องต้องทำให้ `golden_master.py` คำนวณ hash นี้ออกมาเป๊ะ. **ถ้า hash เปลี่ยน = คุณทำผลตรวจพัง → revert ทันที** เว้นแต่เป็นการ rebaseline ที่ตั้งใจ (ต้องมีหลักฐาน + ADR + เจ้าของอนุมัติ).

2. **ลำดับความสำคัญ:** Stability > Reliability > Maintainability > Consistency > Predictability > Scalability > Performance > **Features (ห้ามเพิ่มเว้นได้รับอนุญาตชัดเจน)**.

3. **ทุกการแก้โค้ด → เขียน ADR ต่อท้าย `INVARIANTS/DECISIONS.md`** (เลข ADR ล่าสุดดูในไฟล์นั้น) ระบุ: ความเสี่ยงเดิม / root cause / ทางแก้ / migration risk / priority.

4. **surgical เท่านั้น** — แก้ทีละจุด, golden gate ทุกครั้ง, 1 phase ต่อ commit (bisectable). ห้าม rewrite ใหญ่ / สลับ engine / self-repair loop.

5. **forensic-first** — อ่าน source จริง + reproduce บั๊กด้วย fixture จริงก่อนเขียน patch. **ห้าม patch โค้ดที่ยังไม่ได้อ่าน.**

## 🔒 สภาพแวดล้อมที่ต้องตั้ง (ก่อนรันทุกครั้ง — ไม่ตั้ง = hash เพี้ยน)
```bash
export PYTHONHASHSEED=0
export PUOPUY_AUDIT_DATE=2026-06-02
export PUOPUY_OFFLINE=1
# pinned: pandas==2.2.2 numpy==2.2.6 xlrd==2.0.1 openpyxl==3.1.5 rapidfuzz==3.10.1
# optional (ห้ามติดตั้งถ้าจะ reproduce golden): pythainlp / plotly / tqdm
```

## ✅ คำสั่งตรวจ (oracle) — รันหลังแก้ทุกครั้ง
```bash
# 1. golden hash ต้องตรง baseline (สำคัญสุด)
python3 golden_master.py . /tmp/chk.json <DATA_DIR> && \
  python3 -c "import json; b=json.load(open('baseline.json'))['_sha256']; h=json.load(open('/tmp/chk.json'))['_sha256']; print('MATCH' if h==b else 'DRIFT '+h)"

# 2. regression เต็ม (engine == agent == baseline)
python3 regression_full.py . <DATA_DIR>          # ต้องขึ้น "ผ่านทั้งหมด"

# 3. invariants (fixture hash + pin)
python3 INVARIANTS/check_invariants.py

# 4. doc-sync (เอกสารทุกตัว sync กับ baseline)
python3 test_golden_single_source.py

# 5. reachability (ไม่มี floating module)
python3 test_reachability.py

# 6. เทสทั้งหมด (เป็น standalone script — รันทีละไฟล์ ไม่ใช่ pytest; CI เต็ม time out)
for t in test_*.py; do python3 "$t" >/tmp/t.out 2>&1 && echo "PASS $t" || echo "FAIL $t"; done

# 7. เฉพาะแก้ parser/date → รันตัวนี้ก่อน (ตาข่ายเร็ว)
python3 test_date_parse_characterization.py
```

## 🧪 จุดที่ golden จับไม่ได้ (ตรงนี้คือที่ซ่อนบั๊ก — เน้นตรงนี้)
golden พิสูจน์แค่ "ผลเท่าเดิมบนคลัง 148 ไฟล์ปัจจุบัน" — **ไม่จับบั๊กใน path ที่ไฟล์ปัจจุบันไม่กระตุ้น**. ให้หาแบบ empirical:
- **stress test:** สร้างไฟล์ adversarial (ว่าง/ไฟล์เสีย/cell ขยะ/ตัวเลข overflow 1e308/วันที่เพี้ยน 99/99/9999/unicode zero-width+RTL/ชีต 5000 แถว) ป้อนเข้า `parse_all_files()` → ต้องไม่ครัช, batch ต้องรอด (1 ไฟล์เสียห้ามฆ่าทั้ง batch), ไฟล์ขยะต้องได้ 0 บิล.
- **category-B/C ที่ golden ไม่จับ:** การเข้าถึง attribute ของ module / `core.get`/`getattr` ที่หลุด → ใช้ `test_reachability.py` + `check_invariants.py` เป็น oracle.

## ⚠️ HAZARD ที่รู้แล้ว (อย่าทำพลาดซ้ำ)
- `iv_number` = logic key (normalized) **ห้ามแตะใน `regression_oracle.py`** ; `iv_number_raw` = ค่าที่โชว์.
- **เลขที่เอกสาร**: เคยมีบั๊กไป "คว้าค่า subtotal/ยอดเงินมาเป็นเลขเอกสาร" เมื่อเลขเป็นเลขเปล่า 5 หลัก (ไม่มี IV prefix). ต้องประกบ iv_number_raw กับเซลล์จริงเสมอ. **pre-VAT ต้องใช้เซลล์ line-item ไม่ใช่ block 'รวมเงิน'** (block summary บางทีเป็น 3 เท่าของจริง).
- **วันที่**: ปี 2 หลักกำกวมต้องไม่สร้างวันที่มั่ว ; ที่อยู่ที่มีเลข "2/12-2/13" ต้องไม่ถูกอ่านเป็นวันที่ (เคยกลายเป็น 1970) ; serial ที่เก็บปี พ.ศ.ตรงๆ (เช่น 244471 = พ.ศ.2569) ต้องแปลง -543 ; วันที่ใน datetime ปี > 2500 ต้อง -543 และห่อ try กัน 29 ก.พ. ของปีที่ ค.ศ.ไม่ใช่อธิกสุรทิน.
- **filename parse**: token เช่น `69.012` เลข `012` ต้องไม่อ่านเป็นเดือน 12 (`int("012")=12`) — มี guard เลขนำหน้า 0 สามหลัก.
- **master file**: `write_master_file` เขียน `master_companies.json` เป็น **stub** (มีคีย์ `_golden_stub`) — process golden/regression จะสร้างไฟล์นี้ + โฟลเดอร์ `e2e_output/` ขึ้นมา **ต้อง exclude ออกจากแพ็กเกจ** (รวม `__pycache__`, `*.orig`). มี guard `_file_is_stub()` กัน stub เขียนทับ master จริง.
- **report desync**: รหัสเลน "review" ต้องตรงกันระหว่าง `config.REVIEW_CODES` กับ `issue_consolidator.REVIEW_ONLY` (เคย desync ที่ ITM015 → จัดผิดเป็น must-fix). source of truth = `code_labels.MAP` (action: fix/check/review/note).
- **advisory layer** (`issue_consolidator`, `build_consolidated_report`, `super_ultra_viewer`, `config.REVIEW_CODES`) = อ่านอย่างเดียว **ไม่กระทบ golden** — แก้ได้ปลอดภัย แต่ระวัง: รหัสกฎ ITM011/ITM015/ITM019 ตัว flag **อยู่ใน golden snapshot** (ฝังใน `all_bills[].issues`) แตะเมื่อไหร่ golden ขยับ.

## 🧱 โครงสร้างโมดูลหลัก
- parse: `parser_p0a.py` (filename), `parser_p2.py` + `parser_guards.py` (block/guard), `puopuy_dates.py` (วันที่), `puopuy_units.py` (หน่วย/Decimal)
- rules: `rules_engine.py` + `rules_engine_rules_a/b/c.py` + `rules_engine_base.py`
- report: `issue_consolidator.py`, `config.py` (REVIEW_CODES), `code_labels.py` (MAP/action), `build_consolidated_report.py` (Excel 4 ชีต), `super_ultra_viewer.py` (company_summary), `agents/vendor_report.py`
- entry: `ปุ้มปุ้ย_ultimate_v9_modular.py` (`parse_all_files`/`run_audit_core`/`reset_run_state`), `run_agents.py`
- tooling: `golden_master.py`, `regression_full.py`, `verify_golden.py`, `make_release.py`, `INVARIANTS/check_invariants.py`

## 🚀 ปล่อยแพ็กเกจ — ห้าม zip มือ
```bash
python3 make_release.py <pkg_dir> <data_dir> <out.zip>
```
มันจะ build→extract→รัน oracle บน tree ที่แตกจาก zip→เทียบ hash. **ไม่ตรง golden = ลบ zip ทิ้ง.** ใช้ Python `zipfile` เสมอ (ชื่อไฟล์ไทยรอด ; Linux `unzip` ทำเพี้ยนเป็น `#U0e...`).

## 📋 สิ่งที่ต้องส่งกลับ
สำหรับบั๊กแต่ละตัว: **(1)** ระดับ (🔴ร้ายแรง/🟡กลาง/🟢ต่ำ) **(2)** ความเสี่ยงเดิม **(3)** root cause (พร้อม fixture/เซลล์ที่ reproduce) **(4)** ทางแก้ surgical **(5)** migration risk **(6)** golden ยังตรง `baseline.json` หรือไม่ (ต้องตรง). ปิดท้าย: รายงานว่ารัน oracle ครบ (ข้อ 1-6 ด้านบน) ผลเขียวหมด + เขียน ADR แล้ว.

## ❗ ขอบเขต
- **ห้าม:** เพิ่ม feature, rewrite ใหญ่, สลับ engine, self-repair loop, suppress การจับของจริงเพื่อลด false positive (false negative แพงกว่าในระบบ audit — เว้นแต่มี ground-truth + อนุมัติ + rebaseline).
- **เริ่มจาก:** รัน oracle ปัจจุบันให้เขียวก่อน (ยืนยัน baseline) → แล้วค่อยล่าบั๊ก → แก้ → golden gate → ADR.

เริ่มได้เลย: รัน oracle ยืนยัน baseline ก่อน แล้วรายงานสถานะ จากนั้นเริ่มล่าบั๊กเชิงลึก.
