# PARALLEL_MERGE_FOLLOWUP_TH — ปิดช่อง latent bug ใน parallel merge (ADR-PMERGE)

สถานะ: ✅ แก้ + พิสูจน์ครบ | golden `35b2f7c8…` **ไม่ขยับ** | serial==parallel (real, 2/4/8 workers) | CI เขียวครบ

---

## 1. TL;DR

แก้บั๊ก **latent** 3+1 จุดใน `parallel_audit.py` ที่ "พิสูจน์ได้ว่าผิด" แต่มองไม่เห็นจากทุก gate
เพราะ corpus อ้างอิงสะอาด 100% (`sys_issues=0 / text_num=0`) ทำให้ `verify_parallel` ผ่านแบบ
**vacuous** สำหรับ path ที่เสี่ยงสุด (dedup system-issue ข้าม worker + cap text_num).

- เปลี่ยนหลักการ merge: จาก *"parent เดา dedup-key จาก issue dict"* → *"worker คืน key จริง
  (รวม exc-type) มาให้ parent dedup ตรง ๆ"* → แก้ #3 + #4a ในการเปลี่ยนแปลงเดียว
- cap text_num อ่านจาก `config` (ของจริง) แทน `state` (ที่ไม่มี attr → fallback 20000 เสมอ)
- determinism guard: บังคับ `PYTHONHASHSEED=0` + pin start method (กัน spawn/forkserver บน
  Python 3.14/mac/win ทำ typo ordering เพี้ยนเงียบ ๆ)
- เพิ่ม regression gate `test_parallel_merge_contract.py` ที่ยิงเข้า `_merge_results` (production
  path) → **ปิดช่อง vacuous** ที่ทำให้บั๊กพวกนี้ซ่อนได้

**หลักฐานชี้ขาด:** golden (serial path) บน 106 ไฟล์จริง = `35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba`
ทั้งก่อน/หลังแก้ → fix เป็น surgical (ไม่แตะ serial). ส่วน path ขนานพิสูจน์เท่า serial เป๊ะ.

---

## 2. ปัญหาเชิงระบบ: gate ผ่านแบบ vacuous

`verify_parallel` เทียบ serial vs parallel บน `/mnt/project` แล้วผ่าน — **แต่** corpus นั้น
`sys_issues=0, text_num=0` แปลว่าโค้ดส่วนที่ error-prone ที่สุดของ merge **ไม่เคยรันเลย**:
dedup `_SYSTEM_ISSUES` ข้าม worker, cap `_TEXT_NUM_RECOVERIES`, และ rebuild SEEN.
unit test เดิม (`test_parallel_merge_nonempty.py`) ก็ใช้ SYS001 **ตัวเดียว ที่ file-specific และ
ไม่มี exc** → เลี่ยงบั๊กทั้งหมดพอดี. golden ก็ช่วยไม่ได้เพราะเป็น **serial-only** + parallel path
อยู่นอก snapshot. ⇒ บั๊กจริงทั้ง 3 ตัวจึง "มองไม่เห็น" จนกว่าจะมีไฟล์เสียจริงในรอบ production.

> บทเรียน: gate ที่ผ่านเพราะ "ข้อมูลบังเอิญสะอาด" = false safety. ต้องมี fixture ที่ **บังคับ**
> ให้ path เสี่ยงทำงาน (เราเพิ่มแล้วใน §6).

---

## 3. รายการแก้

### #3 [Medium] SEEN-rebuild key ผิด สำหรับ issue ที่มาจาก exception
- **อาการ (latent):** logger ใช้ dedup key `(code, file, sheet, type(exc).__name__)` แต่ exc-type
  **ไม่ได้เก็บใน issue dict** (ฝังใน `detail` เฉย ๆ). โค้ด merge เดิม rebuild SEEN ด้วย
  `iss.get('name')` เป็น element ที่ 4 → ได้คนละ key → ถ้าเฟสหลัง parse re-log key เดิม จะไม่ถูก
  suppress → parallel นับ system issue เกิน serial.
- **ทำไม latent:** เฟสหลัง parse ปัจจุบันใช้ code `SYS-{rule}` ที่ unique อยู่แล้ว เลยยังไม่ชน.
  แต่ parser log parse failure ด้วย `exc=e` จริง (`parser_p2.py:472/476`) → path ไปถึงได้.
- **แก้:** worker คืน `_SYSTEM_ISSUE_KEYS` (key จริง) → parent dedup ด้วย key นั้น. ลบ rebuild loop ทิ้ง.
- **ไฟล์:** `state.py` (+`_SYSTEM_ISSUE_KEYS`), `diagnostics.py` (append key คู่ issue + clear ใน reset),
  `parallel_audit.py` (`_worker` คืน 5-tuple, `_merge_results` dedup ด้วย key).

### #4a [Low-Med] dup ข้าม worker เมื่อ issue มี `file=None`
- **อาการ (latent):** merge เดิม blind `extend` issue ของทุก worker. ถ้า key มี `file=None`
  (หรือ file-independent) จะซ้ำข้าม worker. demo: `file=None` → serial=1, parallel=2.
- **ทำไม latent:** call-site ปัจจุบันใส่ file จริงทุกจุด (`_fname` / `bill.get('file')`).
- **แก้:** ครอบด้วยฟิกซ์ #3 (parent dedup ด้วย key จริง) — กันทั้ง over-count และ over-dedup.

### #cap [Low] merge อ่าน cap จากโมดูลผิด
- **อาการ (latent):** `getattr(state, '_MAX_TEXT_NUM_RECOVERIES', 20000)` — ค่าจริงอยู่ `config.py:47`
  (`hasattr(state, …)==False`) → fallback `20000` เสมอ. บังเอิญตรงเพราะ config = 20000.
- **ผล:** จำกัด — cap นี้เป็น **LOG cap** (`parser_p1.py:306 _record_text_num`) ไม่ใช่ data gate →
  บิลไม่กระทบ. แต่ถ้าวันหนึ่งแก้ cap ใน config → serial/parallel diverge ที่ audit-trail.
- **แก้:** `from config import _MAX_TEXT_NUM_RECOVERIES` ใน `_merge_results`.

### #1 [Medium] determinism ผูกกับ fork+env โดยไม่ enforce
- **อาการ (latent บน Linux):** typo ordering เป็น hash-seed-sensitive. `parse_all_files_parallel`
  เดิมไม่ assert/pin อะไร — พึ่ง fork สืบทอด env ของ parent. บน **spawn** (mac/win) หรือ
  **forkserver** (default Python 3.14) ถ้าไม่ได้ `export PYTHONHASHSEED` → worker สุ่ม seed เอง →
  serial≠parallel เงียบ (golden serial-only จับไม่ได้). logic เองไม่ crash + มี fallback.
- **แก้:** ต้นฟังก์ชัน assert `os.environ['PYTHONHASHSEED']=='0'` (ไม่ใช่ → raise → monolith
  fallback→serial ให้เอง). + pin `mp.get_context('fork')` ถ้ามี (เสถียรข้าม Python version;
  ถ้าไม่มี fork ใช้ default ได้ เพราะ env-guard คุม determinism อยู่แล้ว).

### (เสริม) reset ก่อน serial fallback
- monolith except-handler เดิมเรียก `parse_all_files` ตรง ๆ. ถ้า parallel ล้ม **กลาง merge**
  (หลัง `reset_run_state()` + extend บางส่วน) → state ครึ่ง ๆ. เพิ่ม `reset_run_state()` ก่อน retry.
  (ความเสี่ยงต่ำ เพราะ `BrokenProcessPool` มักยิงที่ `ex.map` ก่อน parent state ถูกแตะ — belt & suspenders)

---

## 4. หลักฐาน RED → GREEN (สถานการณ์เดียวกัน)

**RED — logic merge เดิม (คัดลอกเป๊ะ) FAIL ทั้ง 3:**
```
#3   SEEN has exc-type 'ValueError'? False   -> FAIL   (rebuilt = (...,'Sheet Parsing Failure'))
#4a  file=None deduped to 1? count=2         -> FAIL
#cap honor config cap=5? len=8               -> FAIL   (ใช้ hardcoded 20000)
RED summary: 3/3 FAILED  => test มีเขี้ยว/บั๊กจริง
```

**GREEN — `test_parallel_merge_contract.py` (เข้า `_merge_results` จริง) ผ่าน 12/12:**
```
✅ #3 SEEN key has real exc-type 'ValueError' (not the issue name)
✅ #3 merged SEEN == serial SEEN
✅ #3 _SYSTEM_ISSUE_KEYS aligned 1:1 with _SYSTEM_ISSUES
✅ #3b post-merge re-log of same exc-key is suppressed (no dup)
✅ #4a file=None dup across workers deduped to serial count (=1)
✅ #4b distinct-file issues preserved (count == serial == 2)   ← กัน over-dedup
✅ #cap merge honors config cap (=5), not hardcoded 20000
✅ #cap kept = global prefix ตามลำดับ chunk (4×X + 1×Y)
✅ #empty merge of [] → no issues, no recoveries
```

---

## 5. หลักฐาน golden ไม่ขยับ + serial==parallel

```
GOLDEN (serial, /mnt/project 106 ไฟล์) ก่อน/หลังแก้:
  35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba   (== baseline.json)
  BILLS=834 FILES=106 fn_issues=9 dup=1 iv_seq=28 iv_date=3 typos=42 companies=2   (ตรงทุกตัว)

verify_parallel (real corpus):
  workers=2/4/8 → serial==parallel, golden ตรงทั้งสอง path เป๊ะ

full real-data regression (run_ci.sh /mnt/project):
  engine_hash == agent_hash == baseline == 35b2f7c8…   (engine==agent → ชั้น agent ไม่เปลี่ยนผล)
```
ทำไม golden ไม่ขยับ: serial path เดินผ่าน `parse_all_files` (ไม่ใช่ parallel). logger ที่เพิ่ม
`_SYSTEM_ISSUE_KEYS.append(dk)` ก็ **ไม่รันบน corpus สะอาด** (ไม่มี system issue) และไม่ feed เข้า
report/snapshot อยู่แล้ว → output ไบต์ต่อไบต์เท่าเดิม.

---

## 6. CI wiring (ปิดช่อง vacuous อย่างถาวร)

- `run_ci.sh` — เพิ่ม `[3u2] parallel merge contract (#3 exc-key/#4a file=None/#cap config)`
- `.github/workflows/ci.yml` — ลูป `for t in test_*.py` เก็บ `test_parallel_merge_contract.py`
  อัตโนมัติ (มี global `env: PYTHONHASHSEED=0`)
- gate นี้รัน **โดยไม่ต้องมีข้อมูลจริง** (สร้าง payload ผ่าน REAL logger ในหน่วยความจำ) → จับ
  regression ของ merge ได้แม้ corpus ยังสะอาด

---

## 7. ที่ "ไม่แก้" — พร้อมเหตุผล (กัน regression เงียบ)

- **ไม่ clamp `workers` ด้วย `cpu_count`** — ตั้งใจให้ over-subscribe ได้ (เช่น `PUOPUY_PARALLEL=8`
  บนเครื่อง 1 core) เพื่อให้ทดสอบ merge หลาย chunk ได้. ถ้า clamp ด้วย cpu_count บน CI core น้อย
  → เหลือ 1 chunk → **path merge ไม่ถูกทดสอบ** (ย้อนแย้งเป้าหมาย). ความเสี่ยง resource-exhaust
  จากค่าที่ตั้งผิดมหาศาล (เช่น 1000) ยังเป็น operability note (ผู้ดูแลตั้งตามจำนวน core ปกติ).
- **ไม่ทำ chunk load-balancing** — แบ่ง block ต่อเนื่อง ~n ก้อน (รักษาลำดับ = merge ตรง serial).
  ไฟล์ใหญ่กองในก้อนเดียวทำให้ perf ตกบน workload เอียง — เป็น **perf-only** ไม่กระทบความถูกต้อง.
  (เปลี่ยนเป็น round-robin/size-aware ได้ภายหลังถ้าจำเป็น โดย merge ยังต้องเรียงตามลำดับไฟล์เดิม.)

---

## 8. คำสั่ง reproduce

```bash
# golden ไม่ขยับ (serial)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 golden_master.py . /tmp/snap.json /mnt/project
#   → 35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba

# regression gate ใหม่ (RED→GREEN lock)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_parallel_merge_contract.py

# serial==parallel บนข้อมูลจริง
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_parallel.py /mnt/project 8

# CI เต็ม (ส่ง data dir เป็น positional arg — ไม่ใช่ env)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 bash run_ci.sh /mnt/project
```

---

## 9. สรุป diff (ไฟล์ที่แตะ)

| ไฟล์ | การเปลี่ยนแปลง |
|---|---|
| `state.py` | + `_SYSTEM_ISSUE_KEYS = []` (1:1 กับ `_SYSTEM_ISSUES`) |
| `diagnostics.py` | `system_issues_reset()` + `.clear()` key-list ; `log_system_issue()` + append `dk` คู่ issue |
| `parallel_audit.py` | `_worker` คืน 5-tuple (+keys) ; แยก `_merge_results()` (dedup ด้วย key จริง + cap จาก config) ; `parse_all_files_parallel` + PYTHONHASHSEED guard + pin context ; ลบ rebuild loop ; ปรับ docstring |
| `ปุ้มปุ้ย_ultimate_v9_modular.py` | + `reset_run_state()` ก่อน serial fallback |
| `test_parallel_merge_contract.py` | **ใหม่** — regression gate 12 check (เข้า `_merge_results` path จริง) |
| `run_ci.sh` | + `[3u2]` |

*ไม่มีการเพิ่มฟีเจอร์ — hardening ล้วน. business logic / schema / golden ไม่เปลี่ยน.*
