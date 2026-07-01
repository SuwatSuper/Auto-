# พร้อมท์ harden "master-population path" ปุ้มปุ้ย v9.3.4 → พร้อมเปิดกฎตัวตนใช้ 5 ปี (สำหรับ Claude Code)

> วางทั้งก้อนให้ Claude Code. เริ่มจาก **ศูนย์ context** — เอกสารนี้ครบในตัวเอง.
> งานนี้ไม่ใช่ rewrite — เป็นการ harden เส้นทาง "เติม master_companies.json แล้วเปิดกฎตรวจตัวตน" ให้ทนใช้ 5 ปี.
> **กฎเหล็กเดิมทั้งหมดยังใช้** (golden `23b315e8`, ENV, ADR append-only, parse-core FREEZE, zipfile, -c constraints, ห้าม pythainlp, make_release ทางเดียว) — อ่าน `PROMPT_HARDEN_CLAUDE_CODE_TH.md` ถ้ามีในชุด หรือ `INVARIANTS/DECISIONS.md`.

## 0. บทบาท & ลำดับความสำคัญ
Principal Architect + Reliability Engineer. ยกระดับคุณภาพ ไม่เพิ่มฟีเจอร์.
`Stability > Reliability > Maintainability > Consistency > Predictability > Scalability > Performance > Features`

## 1. บริบทเฉพาะงานนี้ (ต้องเข้าใจก่อน)
- ระบบตรวจใบกำกับภาษีไทย ~60 กฎ. ใน ~24 กฎเป็น **"กฎตรวจตัวตน" (identity rules)** ที่เทียบบิลกับ **master_companies.json** (ทะเบียน ภ.พ.20): ADDR001, TAX003/005/008, BR004, CMP*.
- เจ้าของ (Tor) กำลังจะ **เติม master จริง** (ก๊อปจากกรมสรรพากร) เพื่อเปิดกฎพวกนี้ → เส้นทางนี้ต้องแข็งพอใช้ 5 ปี / เป้าหมายพันบริษัท.
- **2 master แยกกัน** (สำคัญมาก):
  1. `golden_snapshot.MASTER` = master **ทดสอบฝังในโค้ด** (ตอนนี้ `{}` ว่าง) — ใช้คำนวณ golden/CI เท่านั้น. `golden_master.py` สลับตัวนี้เข้า `master_companies.json` ชั่วคราว → รัน → คืนค่าเดิม (atexit).
  2. `master_companies.json` (live) = ข้อมูลจริงของ Tor — ใช้ใน **production** (`main()` → `load_master()`).
- **ผลพิสูจน์แล้ว: golden `23b315e8` ไม่ขยับแม้ master live มีข้อมูล** (golden ใช้ตัว #1 ว่างเสมอ). → ทุกการแก้ในงานนี้ **ต้อง golden-neutral** (main golden = `23b315e8` เป๊ะ). ห้าม rebaseline.

## 2. ปัญหาที่ต้องแก้ (ตรวจ + พิสูจน์มาแล้ว — reproduce ซ้ำได้)

### 🔴 ปัญหาหลัก — join master ด้วย "ชื่อบริษัท fuzzy" แทน tax_id
**ตำแหน่ง:** `rules_engine.py:300` → `match_company(bill['company'], master_companies)` ; ตัว `match_company` อยู่ `rules_engine_base.py:62` — **รับแค่ชื่อบริษัท** แล้ว match ด้วย substring + `fuzz.partial_ratio` (threshold `CFG['FUZZY_NAME_THRESHOLD']` = 75). **ไม่ใช้ tax_id ในการ "หา" master record เลย** (tax_id ถูกใช้แค่ตอน "เทียบ" หลัง match — rules_engine.py:309-310).
**ทำไมร้ายต่อ 5 ปี:**
- บิลที่ชื่อเพี้ยน/ย่อ/สลับคำ/ภาษาอังกฤษ/typo → score < 75 → **ไม่ match → กฎตัวตนข้ามทั้งบิล (false-negative เงียบ)** ทั้งที่ tax_id ตรง.
- ที่สเกลพันบริษัท + ผู้ขายเขียนชื่อไม่เป๊ะ = บิลจำนวนมากหลุดการตรวจตัวตนเงียบ ๆ.
- substring match (score 100) ที่สเกลใหญ่ = เสี่ยงจับผิดบริษัทชื่อใกล้กัน (false-positive — เทียบที่อยู่/เลขภาษีผิดราย).
**หลักฐาน (reproduce ได้):**
```
master = {'0105563333333': {'tax_id':'0105563333333','name':'บริษัท เอบีซี เอ็นจิเนียริ่ง แอนด์ คอนสตรัคชั่น จำกัด', ...}}
match_company('บริษัท เอบีซี วิศวกรรม จำกัด', master)  → (None, None, 66.7)   ❌ ไม่ match (ทั้งที่ควรเป็นบริษัทเดียวกัน)
match_company('ABC Engineering and Construction Co.,Ltd.', master) → (None, None, 10.5)  ❌
```
- **บิลจริงมี tax_id 100% (1056/1056 บน corpus)** → tax_id (เลข 13 หลัก เอกลักษณ์) ใช้ join ได้กับทุกบิล = แม่นกว่าชื่อทุกทาง.
- **ดีไซน์ตั้งใจให้ join ด้วย tax_id อยู่แล้ว** (DECISIONS/หลักการ: "use tax ID as join key, not fuzzy name") — โค้ดไม่เคยทำตาม.

**วิธีแก้ (surgical, golden-neutral):**
1. เปลี่ยน join เป็น **tax_id-primary**: ส่ง `bill['tax_id']` เข้า `match_company` ด้วย (หรือส่งทั้ง bill). ในตัว match:
   - สร้าง **index ของ master ด้วย `clean_tax_id(m['tax_id'])`** (O(1) dict) ครั้งเดียว.
   - ถ้า `clean_tax_id(bill.tax_id)` ตรง record ใน index → คืน record นั้น (score 100, แหล่ง=tax_id).
   - ถ้าหลาย record แชร์ tax_id เดียว (สำนักงานใหญ่ + สาขา) → **disambiguate ด้วย `branch`/`branch_no`** ให้ตรงสาขาของบิล.
2. **คงการ match ด้วยชื่อไว้เป็น fallback** เท่านั้น — ใช้เมื่อ (ก) บิลไม่มี tax_id หรือ (ข) tax_id ไม่อยู่ใน master. **ห้ามลบ name matching** (กัน regression เคสที่ master ไม่มี tax_id).
3. conservative: ถ้า tax_id ตรงแต่ชื่อต่างมาก → ยัง match (ด้วย tax_id) แต่ปล่อยให้กฎ TAX/CMP ที่มีอยู่เป็นตัวฟ้องความต่าง — **อย่าให้ logic join ไปกลบกฎ**.
**ต้องพิสูจน์:** main golden = `23b315e8` เป๊ะ (corpus ใช้ master ว่าง → match path ไม่ถูกแตะบน corpus = golden-neutral). + เพิ่ม test (ข้อ 3 ล่าง).

### 🟡 ปัญหารอง 1 — กฎตัวตนไม่มี golden/corpus ครอบ
`golden_snapshot.MASTER = {}` (ว่าง) → ~24 กฎตัวตน **ไม่เคยรันบน corpus ใน CI** → ถ้าโค้ดแก้ทำกฎพังเงียบ ๆ golden ไม่จับ(เพราะ master ว่าง = กฎ dormant). ตอนนี้มีแค่ unit test 5 ไฟล์ (master สังเคราะห์).
**วิธีแก้:** เพิ่ม **"identity-golden" แยก** — ชุด test ที่มี (ก) master ทดสอบเล็ก ๆ (fixed, ใส่ในไฟล์ fixture **ไม่ใช่** ใน corpus จริง — กัน PII) + (ข) บิล fixture สังเคราะห์ 5-10 ใบ + (ค) เอาต์พุตกฎตัวตนที่คาดหวัง **pin เป็น literal**. รันใน run_ci.sh เป็น gate ใหม่. **ห้ามแตะ main golden** (`golden_snapshot.MASTER` คงว่างเพื่อ main golden `23b315e8`). นี่คือตะข่ายนิรภัยของกฎที่ Tor กำลังจะเปิดใช้.

### 🟡 ปัญหารอง 2 — parse_master_blob (เส้นทางก๊อป ภ.พ.20 รายวัน) test บาง
`master.py:111 parse_master_blob` โตเต็มวัย (มี BUG-fix หลายชั้น: tax+branch ติดกัน 18/17 หลัก, ADR-100 เลขบ้านเปล่า ฯลฯ) แต่มี test แค่ 2 ไฟล์ (`test_fix_round2.py`, `test_fix_tnt_trio.py`). Tor จะวาง ภ.พ.20 หลากรูปแบบทุกวัน 5 ปี.
**วิธีแก้:** เพิ่ม **characterization test** ครอบรูปแบบจริง: tax+branch glued (`0-2055-...\t00001`), สำนักงานใหญ่ vs สาขา N, เลขบ้านเปล่าขึ้นต้นที่อยู่, ชื่อภาษาอังกฤษ/ผสม, ฟิลด์ขาด, หลายที่อยู่, รหัสไปรษณีย์ปลายบรรทัด → pin ผลลัพธ์ + กันครัชทุก input.

## 3. เงื่อนไขการแก้ไข (คำสั่งเจ้าของ — ครบ 3 ข้อ)
1. **bug-hunt ลึก + ตั้งตะข่ายนิรภัย ตั้งแต่ตัวอักษรแรกของระบบ** — หลังแก้ ไล่บั๊กทุกระดับ (ร้าย/กลาง/ต่ำ/ลึก/ลึกมาก/ครัช) ทั่วทั้งระบบ + เพิ่ม test/tripwire ทุกการแก้.
2. **วนซ้ำ 2 รอบ** (รวม 3 passes) ให้คลีนที่สุด.
3. **มั่นใจ 100% ก่อนส่ง** — ถ้าไม่เต็มร้อย ห้ามส่ง รายงานสิ่งที่ค้างแทน.

## 4. วิธีทำงานต่อ 1 การเปลี่ยน (surgical)
forensic-first (reproduce ก่อนแก้ + cell/หลักฐาน + ✅/❌) → surgical/incremental → พิสูจน์ golden-neutral (main golden `23b315e8` ไม่ขยับ) → เพิ่ม regression test + register `run_ci.sh` → ADR ต่อท้าย `INVARIANTS/DECISIONS.md` (1 การเปลี่ยน = 1 ADR) → รัน gate §5. เรื่อง rebaseline/เปลี่ยน business logic ต้องขออนุมัติเจ้าของ.

## 5. Gate ยอมรับ (ENV: `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1`, ล้าง bytecode ก่อนทุกครั้ง)
```
python3 regression_full.py . corpus          # main golden = 23b315e8 (engine==agent==baseline) — ต้องไม่ขยับ
bash run_ci.sh corpus                          # CI เต็ม เขียวครบ (+ identity-golden gate ใหม่)
python3 parse_canary.py corpus --baseline canary_baseline.json   # อัตรา parse ไม่ร่วง
# crash-fuzz: SYS-* บน corpus = 0 (test_fuzz_rules_robust.py + test_sys_summary.py ผ่าน)
python3 INVARIANTS/check_invariants.py         # tripwire
# ติดตั้ง offline: pip install --no-index --find-links vendor/wheels -r requirements.txt -c constraints.txt
```
**เพิ่มเฉพาะงานนี้:** ต้องมี test ใหม่ที่พิสูจน์ join ด้วย tax_id (เคส FN เดิม 66.7/10.5 ต้อง match ได้ด้วย tax_id) + identity-golden + blob characterization — ทั้งหมด golden-neutral ต่อ main golden.

## 6. ส่งมอบ (offline · ปลอด PII)
`make_release.py` เป็นทางเดียว (มี [1b] PII self-check — **ห้าม corpus/master หลุด**):
```
python3 make_release.py . corpus out.zip       # ต้องพิมพ์ ✅ RELEASE OK reproduce 23b315e8
```
fresh-extract verify บังคับในตัว make_release แล้ว. ส่งเฉพาะเมื่อมั่นใจ 100% + ทุก gate เขียว + golden `23b315e8`.

## สรุปสั่งงาน
แก้ 🔴 (tax_id-primary join, คง name fallback, disambiguate สาขา) + 🟡×2 (identity-golden coverage, blob characterization) → ทุกอย่าง **golden-neutral** (main golden `23b315e8` ห้ามขยับ) → bug-hunt 3 passes → gate §5 ครบ → make_release → ส่งเมื่อมั่นใจ 100%. 1 การเปลี่ยน = 1 ADR. เริ่มจากด่าน sanity (reproduce `23b315e8`) ก่อนเสมอ.
