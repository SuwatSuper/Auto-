# ADR-053 — รอบเสริมความทนทาน 5 ปี: serial พ.ศ.robust + ตาข่าย characterization + release gate + คำตัดสินงานค้าง

สถานะ : ACCEPTED — 20.06.2026 · **golden ไม่เปลี่ยน (คง `ba9deda0`)** · สั่งโดย : ผู้ใช้ ("จัดการแก้ทั้งหมด + เทสไฟล์ทั้งโปรเจค เพื่อระบบที่สมบูรณ์ที่สุดสำหรับ 5 ปีข้างหน้า")

> ระดับ: 🟢 hardening (ไม่มีบั๊ก active เหลือ — ปิดช่องเปราะ/หนี้ที่ระบุใน audit รอบก่อน). ทุกอย่าง golden-safe (พิสูจน์ hash ไม่ขยับ).

บริบท: หลัง ADR-052 (กู้ golden จาก drift) ผู้ใช้ถาม "ระบบสมบูรณ์แบบหรือยัง" → ตรวจพบจุดเปราะ 6 ข้อ → สั่งให้ปิดให้หมด. ADR นี้คือการลงมือกับทั้ง 6 ข้อ โดยคงกติกาหลัก (Stability > Reliability > Maintainability ; ห้าม suppress การจับของจริง ; golden = ความจริง).

---

## สิ่งที่ทำ (ทั้งหมด golden-safe — `regression_full = ba9deda0` หลังทุกข้อ)

### A. `make_release.py` — ประตูปล่อยแพ็กเกจ (ปิดช่อง #1: drift หลุดแพ็กเกจ)
**ปัญหา:** ADR-052 เกิดเพราะแพ็กเกจถูกส่งทั้งที่โค้ดให้ hash ≠ baseline — `regression_full` จับได้แต่ขั้น packaging ไม่บังคับรัน (process gap, ไม่ใช่ code).
**แก้:** สคริปต์ที่ทำ build→extract→verify เป็นอะตอม: (1) zip จาก source (ตัด `__pycache__`/`*.orig`/`*.log`/`master_companies.json` stub/`e2e_output`) (2) extract ไป temp ด้วย Python zipfile (3) รัน `regression_full`(engine==agent==baseline)+`check_invariants` บน **tree ที่แตกจาก zip จริง** (4) เทียบ engine hash == `baseline.json._sha256`. ผ่านครบ→เก็บ zip ; พลาดข้อใด→**ลบ zip + exit 1**.
**พิสูจน์:** positive (แพ็กเกจดี → RELEASE OK) ✅ · **negative** (inject revert ADR-052 → regression_full ❌ + hash `bcfcaf37` → ปฏิเสธ + ลบ zip) ✅ → "สร้าง zip ที่ไม่ reproduce golden" เป็นไปไม่ได้เชิงโครงสร้าง.

### B. `parse_date_any` — รองรับ serial ที่เก็บปี พ.ศ.ตรงๆ ทาง float (ปิด #2: จุดเปราะ date)
**ปัญหา:** `parse_date_any(244471.0)` (float, พ.ศ.2569) เดิมคืน None — corpus รอดเพราะ pandas บังเอิญส่ง `datetime` มา ถ้า read path/pandas เปลี่ยน → พัง. guard `30000<v<70000` ไม่ครอบ serial พ.ศ.เต็ม (~240000–256000).
**แก้:** เพิ่มสาขา float สมมาตรกับสาขา datetime (บรรทัด 32-33): serial 200000<v<300000 → `xldate_as_datetime` → ถ้าปี>2400 ลบ 543 → รับเฉพาะผลปี ค.ศ. 2015–2056 (เกณฑ์ `_ivp_year4_to_ce`) → reject ขยะ.
**golden-safe:** corpus ส่ง cell นี้เป็น datetime อยู่แล้ว → สาขา float ไม่ถูกเรียกบน golden (พิสูจน์: hash = `ba9deda0` หลังเพิ่ม). `244471.0`/`46150.0`/garbage/oob → ถูกต้องครบ.

### C. `test_date_parse_characterization.py` — ตาข่าย 36 เคส (ปิด #3/#4: หนี้ + corpus-bound)
**ปัญหา:** ADR-052 หลุดได้เพราะ "ไม่มีเทสล็อกว่าที่อยู่ต้องไม่เป็นวันที่". `parse_date_any` มี patch ซ้อน ~10 ชั้น interact ยาก.
**แก้:** ล็อกพฤติกรรมทุกสาขา (datetime/serial CE+พ.ศ.raw/Thai-month/2-digit BE+CE/4-digit/leap recovery/**adversarial 11 ตัว→None**/null) ด้วยค่าที่ถูก ณ `ba9deda0`. แก้สาขาใดเพี้ยน→แดงทันที **โดยไม่ต้องรัน golden บนคลังใหญ่** (เร็ว + corpus-independent). มี tripwire เคสบั๊ก ADR-052. wire เข้า `run_ci.sh` [3x3b].
**ผล:** 36/36 PASS.

### E. (ตรวจสอบ — ไม่ต้องแก้โค้ด) optional deps เป็น optional แท้ (#6)
`pythainlp`/`plotly`/`tqdm` ไม่ติดตั้ง: `thai_text.pythainlp_spell_check` มี guard `if not PYTHAINLP_AVAILABLE: return []` (degrade graceful) → **51 typos ใน golden มาจาก CONSTRUCTION_DICT fuzzy ไม่ใช่ pythainlp**. `version_gate.py` แจ้งเตือน optional ชัดอยู่แล้ว. **บทเรียนกลับด้าน:** ติดตั้ง pythainlp เพิ่มอาจ *เพิ่ม* typo candidate → **drift golden** → การ "ไม่ติดตั้ง" คือถูกต้องสำหรับ reproduce `ba9deda0`. (`PYTHAINLP_WHITELIST` กลไกกัน FP มีอยู่แล้ว.)

---

## คำตัดสินที่ "เลือกไม่ทำ" (พร้อมเหตุผล — สำคัญต่อ maintainer 5 ปี)

### D. ITM011/ITM019 whitelist — **ไม่ทำ** (เหตุผล audit-safety + golden integrity)
**ข้อเท็จจริงที่ค้นพบ:** `ITM011`("คำสินค้าผิด",FIX) + `ITM019`("หน่วยสะกดผิด",CHECK) **อยู่ใน golden snapshot จริง** (ฝังใน `all_bills[].issues`) → แตะ = golden ขยับ.
**เหตุผลไม่ suppress:**
1. **golden integrity** — ลด ITM011/019 = เปลี่ยน hash → ต้อง rebaseline (ต้องผู้ใช้อนุมัติ golden ใหม่ที่ "เลิกจับ flag กลุ่มนี้").
2. **cost asymmetry ของระบบ audit** — มัน "จับ typo จริงเป็นส่วนใหญ่" (มั้วน/แกลอน = ผิดจริง). false positive = คนเหลือบดู 2 วินาที ; false negative = ยอดภาษีผิดหลุดไป. การ suppress เพื่อรายงานสวยขึ้น = แลก **Reliability** ทิ้ง (ผิดอันดับ mandate).
3. **ไม่มี ground-truth** — ไม่มีรายการยืนยันว่าคำไหน legit 100% (กระเบื้องพื้น/ปี๊ป = ถูก แต่ต้องผู้รู้โดเมน curate). เดา→กลบการจับของจริง.
**ทางเดินถ้าจะลดจริง (ต้องผู้ใช้ตัดสิน):** ผู้รู้โดเมน curate whitelist คำที่ยืนยัน legit → ใส่ `CONSTRUCTION_DICT`/whitelist → rebaseline golden ใหม่ + ADR + ยอมรับว่า sensitivity ลดลง. ผม **build กลไก + รัน rebaseline ได้ทันทีที่ได้รายการคำ** แต่จะไม่เดาคำเอง.

### DT002 (future-date 8 ตัว) — **ไม่ใช่บั๊ก** artifact ของ `PUOPUY_AUDIT_DATE=2026-06-02` ตรึง (บิล 04-05/06 = อนาคตเทียบวันตรึง). production จริง (today จริง) หายเอง.

---

## เทส/พิสูจน์ (คลังจริง 148/1056 + ชุดเต็ม)
- `regression_full.py . /mnt/project` = `ba9deda0` (engine==agent==baseline ✅) **หลังทุกข้อ A/B/C**
- `check_invariants` (fixture `269ddaed` + pin) ✅ · doc-sync ✅ · package_integrity ✅
- **test_*.py 82/82 PASS** (81 เดิม + characterization ใหม่) · gate/verify ทั้งหมด PASS
- แพ็กเกจสุดท้ายสร้างผ่าน `make_release.py` (build→extract→verify→hash gate) → reproduce golden โดยกลไกบังคับ
- diff vs zip ADR-052: เพิ่ม 2 ไฟล์ (`make_release.py`, `test_date_parse_characterization.py`) + แก้ 2 (`puopuy_dates.py` สาขา float, `run_ci.sh` wire test)

## หลักการที่ตรึงไว้สำหรับอนาคต
- **ห้าม suppress การจับของจริงเพื่อลด false positive** เว้นแต่มี ground-truth + ผู้ใช้อนุมัติ + rebaseline — false negative แพงกว่าเสมอในระบบ audit.
- **ทุกแพ็กเกจต้องออกผ่าน `make_release.py`** — ห้าม zip มือ (กัน ADR-052 ซ้ำ).
- **แก้ parser/date ใดๆ ต้องผ่าน `test_date_parse_characterization.py`** ก่อน — ตาข่ายจับ regression สาขาเร็วกว่า golden เต็ม.
