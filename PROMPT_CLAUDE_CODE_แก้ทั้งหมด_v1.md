# PROMPT สำหรับ Claude Code — แก้ระบบปุ้มปุ้ย v9.3.4 ให้จบ (ฉบับสมบูรณ์ v1)

คุณคือ Principal Software Architect + Production Reliability Engineer ดูแลระบบตรวจใบกำกับภาษี
"ปุ้มปุ้ย" (offline, Python 3.12) ที่รันจริงบนเครื่องนี้. **ภารกิจ: แก้ 3 บั๊กที่ลูกค้าเจอจริง + รีเช็คทั้งระบบ
+ ปิดจบ. ห้ามเพิ่มฟีเจอร์ใหม่เด็ดขาด — แก้/เสริมความทนทานเท่านั้น.** ระบบนี้คือ "ด่านสุดท้าย" ก่อนส่งเอกสาร
ให้ลูกค้า — ข้อมูลผิด = หายนะ. ทำแบบ forensic: พิสูจน์ก่อนแก้, แก้เล็กสุด, verify ทุกขั้น.

---
## 0) กติกาเหล็ก (อ่านก่อนแตะอะไรทั้งสิ้น)

1. ENV บังคับทุกครั้งที่รันตรวจ/เทียบ hash (และล้าง bytecode ก่อนเสมอ):
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 PYTHONPATH=$PWD
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete
```
2. **Oracle ความถูกต้องของโค้ด = fixture golden** (ไม่ต้องใช้ corpus):
```bash
python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json
# ต้องได้: engine_hash = ad0c9dad6fb31bc28251605c1dbad9bf165299d19d11c4752e743477fa6c0749
```
   ถ้าแก้อะไรแล้วค่านี้ขยับ → **หยุด, revert การแก้นั้น, รายงาน** (ห้าม rebaseline fixture เอง).
3. **corpus จริงบนเครื่องนี้ "ใหม่กว่า" baseline** (มีไฟล์เดือน มิ.ย. เพิ่ม เช่น SHS 69.06) →
   `python3 verify_corpus_manifest.py <โฟลเดอร์บิล>` จะขึ้น **DRIFT** และ golden จริงจะ **ไม่ตรง** f05358aa
   = **ปกติ ไม่ใช่บั๊ก**. ห้ามพยายาม "แก้โค้ดให้ hash กลับไปตรง". การ rebaseline ทำ **ท้ายสุด** ตามข้อ 6.
4. ADR ledger (`INVARIANTS/DECISIONS.md`) **append-only** — ทุก fix ต้องเพิ่ม `## ADR-167, 168, …`
   (ล่าสุดตอนนี้ = ADR-166). ห้ามแก้ entry เก่า. ก่อน append ให้ `grep -c "^## ADR-"` และ assert เลขใหม่ไม่ซ้ำ.
5. Dependencies **ห้ามขยับ pin**: pandas 2.2.2 · numpy 2.2.6 · xlrd 2.0.1 · openpyxl 3.1.5 · rapidfuzz 3.10.1.
   `pip install` ทุกครั้งต้องมี `-c constraints.txt`. **pythainlp 5.0.5 ที่ติดตั้งอยู่ = ถูกต้อง (ADR-164) ห้ามถอน/อัป.**
6. ห้ามใช้คำสั่ง `unzip` กับไฟล์ใดๆ (ชื่อไฟล์ไทยเพี้ยน) — ใช้ Python `zipfile` เท่านั้น.
7. Lock tests ต้อง**เขียวเสมอ**หลังทุกการแก้:
```bash
for t in test_unit_detection_ext test_super_ultra_viewer test_vendor_report \
         test_typo_decisions_lock test_adr123_borderline_clear \
         test_golden_single_source test_reachability test_adr138_gate_robust; do
  python3 $t.py >/dev/null 2>&1 && echo "$t OK" || echo "$t FAIL"; done
```
8. ทำ **ทีละบั๊ก**: แก้ → fixture+locks เขียว → ADR → ค่อยไปข้อถัดไป. ห้ามแก้พร้อมกันหลายเรื่อง.
9. แก้ไฟล์ = สำเนา `.bak` ก่อน (`cp X X.bak_YYYYMMDD`) เผื่อ revert.
10. สิ่งที่ทีมแก้มาแล้วในแพ็กนี้ (ADR-166 — ให้ "ยืนยันผลบนเครื่องจริง" ไม่ใช่ทำซ้ำ):
    (ก) หน่วย `ตัว`,`อัน` เข้า family `ชิ้น` → คู่ ตัว/pc, อัน/pc จับแล้ว
    (ข) `main()` โหมด LEAN: หมายเหตุ(agent)+สรุปบริษัท **ออกเสมอ** ไม่ผูกกับ Excel สำเร็จ

---
## 1) แผนงานรวม (ทำตามลำดับ)

```
[เตรียม] ข้อ 0 → fixture ต้องเขียวก่อนเริ่ม (พิสูจน์ base สะอาด)
[BUG-1] batch อ่านไฟล์ SHS 69.06 ไม่ได้ (เดี่ยวได้)      → หัวข้อ 2
[BUG-2] Excel audit (audit_v58_*.xlsx) ไม่ออก             → หัวข้อ 3
[BUG-3] หมายเหตุหน่วยปนไทย+อังกฤษ ไม่ขึ้น                → หัวข้อ 4
[ระบบ]  รีเช็คทั้งระบบ + rebaseline corpus ใหม่ + CI เต็ม   → หัวข้อ 5-6
[ส่งมอบ] รายงานตาม template                                → หัวข้อ 7
```

---
## 2) BUG-1 — batch หลายไฟล์แล้ว "อ่านไฟล์ SHS 69.06 (คาเมล) ไม่ได้" แต่ส่งเดี่ยวอ่านได้

ข้อความ error มาจาก `parser_p2.py` บล็อก `except Exception as e: print('⚠️ ไฟล์เปิดไม่ได้ {fname}: …')`
และถูกบันทึกเป็น `SYS001 File Open Failure`. **สิ่งแรกที่ต้องได้คือ "exception ตัวจริง"** — อย่าเดา.

### 2.1 H1 (น่าจะเป็นสุด): ไฟล์ถูกเปิดค้างในโปรแกรม Excel ระหว่างรัน batch
ลูกค้า "โยนไฟล์กันไปทีละหลายๆ ไฟล์" = ทำงานกับไฟล์ค้างเปิดพร้อมรัน → OS lock → เปิดไม่ได้เฉพาะตอนนั้น
พอปิด Excel แล้วส่งเดี่ยว = อ่านได้ (ตรงอาการ 100%).
```bash
ls -la <โฟลเดอร์บิล> | grep '~\$'        # มีไฟล์ ~$SHS… = ร่องรอย Excel เปิดค้าง
# ทำซ้ำ: เปิด SHS 69.06 ใน Excel/LibreOffice ค้างไว้ → รัน batch → ดูว่า error เดิมโผล่ไหม
```
ถ้าตรง H1 → **ไม่ใช่บั๊ก logic แต่ต้องแก้ UX ให้บอกสาเหตุชัด** (ตอนนี้บอกแค่ "เปิดไม่ได้"):
แก้ที่ `parser_p2.py` บล็อก except ดังกล่าว — จำแนก `PermissionError` / `OSError` (errno EACCES/EBUSY/ETXTBSY)
→ ข้อความ: `"ไฟล์ถูกโปรแกรมอื่นเปิดค้างอยู่ (เช่น Excel) — ปิดไฟล์แล้วรันใหม่: {fname}"` และคง SYS001 เดิม.
ห้ามเปลี่ยน flow อื่น. จากนั้น: fixture ต้องคง `ad0c9dad…` เป๊ะ (บล็อกนี้อยู่ใน parser — ตรวจซ้ำให้แน่).

### 2.2 H2: จับ exception ตัวจริงจาก batch เดิมที่พัง
```bash
python3 - <<'PY'
import glob, importlib, io, contextlib, traceback, sys
app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular'); app.reset_run_state()
files = sorted(glob.glob('/PATH/บิล/*.xls')) + sorted(glob.glob('/PATH/บิล/*.xlsx'))   # ← แก้ path จริง
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    bills,_ = app.parse_all_files(files)
out = buf.getvalue()
print("BILLS:", len(bills))
for ln in out.splitlines():
    if 'เปิดไม่ได้' in ln or 'ล้มเหลว' in ln: print("ERR>", ln)
PY
```
เอาบรรทัด `ERR>` มาดู `{str(e)[:80]}` — ชนิด exception ชี้ทางแก้. ถ้าต้องการ traceback เต็ม: แก้ชั่วคราว
ให้บล็อก except นั้น `traceback.print_exc()` (ลบออกหลังวินิจฉัย หรือคงไว้แบบ log ก็ได้ถ้าเงียบพอ).

### 2.3 H3: ไฟล์ "ก่อนหน้า" ใน batch วางยา → bisect หา minimal pair
```bash
python3 - <<'PY'
import glob, importlib, io, contextlib
app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
ALL = sorted(glob.glob('/PATH/บิล/*.xls'))+sorted(glob.glob('/PATH/บิล/*.xlsx'))   # ← path จริง
TARGET = [f for f in ALL if 'SHS 69.06' in f][0]
def fails(subset):
    app.reset_run_state(); buf=io.StringIO()
    with contextlib.redirect_stdout(buf): app.parse_all_files(subset+[TARGET])
    return 'เปิดไม่ได้' in buf.getvalue() and 'SHS 69.06' in buf.getvalue()
pre = [f for f in ALL if f != TARGET]
print("ทั้งชุดพัง?", fails(pre))
lo = []
while pre:
    half = pre[:len(pre)//2] or pre[:1]
    if fails(lo+half): pre = half if len(half)>1 else []; lo += ([] if len(half)>1 else half)
    else: lo += half; pre = pre[len(half):]
print("ไฟล์วางยา (minimal):", lo[-3:] if lo else "ไม่พบ — ไม่ใช่ order-dependent")
PY
```
ถ้าพบไฟล์วางยา → เปิดดูว่าทำ state อะไรพัง (`state.py` globals / merge / diagnostics) → แก้จุด reset/isolate
เฉพาะจุด **โดย fixture ต้องคงเดิม**; ถ้า fix จำเป็นต้องขยับ fixture → หยุด รายงาน.

### 2.4 H4: file-descriptor หมด (batch ใหญ่มาก)
```bash
python3 - <<'PY'
import os, glob, importlib, io, contextlib
app=importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular'); app.reset_run_state()
files=sorted(glob.glob('/PATH/บิล/*.xls'))+sorted(glob.glob('/PATH/บิล/*.xlsx'))
n0=len(os.listdir('/proc/self/fd'))
with contextlib.redirect_stdout(io.StringIO()): app.parse_all_files(files)
print("fd ค้าง:", len(os.listdir('/proc/self/fd'))-n0, "(0=ไม่รั่ว)")
PY
```
> อ้างอิง: บนชุด 152×5=760 ไฟล์ในแล็บ fd ค้าง=0 — ถ้าเครื่องนี้รั่ว = ไฟล์ มิ.ย. บางตัวเข้า path ที่ไม่ปิด → ตามรอย opener แล้วปิดใน finally (มี precedent v6.1 [S2]).

**เกณฑ์ปิด BUG-1:** batch ชุดเดิมที่เคยพัง → รันผ่าน · SHS 69.06 ได้บิลครบ (เทียบจำนวนบิลกับตอนส่งเดี่ยว) ·
ข้อความ error กรณี lock บอกสาเหตุชัด · fixture `ad0c9dad…` คงเดิม · ADR-167 บันทึกราก+แก้.

---
## 3) BUG-2 — Excel audit (audit_v58_*.xlsx) ไม่ออก

โค้ดมี safety wrapper แล้ว: `reporting_p2.build_clean_report` เมื่อพังจะ **พิมพ์**
`⚠️ สร้างรายงานคลีนล้มเหลว: {e}` + traceback เต็ม และ `main()` พิมพ์ `❌ สร้างรายงานคลีน (Excel) ไม่สำเร็จ`.
ในแล็บ (1,153 บิล) สร้างสำเร็จ (484KB) → บนเครื่องนี้ **มี exception จริงรออ่านอยู่**.

ขั้นตอน:
1. รันโฟลว์จริงของลูกค้า (main กับโฟลเดอร์บิลจริง) → **คัดลอก traceback ทั้งก้อน** จาก
   `⚠️ สร้างรายงานคลีนล้มเหลว` — นี่คือคำตอบ.
2. แก้ตามชนิดที่เจอ (พบบ่อย):
   - `PermissionError` ตอน `wb.save` → ไฟล์รายงานเก่าถูกเปิดค้าง/สิทธิ์ REPORT_DIR → ข้อความแนะนำปิดไฟล์ +
     ตรวจ REPORT_DIR (ชื่อไฟล์มี timestamp อยู่แล้ว จึงมักเป็นสิทธิ์โฟลเดอร์)
   - crash ใน `_xlsx_sheet_*` / `_clean_sheet_*` (reporting_p2) จาก **ค่าแปลกในบิลเดือน มิ.ย.**
     (None/ชนิดผิด/สตริงยาว) → กันแบบ surgical จุดที่ครัชตามแนว precedent `[A5-FIX]`/`[M4]` ในไฟล์เดียวกัน
     (setdefault/coerce เฉพาะคีย์ที่พัง) — ห้ามรื้อ builder.
3. ยืนยัน: ได้ไฟล์ `audit_v58_*.xlsx` เปิดได้ครบ 7 ชีต + ขึ้น `✅ ไฟล์รายงาน (คลีน 7 ชีต) บันทึกแล้ว` +
   **แม้บังคับให้ fail (ทดลอง)** หมายเหตุ .txt + สรุปบริษัท ต้องยังออก (พฤติกรรม ADR-166).
4. fixture คงเดิม (reporting คือชั้น advisory — ต้องไม่แตะ golden) · ADR-168.

---
## 4) BUG-3 — หมายเหตุ "หน่วยสินค้าปนไทย+อังกฤษ" ไม่ขึ้น (เคยแก้แล้วใน ADR-104)

รากที่พบ + แก้มาแล้ว (ADR-166): (ก) คู่ `ตัว/pc`,`อัน/pc` เดิมหลุด (ตัว/อัน ไม่มีตระกูล) → เพิ่มเข้า family `ชิ้น`
(ข) เดิมหมายเหตุออก "เฉพาะเมื่อ Excel สำเร็จ" → ถ้า BUG-2 เกิด หมายเหตุหายทั้งไฟล์ → ตอนนี้ออกเสมอ.

งานของคุณ = **ยืนยันบนเครื่องจริง + อุดคู่ที่เหลือถ้ามี**:
1. รัน batch จริง (หลังปิด BUG-1/2) → เปิดไฟล์ `หมายเหตุ*.txt` ข้างรายงาน → ต้องมี section
   `หน่วยสินค้า — ตรวจเพิ่ม (Unit Consistency, advisory)` และเคสคาเมลต้องขึ้นทำนอง:
   `⚠️ ไฟล์ที่ใช้หน่วยสินค้า (หน่วยเดียวกัน) ปนภาษาไทย+อังกฤษ … SHS 69.06 — หน่วย "ชิ้น" เขียนปน: ตัว / pc`
2. Smoke เร็ว (ไม่ต้องรอ batch):
```bash
python3 - <<'PY'
import sys; sys.path.insert(0,'agents')
from agents import notepad_report as NR
bills=[{'file':'SHS_69_06.xls','company':'คาเมล','items':[
  {'seq':1,'name':'ท่อ','unit':'ตัว'},{'seq':2,'name':'ท่อ','unit':'pc'}]}]
print('\n'.join(NR._render_unit_consistency(bills)))
PY
# ต้องเห็นบรรทัด: … SHS_69_06.xls — หน่วย "ชิ้น" เขียนปน: ตัว / pc
```
3. ถ้าคู่หน่วยจริงของลูกค้า "ยังหลุด" → เพิ่มใน `unit_detection_ext.py` ตาม pattern เดียวกับ ADR-166:
   ใส่รูปไทยเข้า `th` ของ family ที่ความหมายเดียวกัน (หรือเพิ่ม family ใหม่ th↔en) — **กติกา: ระบบ flag
   เฉพาะ th↔en ใน family เดียว; ห้ามทำให้ th↔th flag กันเอง** → รัน `test_unit_detection_ext.py` ต้องเขียว
   (ถ้า lock เดิมขัดกับคู่ใหม่ → อัป test พร้อมเหตุผลใน ADR) · ADR-169.

---
## 5) รีเช็คทั้งระบบ (หลัง 3 บั๊กปิด)

```bash
# 5.1 code oracle + locks (ข้อ 0.2 + 0.7) ต้องเขียวหมด
# 5.2 สุขภาพระบบ
python3 doctor.py            # ต้อง exit 0 (ยกเว้น advice master ว่าง = ปกติ)
# 5.3 CI ชุด fixture (ไม่ใช้ corpus)
bash run_ci.sh               # ต้อง exit 0 (≈126 step)
# 5.4 sweep ครัช/เงียบ/การเงิน บน corpus จริงเครื่องนี้
python3 - <<'PY'
import glob, importlib, io, contextlib
app=importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular'); app.reset_run_state()
files=sorted(glob.glob('/PATH/บิล/*.xls'))+sorted(glob.glob('/PATH/บิล/*.xlsx'))
with contextlib.redirect_stdout(io.StringIO()):
    bills,_=app.parse_all_files(files)
    for b in bills: app.compute_bill_confidence(b)
    app.run_audit_core(bills,{},isolate=True)
def num(x):
    try: return float(x)
    except: return None
fin=sum(1 for b in bills if None not in(num(b.get('subtotal')),num(b.get('vat')),num(b.get('total')))
        and abs(num(b['subtotal'])+num(b['vat'])-num(b['total']))<=1.0)
print("bills:",len(bills),"| no-item:",sum(1 for b in bills if not b.get('items')),
      "| no-iv:",sum(1 for b in bills if not b.get('iv_number')),
      "| sub+vat=total:",fin,"/",len(bills))
PY
# คาด: no-item=0, no-iv=0, sub+vat=total = 100% (ถ้าไม่ → ไฟล์ไหน อะไร → forensic ต่อ ห้ามปล่อยผ่าน)
```

## 6) Rebaseline corpus ใหม่ของเครื่องนี้ (ทำหลังทุกบั๊กปิด + ข้อ 5 สะอาดเท่านั้น)

```bash
python3 verify_corpus_manifest.py /PATH/บิล            # ยืนยันว่า DRIFT = ไฟล์ใหม่ตามคาด (อ่านรายชื่อ +/−)
python3 golden_master.py . baseline.json /PATH/บิล      # golden ใหม่ (จด hash 8 ตัวแรก)
python3 verify_corpus_manifest.py /PATH/บิล --write     # อัป manifest
python3 test_golden_single_source.py                    # จะฟ้องพื้นผิว doc ที่ต้อง sync hash ใหม่ → แก้ตามที่บอกครบ
# เพิ่ม ADR ใหม่: rebaseline (เหตุผล: +ไฟล์ มิ.ย. N ไฟล์, hash เก่า f05358aa → ใหม่ XXXXXXXX, บิลเก่า 1153 → ใหม่ N)
bash run_ci.sh /PATH/บิล                                # ต้อง exit 0 ครบทุก step รวม [7pre][7][8][8d]
```

## 7) รายงานกลับ (template — กรอกให้ครบ)

| บั๊ก | รากสาเหตุ (พิสูจน์ยังไง) | แก้ที่ไฟล์:บรรทัด | หลักฐานผ่าน | ADR |
|---|---|---|---|---|
| 1 batch อ่านไม่ได้ | | | batch เดิมผ่าน + SHS บิลครบ | 167 |
| 2 excel ไม่ออก | (แปะ traceback ย่อ) | | audit_v58_*.xlsx 7 ชีต | 168 |
| 3 หมายเหตุหน่วย | | | บรรทัด ⚠️ ใน หมายเหตุ*.txt | 169 |

- fixture: `ad0c9dad…` คงเดิมทุกขั้น: ☐
- rebaseline: hash ใหม่ = ________ · ไฟล์ = ___ · บิล = ___ · ADR = ___
- CI เต็ม (`run_ci.sh /PATH/บิล`): exit 0 · step ผ่านทั้งหมด: ☐
- locks 8 ตัว (ข้อ 0.7) เขียว: ☐

## ⛔ ห้ามเด็ดขาด (ทวนอีกครั้ง)
ห้ามเพิ่มฟีเจอร์ · ห้ามแตะ THAI_TYPO_PATTERNS/rules/parse-core เกินจำเป็นต่อบั๊ก · ห้าม rebaseline fixture ·
ห้ามถอน/อัป pythainlp · ห้าม unzip · ห้ามข้าม ADR · ถ้า fix ใดทำ fixture ขยับ → revert + รายงาน (ห้ามฝืนไปต่อ)
