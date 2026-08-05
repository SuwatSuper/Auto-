# ปุ้มปุ้ย (Puopuy) v9.3.5 — ระบบตรวจสอบใบกำกับภาษี (offline tax-invoice audit)

ระบบ Python แบบ **offline / deterministic** สำหรับตรวจใบกำกับภาษี/ใบแจ้งหนี้จากไฟล์ Excel
(`.xls` / `.xlsx`) ของผู้ขาย: แกะไฟล์ → รัน rules ตรวจสอบ → ออกรายงาน Excel + สรุปรายบริษัทเป็น `.txt`
ทำงานครบในเครื่อง ไม่มี outbound network ระหว่างตรวจ (OBJ-OFFLINE).

## golden baseline (แหล่งความจริงเดียว)

- ค่า hash ปัจจุบันของผลตรวจทั้งระบบเก็บไว้ที่ **`baseline.json._sha256`** — ใช้เป็น oracle ของ
  `golden_master.py` / `regression_full.py`. เอกสารทุกฉบับอ้างค่านี้ผ่าน single source เพื่อกัน drift
  (ดู `GOLDEN.md` สำหรับอภิธานศัพท์ hash ทางการ และ `INVARIANTS/DECISIONS.md` สำหรับ ADR ledger).
- baseline ทางการรันบน corpus จริง **146 ไฟล์ / 1085 บิล** บนเครื่องเจ้าของระบบ (โฟลเดอร์ `/mnt/project`).

## วิธีรัน

```bash
pip install -r requirements.txt -c constraints.txt    # numpy ต้อง 2.2.x, Python 3.12

export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02   # ตรึงผลให้ reproducible

bash run_ci.sh                       # ด่าน CI ทั้งหมด (gate+smoke+pinned+mesh+agents+regression fixture)
bash run_ci.sh /path/to/data         # + regression เต็มบน corpus จริง (เทียบ baseline.json._sha256)
```

## โครงสร้างหลัก

```
parser*.py                          แกะไฟล์ Excel → bill dict (TOR-format handler, provenance amount_source)
rules_engine*.py                    กฎตรวจสอบ r_* (CMP/ADDR/TAX/DT/ITM/VAT/BR) + RULES registry + run_rules
validators.py                       ตรวจข้ามบิล/ข้ามไฟล์ (เดือนตามชื่อไฟล์, IV ซ้ำ, cross-check)
super_ultra_viewer.py               composer สร้าง company_summary.txt / .xlsx (ชั้น advisory)
code_labels.py / code_registry.py   metadata รหัสกฎ (field/label/lane) + จักรวาลรหัส
agents/                             ชั้น multi-agent (orchestrator/verification/vendor_report/…)
golden_master.py / baseline.json    snapshot hash (กันผลตรวจเพี้ยนเงียบ) — แหล่งความจริงเดียว
run_ci.sh / .github/                ชุด CI ครบด่าน
tests/fixtures · tests/real_cases   ข้อมูลตัวอย่าง + บิลจริง 3 ไฟล์ + baseline fixture
ปุ้มปุ้ย_ultimate_v9_modular.py     main entry (โหลดทั้งระบบ)
```

## เอกสาร

เริ่มที่ **[`DOCS_INDEX.md`](DOCS_INDEX.md)** — สารบัญเอกสารทั้งหมด แบ่งเป็น active / ADR / historical.
การเปลี่ยนแปลงตามเวอร์ชันดู [`CHANGELOG.md`](CHANGELOG.md); ค่า hash ทางการดู `GOLDEN.md`;
ทะเบียน ADR + ตัวเลข baseline ดู `INVARIANTS/DECISIONS.md`.

## ปรัชญาการตรวจ

> **"ตรวจไม่ได้" ≠ "ถูก"** — ถ้าไม่มี reference (master) หรือข้อมูลขาด ระบบต้องพูดความจริงว่า
> "ตรวจไม่ได้" แทนที่จะขึ้น "ตรง" หลอก. การตรวจที่พิสูจน์ความจริงได้แม้ไม่มี master
> (เช่น เลขภาษีเดียวชื่อต่าง, ไปรษณีย์↔จังหวัดขัดกัน) คุมความเสี่ยง false positive แบบ conservative
> (false-negative ดีกว่า false-positive) และเคารพ golden discipline ทุกขั้น.
