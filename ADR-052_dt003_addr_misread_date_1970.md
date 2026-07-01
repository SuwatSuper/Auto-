# ADR-052 — `parse_date_any` จับเลขที่อยู่ "2/12-2/13" เป็นวันที่ → 1970 (false positive) · golden-RESTORING

สถานะ : ACCEPTED — 20.06.2026 · **golden ไม่เปลี่ยน** (คง `ba9deda0` — นี่คือการ *กู้* golden ที่โค้ดใน RECHECK zip drift ออกไป ไม่ใช่ rebaseline)
สั่งโดย : ผู้ใช้ (สั่ง "อ่านไฟล์ทั้งโปรเจคได้มั้ย + ให้คะแนนระบบ" → ตรวจพบ drift ระหว่าง verify → สั่งแก้ทั้งหมดให้สมบูรณ์)

> ระดับ: 🟠 กลาง (false positive 5 บิล + hash drift จาก golden), golden-safe ในการแก้ (แก้แล้วกลับไป `ba9deda0` เป๊ะ)

---

## อาการที่พบ (DT003) — แพ็กเกจ RECHECK ให้ hash ไม่ตรง baseline ของตัวเอง

รัน engine บนคลังจริง 148 ไฟล์ /mnt/project:

```
engine_hash = bcfcaf37...      ← โค้ดใน pukpui_v9_3_4_RECHECK_20260620.zip
baseline    = ba9deda0...      ← baseline.json ในแพ็กเกจเดียวกัน (golden ทางการ)
```

นิ่งทุกครั้ง (รัน 3 รอบ ได้ `bcfcaf37` เท่ากัน = deterministic ไม่ใช่ flakiness). diff snapshot เทียบ baseline:
ต่างแค่ 3 key — `iv_seq` (15→**20**), `all_bills` (5 บิลวันที่เพี้ยน), `summary`. ที่เหลือ (typos 51, filename_issues 14, iv_date 3, dup 1, file_names 148) **ตรง baseline เป๊ะ**.

5 รายการที่เกินมาทั้งหมดมาจาก **ไฟล์เดียว** = `ที่อยู่ เลขที่.xls` (ไฟล์ QA edge-case) — เป็น flag
"IV วันที่ไม่สอดคล้อง" (CRITICAL) เพราะบิลทุกใบในไฟล์มี `iv_date = 12/02/1970`.

---

## Root cause (forensic ระดับเซลล์ + regex)

บิลในไฟล์นี้มี date cell `r6c16` = Excel serial `244471.0` = **พ.ศ. 2569** (เกิน pandas `Timestamp.max` ปี 2262
→ pandas อ่านเป็น `datetime.datetime(2569,5,2)` แทน Timestamp). `parse_date_any(datetime(2569,5,2))` แปลงถูก
(`year>2400 → -543 = 2026-05-02`). **แต่บิลกลับได้ 1970-02-12** — เพราะมี cell อื่นชนะก่อน:

cell ที่อยู่ `r5c4` = `'2/12-2/13 หมู่ที่ 3 ตำบลลำไทร อำเภอลำลูกกา'` ถูก `parse_date_any` คืน `datetime(1970,2,12)`:

1. regex `m_yy` (เปลี่ยนเป็น `re.search` ตอน P4 เพื่อรับ label นำหน้า เช่น 'วันที่ 11/05/69') **ไม่ anchor** →
   สแกนเจอ embedded triple **"12/2/13"** ในสตริง "2/12-2/13" (`(?!\d)` ปล่อยให้ตามด้วยช่องว่างได้) → day=12, mon=2, yy=13
2. `_ivp_year2_to_ce(13)` = **None** (ปี 13 อยู่นอกช่วงปีจริง 58–99/15–39 → "ตีความไม่ได้" ตาม docstring มันเอง)
3. โค้ดเดิม: `year = _ce if _ce is not None else (yy+2500)-543` → **fallback `(13+2500)-543 = 1970`** → `datetime(1970,2,12)`
4. วันที่ขยะนี้ถูก set เป็น `iv_date` ก่อน → ชนะ date cell จริง → "วัน(=12) ≠ sheet(=2/7/18/23/29)" → false flag 5 ใบ

→ **ตัวการ = บรรทัด fallback `(yy+2500)-543`** ที่ "เดา" วันจากปี 2 หลักที่ระบบเองบอกว่าตีความไม่ได้ ขัดสัญญาของ
`_ivp_year2_to_ce` (docstring: *"ช่วง 40–57 คงตีความไม่ได้โดยตั้งใจ — คืน None ให้ชั้นบนตัดสิน"*). P4 (re.search) แค่
*เปิดทาง* ให้ regex ไปจับเลขในที่อยู่ — รากของบั๊กคือ fallback ที่ fabricate วันที่.

---

## การตัดสินใจ + การแก้ (surgical, 1 ไฟล์)

`puopuy_dates.py` `parse_date_any` สาขาวันที่ปี 2 หลัก: **ปี 2 หลักนอกช่วงปีจริง (`_ce is None`) → ไม่สร้างวันที่**
(ปล่อยให้ตกผู้แปลงตัวถัดไป → คืน None สำหรับที่อยู่ → date cell จริงชนะ).

```python
# เดิม (fabricate วันจากปีที่ตีความไม่ได้):
_ce = _ivp_year2_to_ce(yy)[0]
year = _ce if _ce is not None else (yy + 2500) - 543
if 1 <= mon <= 12 and 1 <= day <= 31:
    return datetime(year, mon, day)

# ใหม่ (สร้างเฉพาะปีที่รู้จัก):
_ce = _ivp_year2_to_ce(yy)[0]
if _ce is not None and 1 <= mon <= 12 and 1 <= day <= 31:
    return datetime(_ce, mon, day)
```

**Golden-safe:** corpus 66–69 อยู่ในช่วง 58–99 → `_ce` ไม่เป็น None → พฤติกรรมเดิมทุกบิล. เฉพาะปีตีความไม่ได้
(เช่น 13 จากเลขที่อยู่) ที่เปลี่ยนจาก "fabricate 1970" → "ไม่จับ".

---

## หลักฐาน (พิสูจน์ก่อน–หลัง)

| input | ก่อนแก้ | หลังแก้ | ต้องเป็น |
|---|---|---|---|
| `2/12-2/13 หมู่ที่ 3 ...` (ที่อยู่) | `1970-02-12` ❌ | `None` ✅ | None (ไม่ใช่วันที่) |
| `วันที่ 11/05/69` | `2026-05-11` | `2026-05-11` ✅ | คงเดิม (P4) |
| `Date: 5/5/69` | `2026-05-05` | `2026-05-05` ✅ | คงเดิม (P4) |
| `5/5/69` / `5/5/69 10:00:00` | `2026-05-05` | `2026-05-05` ✅ | คงเดิม |
| `1/1/15` (ค.ศ. 2 หลัก) | `2015-01-01` | `2015-01-01` ✅ | คงเดิม |
| `11/05/2569` (พ.ศ. 4 หลัก) | `2026-05-11` | `2026-05-11` ✅ | คงเดิม |

- date cell serial `244471` (พ.ศ.2569) → 5 บิลกลับเป็น `2026-05-02/07/18/23/29` (ตรง IV-number-encoded date) ✅
- `iv_seq` 20 → **15** (false positive 5 ใบหายหมด); key อื่นเท่าเดิม

---

## เทส/พิสูจน์ (รันบนคลังจริง 148 ไฟล์ /1056 บิล)

- `regression_full.py . /mnt/project` → engine == agent == baseline == **`ba9deda0`** ✅ (exit 0)
- `INVARIANTS/check_invariants.py` → GOLDEN FIXTURE (`269ddaed`) + PIN LOGIC/LENSES/VAT002 ✅
- **test_*.py ทั้ง 81 ไฟล์ PASS** (รัน standalone ตาม run_ci.sh) — 0 fail
- version_gate / smoke_test / e2e_test / verify_golden / verify_parallel / verify_report_det → PASS ทั้งหมด
- diff vs RECHECK zip เดิม: เปลี่ยน **1 ไฟล์เดียว** = `puopuy_dates.py`

---

## บทเรียน / กันซ้ำ

- **fallback ที่ "เดา" จากข้อมูลกำกวมเป็น false-positive รอเกิด** — เมื่อ helper (เช่น `_ivp_year2_to_ce`) ออกแบบให้
  คืน None สำหรับ "ตีความไม่ได้" ผู้เรียกต้อง**เคารพ None** ไม่ใช่ใส่ค่าเดาแทน. การ fabricate วันจากปีกำกวมทำให้
  เศษเลขในที่อยู่/หมายเหตุกลายเป็นวันที่ได้.
- **regex แบบ `re.search` (ไม่ anchor) ต้องคู่กับ gate ค่าที่เข้มงวด** — เปิดให้สแกนทั้งสตริงแล้ว ตัวกรองปลายทาง
  (ช่วงปีจริง) คือด่านกันการจับผิด.
- การมีไฟล์ QA edge-case (serial พ.ศ.เต็มเกิน Timestamp) ในคลัง golden เป็นของดี — มันคือ canary ที่ทำให้ drift
  นี้โผล่ตอน verify hash แทนที่จะเงียบ.
