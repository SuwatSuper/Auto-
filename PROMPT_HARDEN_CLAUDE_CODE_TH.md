# พร้อมท์ harden ระบบ "ปุ้มปุ้ย (Puopuy) v9.3.4" → ระบบสมบูรณ์ 5 ปี (สำหรับ Claude Code)

> วางพร้อมท์นี้ให้ Claude Code ทั้งก้อน. Claude Code เริ่มจาก **ศูนย์ context** — เอกสารนี้จึงต้องครบในตัวเอง.
> ระบบทั้งหมดอยู่ใน zip นี้แล้ว (ยกเว้น `vendor/wheels/` ที่ถอดออกเพื่อให้ไฟล์ < 30MB — ดู §3 การติดตั้ง).

---

## 0. บทบาท

You are a **Principal Software Architect + Production Reliability Engineer + Code Auditor + Long-Term Maintenance Specialist** สำหรับ "ปุ้มปุ้ย (Puopuy) v9.3.4" — ระบบตรวจสอบใบกำกับภาษี/VAT ไทย แบบ **offline** (Python 3.12).

**ภารกิจ: ยกระดับคุณภาพระบบ (เสถียร/เชื่อถือได้/ดูแลต่อได้) — ไม่ใช่เพิ่มฟีเจอร์.** ห้ามเพิ่มฟีเจอร์เว้นแต่เจ้าของอนุญาตชัดเจน. คิดเสมือนนายจะต้องดูแลระบบนี้ในโปรดักชันด้วยตัวเองอีก 10 ปี.

**ลำดับความสำคัญ (ใช้ตัดสินทุกครั้งที่ขัดกัน):**
`Stability > Reliability > Maintainability > Consistency > Predictability > Scalability > Performance > Features`

---

## 1. ระบบนี้คืออะไร (context ที่ต้องเข้าใจก่อนแตะโค้ด)

- **อินพุต:** ไฟล์ Excel ผู้ขาย (`.xls/.xlsx`) เซลล์ภาษาไทย → parse เป็น bill objects → ตรวจด้วย **~60 กฎที่เปิดใช้** → ออกรายงาน audit.
- **Corpus ทางการ:** `corpus/` = **148 ไฟล์ / 1,056 บิล** (อยู่ใน zip นี้). คือชุดข้อมูลจริงที่ golden ผูกไว้.
- **Pipeline:** `parse_all_files` → `compute_bill_confidence` → `run_audit_core` (กฎ) → report/agents. เรียกผ่าน `ปุ้มปุ้ย_ultimate_v9_modular.py` (โมดูลรวม) ที่ re-export จากชั้น `parser_p0/p0a/p1/p2`, `rules_engine_*`, `reporting_*`.
- **ชั้น agent/report = advisory เท่านั้น:** ไม่ mutate bill/snapshot, **ไม่กระทบ golden hash**. (ตรวจด้วย `regression_full` ที่ยืนยัน `engine == agent`.)
- **master_companies.json:** ทะเบียนบริษัทจาก ภ.พ.20 (ชื่อ/เลขภาษี/สาขา/ที่อยู่) — ใช้ join ด้วย **tax_id** (ไม่ใช่ fuzzy name). **ปัจจุบันข้อมูลจริงน้อย + ถูก exclude ออกจาก release** → กฎตรวจตัวตน ~24 กฎ dormant (ดู §9 รายการที่ 1).

**ไฟล์สำคัญที่ต้องรู้จัก:**
- `baseline.json` — golden snapshot (มี `_sha256` = **`23b315e8…`** ที่ต้องตรงเป๊ะ)
- `regression_full.py` — รัน audit corpus → เทียบ hash (engine==agent==baseline)
- `golden_master.py` / `golden_snapshot.py` — สร้าง snapshot + hash (แหล่งความจริงเดียว)
- `run_ci.sh` — CI ทั้งหมด (≥109 ด่าน) · `INVARIANTS/check_invariants.py` — tripwire
- `make_release.py` — **ทางปล่อย release ทางเดียวที่อนุญาต** (build→extract→verify→reject ถ้า drift)
- `INVARIANTS/DECISIONS.md` — ledger ADR **append-only** (ADR ล่าสุด = ADR-125)
- `parse_canary.py` — เตือน "อัตรา parse ร่วง" · `constraints.txt` — ตรึงเวอร์ชัน

---

## 2. INVARIANTS เหล็ก — ห้ามละเมิดเด็ดขาด (ละเมิด = งานเสีย)

1. **Golden hash = แหล่งความจริงเดียว.** `baseline.json._sha256` = **`23b315e809b6a2d095f2192a68dfc11e789a69b0b8d9f55ed994b70788517301`**. ทุกการเปลี่ยนโค้ดต้อง reproduce hash นี้เป๊ะ. การ rebaseline (เปลี่ยน hash) ทำได้เฉพาะ **เจตนา + มี ADR + เจ้าของอนุมัติ**.
2. **ENV บังคับทุกครั้งที่รัน oracle/golden/CI:** `PYTHONHASHSEED=0`, `PUOPUY_AUDIT_DATE=2026-06-02`, `PUOPUY_OFFLINE=1`. ลืมตั้ง = hash เพี้ยนหลอก.
3. **ล้าง bytecode ก่อนตรวจ hash ทุกครั้ง:** `find . -name __pycache__ -type d -exec rm -rf {} +; find . -name '*.pyc' -delete`.
4. **parse-core FROZEN:** แตะ `parser_p0/p0a/p1/p2.py` ด้วยความระมัดระวังสูงสุด. แก้ได้เฉพาะเมื่อมีบั๊กจริง + พิสูจน์ reproduce + ทำแบบ surgical + ผ่าน `parse_canary` (อัตรา parse ไม่ร่วง) + golden เป๊ะ. โครง seq/merge/serial ต้อง byte-identical.
5. **ADR ledger append-only:** `INVARIANTS/DECISIONS.md` **ห้ามแก้ของเดิม** — ต่อท้ายอย่างเดียว. **1 การเปลี่ยน = 1 ADR.**
6. **ติดตั้ง dependency ต้องใช้ `-c constraints.txt` เสมอ** (กัน numpy/pandas เวอร์ชันเลื่อน). เวอร์ชันต้องเป๊ะ: `pandas==2.2.2, numpy==2.2.6, xlrd==2.0.1, openpyxl==3.1.5, rapidfuzz==3.10.1`.
7. **ห้ามติดตั้ง `pythainlp` เด็ดขาด.** Golden 51 typo มาจาก `CONSTRUCTION_DICT` — ถ้ามี pythainlp จะเปลี่ยนผล typo → hash เพี้ยน.
8. **บีบ/แตก zip ใช้ Python `zipfile` เสมอ** (อย่าใช้ `unzip` ของ Linux) — เพื่อรักษาชื่อไฟล์ภาษาไทย.
9. **`make_release.py` คือทางปล่อย release ทางเดียว.** ห้าม zip มือ. สคริปต์นี้บังคับ verify ก่อนปล่อย.
10. **กฎ typo:** flag เฉพาะคำที่ **ผิดแน่ ๆ** เท่านั้น. การ "ปลด flag" ต้องได้อนุญาตรายคำ. ITM011 "ตรวจตาเพิ่ม/ก้ำกึ่ง" = จงใจ defer ให้คนตรวจ (ADR-098).

---

## 3. ตั้งค่า environment — ⚠️ wheelhouse ถูกถอดออก (เพื่อให้ไฟล์ < 30MB)

zip นี้ **ไม่มี** `vendor/wheels/` (ถอดออก 73MB). Claude Code มีเน็ต → ติดตั้งจาก PyPI ด้วยเวอร์ชันตรึง:

```bash
pip install -r requirements.txt -c constraints.txt --break-system-packages
# (ถ้า env เป็น venv ไม่ต้องใส่ --break-system-packages)
```

**ด่าน sanity บังคับ — ก่อนแตะโค้ดบรรทัดแรก** ต้องพิสูจน์ว่า environment ตรง golden:

```bash
find . -name __pycache__ -type d -exec rm -rf {} + ; find . -name '*.pyc' -delete
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 \
  python3 regression_full.py . corpus
# ต้องพิมพ์: engine == baseline ✅  (hash = 23b315e8…)
```

ถ้า **ไม่** ได้ `23b315e8` → environment ไม่ตรง (เวอร์ชัน lib เพี้ยน) → **หยุด** แก้เวอร์ชันให้ตรง constraints.txt ก่อน. ห้ามแก้โค้ดใด ๆ จนกว่า baseline reproduce ได้ — ไม่งั้นจะแยกไม่ออกว่า hash เพี้ยนเพราะ env หรือเพราะโค้ด.

**สำหรับ release สุดท้าย (offline):** ต้อง re-vendor wheelhouse กลับ (ดู §10).

---

## 4. เงื่อนไขการแก้ไข (คำสั่งเจ้าของ — ทำตามครบ 3 ข้อ)

### ข้อ 1 — bug-hunt ลึก + ตั้งตะข่ายนิรภัย ตั้งแต่ตัวอักษรแรกของระบบ
หลังแก้แต่ละจุดเสร็จ ให้ไล่ตรวจบั๊กทุกระดับ: **ร้าย / กลาง / ต่ำ / ลึก / ลึกมาก ๆ / ครัช / ทุกอย่าง** ทั่วทั้งระบบ (เริ่มจากไฟล์/บรรทัดแรกของ pipeline ไปจนจบ). เจอ → **แก้ + ตั้งตะข่ายนิรภัย (regression test / tripwire)** ทุกจุด เพื่อกันถอยหลัง.

### ข้อ 2 — วนซ้ำ 2 รอบ
เมื่อรอบที่ 1 เสร็จ ให้ **วนล่าบั๊ก + harden ซ้ำอีก 2 รอบเต็ม** (รวมเป็น 3 passes) เพื่อให้ระบบคลีนที่สุด. แต่ละรอบต้องไล่ taxonomy ใน §6 ใหม่หมด — รอบหลังมักเจอบั๊กที่รอบก่อนเปิดออกมา.

### ข้อ 3 — มั่นใจ 100% ก่อนส่ง
ก่อนส่งระบบสมบูรณ์ ต้องมั่นใจเต็มร้อยทุกด้าน. **ถ้าไม่มั่นใจเต็มร้อย ห้ามส่ง** — รายงานสิ่งที่ยังค้าง/เสี่ยงแทน. "มั่นใจ 100%" = ทุก gate ใน §7 เขียวครบ + ผ่าน fresh-extract verify อิสระ.

---

## 5. กรอบ "ก่อนเสนอแก้/เพิ่มอะไร" (ถามตัวเองทุกครั้ง)
ก่อนจะเพิ่มของใหม่ ตรวจก่อนว่าแก้ได้ด้วย: (ก) ปรับ implementation เดิม (ข) refactor (ค) ปรับ architecture (ง) ปรับ validation. Default: **รักษา functionality/business logic เดิม · เลี่ยง rewrite · เลือก incremental · ลดความเสี่ยง regression.**

**ทุกข้อเสนอต้องระบุ:** Current risk · Root cause · Long-term impact · Recommended solution · Migration risk · Priority.

---

## 6. taxonomy บั๊กที่ต้องล่า (ไล่ครบทุกรอบ)
Hidden bugs · Edge cases · Silent failures · Logic conflicts · Weak validation chains · Technical debt · Duplicate code · Dead code · Tight coupling · Circular dependencies · State management risks · Error handling weaknesses · Memory issues · Performance bottlenecks · Architecture weaknesses · Maintainability risks · Future scalability risks.

**โฟกัสเฉพาะระบบนี้ (จุดเสี่ยงที่เคยกัด):**
- **parser ทิ้งข้อมูลเงียบ ๆ** (เช่น ADR-125: บรรทัดที่อยู่ถูกทิ้งเพราะไม่มี anchor → บ้านเลขที่หาย). ไล่ทุก `_pb_try_*` / header-scan / item-extract ว่ามี input รูปแบบไหนที่ทำให้ field หาย/อ่านผิดเงียบ ๆ.
- **กฎครัชเงียบ → SYS → ข้ามกฎ/ข้ามบิล = false-negative** (ADR-120/124 GAP-A/B). ทุกกฎต้องทน non-str / None / non-list / NaN / bool / Decimal โดยไม่ครัช.
- **money/serial misread** (ยอดเงินถูกอ่านเป็นเลขเอกสาร/วันที่ — ADR-055/F-MONEYIV).
- **เลขไทย/full-width/NBSP/ZWS/นิฮหิต** ในเซลล์ (normalize ครบไหม — ADR-074/114).
- **fuzzy match ข้ามบริษัท** (match-guard — กันผูกผิดบริษัท).
- **state ค้างข้ามการรัน** (parse 2 รอบในโปรเซสเดียวต้องได้ผลเท่ากัน — `test_reset_completeness`).

---

## 7. Gate ยอมรับ — ทุก gate ต้องเขียว "ก่อน" ถือว่าเสร็จ (รันด้วย ENV §2)

```bash
# (1) golden reproduce (engine==agent==baseline = 23b315e8)
python3 regression_full.py . corpus

# (2) CI เต็ม + regression ข้อมูลจริง (≥109 ด่าน ต้องเขียวครบ)
bash run_ci.sh corpus

# (3) parse-canary (อัตรา parse ไม่ร่วง — 1056 บิล / 0 ไฟล์ได้ 0 บิล)
python3 parse_canary.py corpus --baseline canary_baseline.json

# (4) crash-fuzz / SYS=0 บน corpus  (รัน audit แล้วนับ SYS-* = 0 ทั้ง 1056 บิล)
#     (มีในชุด CI: test_fuzz_rules_robust.py + test_sys_summary.py — ต้องผ่าน)

# (5) invariants tripwire
python3 INVARIANTS/check_invariants.py

# (6) fresh-extract verify (แตก zip ที่จะส่ง → clean dir → regression_full = 23b315e8)
#     ทำผ่าน make_release.py (§10) ซึ่งบังคับขั้นนี้อยู่แล้ว
```

**ลำดับใต้ทุก gate:** golden reproduce → strict CI → ADR append-only → rebaseline bookkeeping (ถ้าจำเป็น) → parse-core FREEZE check → exact delta verification.

---

## 8. วิธีทำงานต่อ 1 การเปลี่ยน (per-change protocol — surgical)
1. **Forensic-first:** reproduce บั๊กบน corpus จริงก่อนเสมอ. **ห้ามสรุปจากความจำ** — ทุก finding ต้อง reproduce ได้ พร้อม cell reference (ไฟล์/ชีต/แถว) + verdict ✅/❌.
2. แก้แบบ **surgical/incremental** — เปลี่ยนน้อยที่สุด, รักษาพฤติกรรมเดิมที่ไม่เกี่ยวให้ byte-identical.
3. **พิสูจน์ golden-neutral:** วัด blast radius บน corpus (กี่บิลเปลี่ยน). ถ้า 0 → golden ไม่ขยับ. ถ้า >0 และไม่ตั้งใจ → หยุด หาเหตุ.
4. เพิ่ม **regression test** ล็อกการแก้ + **register เข้า `run_ci.sh`**.
5. เขียน **ADR ต่อท้าย** `INVARIANTS/DECISIONS.md` (โครง §1-6 ตามของเดิม: บั๊ก/หลักฐาน/วิธีทำ/พิสูจน์/migration risk/ยืนยัน).
6. รัน gate §7 ครบ.
7. ตัดสินใจสถาปัตย์ที่ชัดเจนได้เอง (ไม่ต้องเด้งถาม) — แต่เรื่อง rebaseline / เปลี่ยน business logic ต้องขออนุมัติเจ้าของ.

---

## 9. เป้าหมายเฉพาะ — 4 รายการที่เหลือ (เรียงตามผลกระทบ)

🔴 **1. master_companies.json (สำคัญสุด).** ข้อมูลจริงน้อย + ไม่ได้แพ็กลง release → กฎตรวจตัวตน ~24 กฎ (ADDR001, TAX003/005/008, BR004, CMP*) **dormant ในโปรดักชัน** ทั้งที่แดชบอร์ดโชว์ active.
   - งาน: (ก) ยืนยัน matching ใช้ **tax_id เป็น join key** (ไม่ใช่ fuzzy name). (ข) ออกแบบทางใส่ไฟล์ master ลง release package (เลิก exclude) โดยมี guard ว่า master ที่ข้อมูลจริงน้อย **ไม่ทำให้ golden ขยับ**. (ค) ทำให้ "rule status" ไม่หลอกตา — ถ้า master ว่าง กฎต้องรายงานว่า unavailable/dormant ชัดเจน ไม่ใช่ active เฉย ๆ. **ระวัง:** การเพิ่ม master จริงจะเปิดกฎตัวตน → อาจเปลี่ยนผล corpus → ถ้าเปลี่ยนคือ **rebaseline ที่ต้องมี ADR + เจ้าของอนุมัติ** (อย่าทำเงียบ).

🟡 **2. UNIT_OK ไม่สอดคล้อง.** `นิ้ว/มม/เมตร/ซม/กก` ยกเว้น แต่ `ลิตร/วัตต์/ขีด/แอมป์/โวลต์` ไม่ยกเว้น → ITM004 ฟ้อง "5ลิตร/5วัตต์" ไม่ลงรอยหลัก ADR-075. **เสนอทางแก้ให้สอดคล้อง + ผลกระทบ แล้วรอเจ้าของตัดสิน** (scope เล็ก, อย่าตัดสินเอง — เป็นเรื่อง policy).

🟡 **3. Typo dictionary (งานต่อเนื่อง).** คำการค้าใหม่ต้อง review รายคำ — flag เฉพาะที่ผิดแน่. ทำให้ flow การเพิ่มคำ + ล็อกการตัดสิน (`test_typo_decisions_lock`) ชัด/ปลอดภัย. ไม่มีวัน "จบ".

🟢 **4. wheels เป็น cp312 (ขอบ 5 ปี).** วัน Python ขยับรุ่น ต้อง re-vendor wheelhouse ใหม่. `test_forward_compat.py` เป็น tripwire เตือนแล้ว. งานบำรุงตามรอบ — ทำให้ขั้นตอน re-vendor (§10) ทำซ้ำได้ชัดเจน.

---

## 10. re-vendor wheelhouse + การส่งมอบ (release สุดท้าย ต้อง offline)

**re-vendor (เพื่อให้ติดตั้ง offline ได้เหมือนเดิม):**
```bash
mkdir -p vendor/wheels
pip download -r requirements.txt -c constraints.txt -d vendor/wheels \
  --platform manylinux2014_x86_64 --python-version 312 --only-binary=:all:
# ตรวจ: ครบทุก wheel + cp312 + regenerate requirements.lock (มี hash)
```

**ปล่อย release (ทางเดียวที่อนุญาต):**
```bash
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
  python3 make_release.py . corpus puopuy_v9_3_4_OFFLINE_COMPLETE_23b315e8_5year.zip
# ต้องพิมพ์: ✅ RELEASE OK ... reproduce golden 23b315e8
# ถ้าไม่ผ่าน = zip ถูกลบทิ้งอัตโนมัติ (ปล่อยไม่ได้) → แก้ให้ผ่านก่อน
```
`make_release.py` จะ build→extract→รัน `regression_full`+`check_invariants` บน tree ที่แตกจริง→เทียบ hash. ผ่านครบเท่านั้นถึงเก็บ zip.

**เกณฑ์ส่งมอบ (ข้อ 3):** ส่งเฉพาะเมื่อ gate §7 เขียวครบ + `make_release` = RELEASE OK + golden = `23b315e8` (หรือ hash ใหม่ที่ rebaseline อย่างมี ADR+อนุมัติแล้ว). **ไม่มั่นใจ 100% = ไม่ส่ง** — รายงานสิ่งที่ค้างแทน.

---

## 11. รูปแบบรายงานบังคับ (ห้ามเปลี่ยน — ล็อกโดยเทสแล้ว)
รายงานสรุปผู้ขาย (`company_summary.txt` ผ่าน `super_ultra_viewer.py` + รายบริษัทผ่าน vendor_report agent) **ต้อง:**
1. รวมตาม `tax_id` — 1 บริษัท+เดือน = 1 บล็อก (ห้ามแยกเป็น ต้องแก้/พร้อมส่ง)
2. ยอด = ผลรวมก่อน VAT (sum subtotal)
3. ชี้บั๊กด้วย ไฟล์/เลขที่เอกสาร/วันที่/ลำดับรายการ/ชื่อ/หน่วย (ไม่ใช่ "(N ใบ)")
4. ใช้คำว่า **"รีเช็ค"** ไม่ใช่ "แก้"

ล็อกด้วย `test_super_ultra_viewer.py` + `test_vendor_report.py` (advisory — ไม่กระทบ golden).

---

## สรุปสั่งงาน
ทำตาม §4 (3 เงื่อนไข) + §8 (per-change) + วน §6 ครบ 3 passes (§4 ข้อ 2) → ผ่าน gate §7 ทุกตัว → re-vendor §10 → `make_release` → ส่งเฉพาะเมื่อมั่นใจ 100%. ทุกการเปลี่ยน = 1 ADR ต่อท้าย. รักษา golden `23b315e8` (หรือ rebaseline อย่างมี ADR+อนุมัติ). เริ่มจากด่าน sanity §3 ก่อนเสมอ.
