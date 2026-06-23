# ADR-055 — money-serial อ่านเป็นวันที่ใน header scan · rebaseline ba9deda0→0563245c

**วันที่:** 2026-06-20
**สถานะ:** ACTIVE
**golden:** เปลี่ยน `ba9deda0…` → `0563245c…` (rebaseline ตั้งใจ — หลักฐาน+ADR ครบ)
**สั่งโดย:** ผู้ใช้ (forensic audit รีพอร์ต — "ถ้าเจอผิดจริงให้แก้ใข เทสอีก ถ้าเจออีกก็แก้อีก")
**priority:** 🔴 correctness (เงิน≠วันที่ — objective bug, ไม่ใช่ judgment call)

---

## 1. ความเสี่ยงเดิม (current risk)

บิล `TSH_68_0112.xls` ชีต `4.12` มีเซลล์วันที่จริงที่ [3,16] = `'40/12/2568'` — เป็น **typo** (วัน 40 ไม่มีจริงในปฏิทิน ; น่าจะพิมพ์ `04/12/2568` ผิด). `parse_date_any('40/12/2568')` คืน `None` **ถูกต้อง**.

แต่ header scan วิ่งสแกนเซลล์ต่อ แล้วไปเจอเซลล์ [10,19] = `43600.0` ซึ่งคือ **line-total ของรายการ #2** (สิ่วด้ามไม้: 400 × 109 = 43600 บาท). ค่า 43600 อยู่ในช่วง Excel-serial ฝั่ง ค.ศ. (30000–70000) → `parse_date_any(43600)` แปลงเป็นวันที่ **15/05/2019** (มั่ว).

**ผลพวง (cascade):**
- ฟ้อง `DT004` (งวดบิล 62/05 ≠ งวดฝังใน IV 68/12)
- ฟ้อง `DOC001` (ชื่อชีต 04/12 ≠ วันที่บิล 15/05)
- วันที่มั่ว **poison** การตรวจลำดับ IV ข้ามชีต → ชีต `2.01` ฟ้อง `IV004` **เท็จ** (เทียบกับ "ใบก่อนหน้า 15/05 IV68120458")
- ใน company_summary: สร้าง **phantom period** "เอ็น.พี.เอส.พลัส 62.05" (พ.ค.2562) แยกออกจากงวดจริง

นักบัญชีเห็นวันที่ผิด (15/05/2019) แทนที่จะเห็นต้นตอจริง (เซลล์เป็น 40/12/2568 ที่ต้องแก้).

## 2. Root cause

`parser_p1.py::_pb_scan_header` (เดิมบรรทัด 561-565) ส่ง **ทุกเซลล์** เข้า `parse_date_any` รวมเซลล์ยอดเงิน:
```python
if not result['iv_date']:
    d = parse_date_any(v)   # v = เซลล์ใด ๆ รวมยอดเงิน 43600
    if d: result['iv_date'] = d ...
```
เมื่อ date cell จริงเป็น typo (parse ไม่ได้) loop จะวิ่งต่อแล้วคว้าเซลล์เงินตัวแรกในช่วง serial มา fabricate วันที่. เซลล์เงิน 43600 บาท แยกจาก serial วันที่ (43600 = 15/05/2019) **ไม่ได้ด้วยค่าเปล่า ๆ** — ต้องอาศัย context (นี่คือ header date scan).

`parse_date_any` สาขา `30000 < v < 70000` → xldate เป็น **feature ที่ตั้งใจ** (รับวันที่ที่เก็บเป็น serial) + มี characterization test (`ser_ce_inrange` 46150→2026-05-08) → **ห้ามแก้ที่ utility**.

## 3. ทางแก้ (surgical · call-site)

ใน `_pb_scan_header` ก่อนเรียก `parse_date_any(v)` เพิ่ม guard: ถ้า `v` เป็นตัวเลขเปล่า (`int/float`, ไม่ใช่ bool/NaN) อยู่ในช่วง `30000 < v < 70000` → ข้าม (ไม่ถือเป็นวันที่):
```python
_money_serial = (isinstance(v, (int, float)) and not isinstance(v, bool)
                 and not pd.isna(v) and 30000 < float(v) < 70000)
d = None if _money_serial else parse_date_any(v)
```
**ไม่แตะ `parse_date_any`** → utility คงสัญญาเดิม 100% + characterization test ผ่าน. วันที่ข้อความ / datetime object / **พ.ศ.-serial (>200000 เช่น 244419 ของ TNT)** ไม่กระทบ.

## 4. Migration risk / delta (วัด exact บนคลัง 148 ไฟล์ / 1056 บิล)

เปลี่ยน **iv_date เพียง 1 บิล** (พิสูจน์: patch ที่ call-site และ patch global ทั้งคู่เปลี่ยน 1 บิลเดียวกัน — ไม่มีบิลใดพึ่ง bare CE-serial เป็นวันที่):

| บิล | เดิม | ใหม่ |
|-----|------|------|
| TSH_68_0112 ชีต 4.12 | date=15/05/2019 · DT004 + DOC001 | date='' · `_bad_date`=40/12/2568 · **DT006** "วันที่ 40/12/2568 ไม่มีจริงในปฏิทิน ต้องแก้วันที่" |
| TSH_68_0112 ชีต 2.01 | IV004 (เทียบ sequence กับ 15/05 มั่ว) | — (ลบ false flag) |

- `iv_seq` 15→14 · raw issues 927→925 · consolidated ต้องแก้ 161→159
- company_summary: phantom "62.05" หาย → บิล merge เข้างวดจริง "68.12" (ถูกต้อง)
- **ไม่มี detection จริงหาย · ไม่มี false negative** (บิลยัง flag DT006) · ผลถูกต้องมากขึ้นทุกจุด

## 5. rebaseline (ba9deda0 → 0563245c)

`baseline.json` ใหม่ = `0563245c1237379f955c1b8070f2b4376d25652a8f8595e01c76d9784ec83ce3`
- อัปเดต OPERATIONAL_SURFACES ที่ hardcode: MAINTENANCE.md · QUICKSTART_VSCODE_TH.md · _SESSION_HANDOFF.md · DECISIONS.md (banner) · .vscode/tasks.json · .vscode/launch.json · Makefile · ci.yml → 0563245c
- (README/version_gate/orchestrator/constraints ใช้ `baseline.json._sha256` neutral — ไม่ต้องแก้)
- เพิ่ม `ba9deda0` ใน `RETIRED_PREFIXES` (test_golden_single_source.py)
- GOLDEN.md: current=0563245c + ledger ba9deda0 (ประวัติ)
- whitelist `parser_p1.py` (605 LOC) ใน test_file_size_ceiling.py — chain `_pb_*` เดียวกับ parser_p2 (แผนแยก parser_p3 รอบหน้า)

## 6. เทส/พิสูจน์ (oracle 6/6 เขียว @ 0563245c)

- `golden_master.py . /tmp/x /mnt/project` = `0563245c` ✅
- `regression_full.py . /mnt/project` = `0563245c` (engine==agent==baseline) ✅
- `check_invariants.py` (fixture `269ddaed` ไม่ขยับ — fix ไม่แตะ fixture/parse_date_any) ✅
- `test_golden_single_source.py` (doc-sync prefix 0563245c) ✅
- `test_reachability.py` ✅
- `test_*.py` **82/82 PASS** (รวม characterization — parse_date_any ไม่เปลี่ยน) ✅

backup: `parser_p1.py` เดิม @ `/tmp/parser_p1.py.bak` · baseline เดิม @ `/tmp/baseline.ba9deda0.bak`

## 7. ค้าง (ไม่ทำ — รอผู้ใช้ตัดสิน)

- **ITM010/011/019 typo whitelist:** อยู่ใน golden, จับ typo จริงปน variant legit. หลักฐาน FP: "บริสุทธิ์" ถูก ITM010 ฟ้อง "การันต์หลังสระ" ทั้งที่สะกดถูก ; "กระเบื้องพื้น" vs "กระเบื้องปูพื้น", "แกลอน" vs "แกลลอน" = variant ก้ำกึ่ง ปน typo จริง (บสังกะสี, หล็กฉาก→เหล็กฉาก, ตู้คอนซูเมอร์). suppress เสี่ยง false negative → ต้อง curate คำ legit + rebaseline.
- **lane logic:** "ต้องแก้" ใช้ REVIEW_ONLY hardcoded ไม่ใช่ code_labels action tier (design call).
- **ประกบรีพอร์ตระดับบิลอัตโนมัติ.**
