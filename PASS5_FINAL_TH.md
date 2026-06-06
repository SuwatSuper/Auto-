# พาส 5 — Final Hardening & Handover (ปิดงาน production-ready)

เอกสารนี้สรุปงานพาส 5: ปิดช่องโหว่สุดท้าย + เพิ่ม "ตาข่ายนิรภัยชั้นที่ครอบ `main()`"
หลังพบว่าเวอร์ชันก่อนหน้ามีบั๊ก `NameError` ที่หลุดออกถึงผู้ใช้จริง — บั๊กที่ golden_master
**มองไม่เห็น** เพราะมันทดสอบ pipeline ทีละฟังก์ชัน แต่ไม่เคยเรียก `main()`.

> **พิสูจน์แล้ว 4 ด่าน (ชุด /mnt/project — 32 ไฟล์ / 192 บิล):**
> 1. oracle หลัก `41cf259a…` ✅ (บิล + issue + summary byte-identical)
> 2. oracle ขยาย `168891d7…` ✅ (system_issues + rules state)
> 3. agent path (verify_golden) ✅ — 9 agents, hash ตรง baseline
> 4. **main() path (verify_main_path) ✅ — ใหม่พาสนี้: รัน main() จริงครบเส้น, ไม่มี NameError ซ่อน**

---

## 1. บั๊กที่พบและแก้ (ทั้งหมดเกิดจาก "import หายตอนแยกโมดูล")

อาการที่ผู้ใช้เจอ:
```
❌ Error: name 'section_header' is not defined
  File "parser.py", line 583, in display_low_confidence_bills
    section_header('บิลที่ต้องเช็คมือ (Low Confidence)', '✋')
```

**รากของปัญหา:** ตอนแยก God File ออกเป็นโมดูล โค้ดเดิมเคยได้ `display`/`HTML`/`os`/
`section_header` มา "ฟรี" ผ่าน scope เดียวของ monolith. พอแยกเป็นโมดูลอิสระ แต่ละไฟล์ต้อง
import เองให้ครบ — ที่หลุดคือ:

| # | ไฟล์ | สิ่งที่ขาด | วิธีแก้ |
|---|---|---|---|
| 1 | `parser.py` | `display_low_confidence_bills` เป็น *display logic* แต่ไปอยู่ใน parser และเรียก `section_header`/`display`/`HTML` ที่ไม่มี | **ย้ายฟังก์ชันไป `reporting.py`** (ตาม SoC — ที่นั่นมีครบ) |
| 2 | `analytics.py` | ไม่ได้ `import os` (ใช้ใน `run_addon_pack`) | เพิ่ม `import os` |
| 3 | `analytics.py` | ใช้ `display(HTML(...))` แต่ไม่มี IPython | เพิ่ม **IPython guard** (มี→ใช้, ไม่มี→no-op) แบบเดียวกับ reporting |
| 4 | `analytics.py` | ขาด `traceback`, `load_workbook`, `style_excel_report` | เพิ่ม import (stdlib / openpyxl / reporting) |

**หลักการแก้:** ไม่แก้ logic — แค่คืน import ที่ขาด + ย้ายฟังก์ชันให้อยู่ถูกแผนก (SoC).
ผลตรวจหลักจึง byte-identical (oracle ทั้งสองยังตรงเป๊ะ).

---

## 2. ตาข่ายนิรภัยใหม่: `verify_main_path.py` (ครอบเส้น `main()`)

### ทำไมต้องมี (ช่องโหว่ที่ทำให้บั๊กหลุด)
`golden_master.py` รัน pipeline แบบ **ทีละฟังก์ชัน**:
```
reset → parse_all_files → compute_confidence → run_all_rules → check_* → summarize → crosscheck
```
→ ครอบ "เครื่องยนต์ตรวจ" ครบ และพิสูจน์ byte-identical ได้ดี.
แต่ **ไม่เคยเรียก `main()`** จึงไม่ครอบโค้ดที่อยู่ใน `main()` เอง เช่น:
`display_low_confidence_bills`, `display_executive_dashboard`, `run_addon_pack`,
`audit_text_num_summary`, `run_self_check`, `print_audit_banner`.
บั๊ก `NameError` (ลืม import) ในฟังก์ชันเหล่านี้จึงหลุดออกถึงผู้ใช้.

### harness นี้ทำอะไร
- mock `IPython.display` + `input()` + ชี้ข้อมูลจริง → รันทุกฟังก์ชันในเส้น `main()`
- โฟกัส "resolve ครบทุก symbol / รันได้ครบเส้น" (ไม่ใช่ byte-identical — golden_master ทำแล้ว)
- ถ้าเจอ `NameError`/`ImportError` ที่ใดที่หนึ่ง → รายงานพร้อม traceback → จับได้ก่อนถึงมือผู้ใช้

### ใช้
```bash
python3 verify_main_path.py . /path/to/data
# ✅ ผ่าน: ทุกฟังก์ชันในเส้น main() resolve ครบ — ไม่มี NameError/import bug ซ่อน
```

---

## 3. ชุดพิสูจน์ครบวงจร (รันก่อนส่งมอบทุกครั้ง)

```bash
# 1-2) ผลตรวจ byte-identical (เครื่องยนต์หลัก + state)
python3 golden_master.py    . o1.json /path/to/data   # ต้องได้ 41cf259a…
python3 golden_master_v2.py . o2.json /path/to/data   # ต้องได้ 168891d7…

# 3) agent system เต็ม (9 agents, Hybrid Hierarchical + Mesh)
PYTHONHASHSEED=0 python3 verify_golden.py . o1.json /path/to/data

# 4) เส้น main() ครบ (กัน NameError/import bug — ตาข่ายใหม่พาส 5)
python3 verify_main_path.py . /path/to/data
```

> ⚠️ baseline hash ขึ้นกับชุดข้อมูล + เวอร์ชันไลบรารี. ค่าข้างบน (`41cf259a` / `168891d7`)
> มาจากชุด `/mnt/project` (32 ไฟล์) บน Python 3.12 + ไลบรารีตาม `requirements.txt`.
> ชุดข้อมูล/เวอร์ชันอื่นจะได้ hash ต่างกัน — สร้าง baseline ของตัวเองด้วยคำสั่งเดียวกัน
> แล้วยึดเป็น golden master ของ environment นั้น.

---

## 4. ⚠️ เรื่องเวอร์ชันไลบรารี (สำคัญต่อความถูกต้องของผล)

ระบบ **ล็อกเวอร์ชัน** ไว้ใน `requirements.txt` เพราะ pandas/rapidfuzz/pythainlp ต่างเวอร์ชัน
อาจให้ผล fuzzy-match / ปัดเศษ / tokenize ต่างกันเล็กน้อย → hash เปลี่ยน → "ผลตรวจอาจเพี้ยน".

ถ้าเห็น banner เตือน `🚨 เวอร์ชันไม่ตรงล็อก!` (เช่น Python 3.14 / pandas 3.0 / pythainlp 5.3)
ให้ติดตั้งตามล็อกก่อนใช้งานจริง:
```bash
pip install -r requirements.txt        # ติดตั้งเวอร์ชันที่พิสูจน์แล้ว
```
เวอร์ชันที่พิสูจน์: **Python 3.12** + pandas 2.2.2 · xlrd 2.0.1 · openpyxl 3.1.5 ·
rapidfuzz 3.10.1 · matplotlib 3.9.2 · plotly 5.24.1 · tqdm 4.67.1 · pythainlp 5.0.5.

> หมายเหตุ: โค้ดยัง **รันได้** บนเวอร์ชันใหม่กว่า (degrade graceful) แต่ตัวเลข fingerprint
> อาจต่างจาก baseline ที่ทำไว้ — ถ้าจะยึด byte-identical ให้ใช้เวอร์ชันตามล็อก.

---

## 5. สถานะสุดท้าย (จบ 5 พาส)

```
God File เดิม 5,093 บรรทัด (1 ไฟล์)  →  DAG หลายโมดูล + ระบบ agent 3 ชั้น

config · state                                   ← ฐานราก (ไม่พึ่งใคร)
  ↓
puopuy_core/dates/units · diagnostics · thai_text ← core/leaf (utils, NLP, logger)
  ↓
core_utils · parser · webverify · master · rules_engine ← service layer
  ↓
validators · analytics · reporting               ← consumer (เลิก import main แล้ว)
  ↓
main (orchestrator ~1,027 บรรทัด — ไม่มีใคร import)

           ┌─ agents/ (Hybrid Hierarchical + Mesh) ────────────┐
Control →  │ Tier-1: formula/vat/wht/taxid → mesh → Tier-2:    │
plane      │ crosscheck/confidence → ai_review → synthesis     │  ← advisory ล้วน
           └───────────────────────────────────────────────────┘  (ไม่แตะผลตรวจหลัก)
```

**คงไว้ครบทุกข้อ:** ผลตรวจ byte-identical · ลำดับกฎ 56 ข้อเหมือนเดิม · agent read-only ·
error-isolation · LLM degrade graceful · ตาข่ายนิรภัย 4 ชั้นพิสูจน์ทุกการเปลี่ยนแปลง.
