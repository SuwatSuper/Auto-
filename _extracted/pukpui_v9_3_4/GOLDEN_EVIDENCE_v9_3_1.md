# หลักฐาน Golden — ปุ้มปุ้ย v9.3.1 (รอบ hardening 17.06.2026)

สภาพแวดล้อมที่ใช้พิสูจน์ (pin ทุกคำสั่ง):
```
Python 3.12.3  |  pandas 2.2.2  numpy 2.2.6  xlrd 2.0.1  openpyxl 3.1.5  rapidfuzz 3.10.1
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1
```

> ⚠️ **ข้อจำกัด:** กล่องนี้ **ไม่มี corpus จริง 106 ไฟล์** (ข้อมูลผู้เสียภาษีออฟไลน์ ไม่มากับแพ็ก)
> จึง **รัน baseline `d6b23d12…` ไม่ได้** — ต้องรันบนเครื่องเจ้าของระบบที่มี `<CORPUS>` :
> ```
> PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . "<CORPUS>"
> # ต้องได้ engine == agent == baseline = d6b23d127999e62c2a898554c012e60c1d8731dffec212770569fa6ec8818173
> PUOPUY_CI_STRICT=1 bash run_ci.sh "<CORPUS>"   # + ด่าน [7][8][8b][8c]
> ```
> การแก้ทั้ง 6 รายการเป็น **golden-safe** (เส้น error/edge/off-audit) → คาดว่า `d6b23d12…` **ไม่ขยับ**
> แต่ต้องให้เจ้าของยืนยันด้วย corpus จริงก่อน ship เป็นทางการ

---

## หลักฐานที่รันได้จริงในกล่องนี้ (เขียวครบ)

### 1) Fixture oracle — `engine == agent == baseline` (แทน baseline เต็มที่รันไม่ได้)
```
$ python regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json
baseline_hash = 269ddaed0c6dd34c735bc09a35dbe82f7b228dc62d424f2b13a740d51aaa34c1
engine_hash   = 269ddaed0c6dd34c735bc09a35dbe82f7b228dc62d424f2b13a740d51aaa34c1
agent_hash    = 269ddaed0c6dd34c735bc09a35dbe82f7b228dc62d424f2b13a740d51aaa34c1
  engine == baseline : ✅
  agent  == baseline : ✅
  engine == agent    : ✅  (ชั้น agent ไม่เปลี่ยนผลตรวจ)
RESULT: ✅ ผ่านทั้งหมด — ผลตรวจตรง baseline และ agent==engine
```
ค่านี้ **เท่ากันก่อนและหลัง** ทุก commit แก้บั๊ก (golden-safe ยืนยัน)

### 2) เทสทุกไฟล์ `test_*.py` — exit 0 ครบ
```
tests pass=76 fail=0
```

### 3) CI เต็ม (ไม่รวมด่านที่ต้อง corpus) — `✅ CI ผ่านทั้งหมด`
```
$ PYTHON=<py3.12> bash run_ci.sh
✔ ผ่าน × 78 ด่าน   |   ✘ ล้มเหลว 0
✅ CI ผ่านทั้งหมด
ℹ ข้าม [7][8][8b][8c] (regression เต็ม) — ต้องระบุ data dir corpus จริง
ℹ ข้าม [9] pip-audit (ไม่ติดตั้ง — graceful, ไม่ใช่ STRICT)
```
(รวมด่านใหม่ `[3x14] bughunt hardening` ที่ตรึงการแก้ทั้ง 6)

### 4) parallel == serial (บน `tests/real_cases` 3 ไฟล์จริง 15 บิล)
```
$ python verify_parallel.py tests/real_cases 8
serial   : bills=15 sys_issues=0 text_num=0 golden=95852c68d66225d9fdbdd1678b703978ea63708ec1dd7c9e24d596b1000a84b4
parallel : bills=15 sys_issues=0 text_num=0 golden=95852c68d66225d9fdbdd1678b703978ea63708ec1dd7c9e24d596b1000a84b4
RESULT: ✅ serial==parallel (golden+issues+recoveries ตรงเป๊ะ)
```

### 5) version gate — ผ่าน (lib หัวใจครบ/ตรง ; ส่วนแสดงผลขาด = WARN ไม่กระทบ hash)
```
$ python version_gate.py   → exit 0 (pandas/numpy/xlrd/openpyxl/rapidfuzz ตรง pin ; matplotlib/plotly/tqdm/pythainlp = WARN)
```

---

## สรุปการแก้ (bisectable — 1 commit/บั๊ก, gate ผ่านทุก commit)
| commit | บั๊ก | ADR |
|--------|------|-----|
| `aecd960` | Parse-S1 `_dic_int_run` OverflowError | 038 |
| `b42ce5b` | Parse-M1/M3 Decimal InvalidOperation + `_cell_to_num` inf | 038 |
| `a383257` | Master-S1 `write_master_file` data loss | 039 |
| `c3f2d57` | Master-M1/M2 `save_master` atomic + `.bak` | 040 |
| `(ci)`    | ลงทะเบียน `test_bughunt_hardening.py` เป็นด่าน `[3x14]` | — |
