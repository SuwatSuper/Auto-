# ปุ้มปุ้ย v9.1 — ระบบตรวจสอบใบกำกับภาษี (แพ็กเกจสมบูรณ์)

ระบบ multi-agent สำหรับ audit ใบกำกับภาษี/ใบแจ้งหนี้จากไฟล์ Excel — ประกอบร่างครบ:
ซอร์สเอนจิน + ชุดทดสอบ + CI + เอกสาร ในแพ็กเกจเดียว พร้อมรัน

## โครงสร้างหลัก

```
parser.py                  แกะไฟล์ Excel → bill dict (รวม TOR-format handler)
rules_engine.py            กฎตรวจสอบ r_* ~70 กฎ (CMP/ADDR/TAX/DT/ITM/VAT) + run_rules
validators.py              ตรวจข้ามบิล/ข้ามไฟล์ (เดือนตามชื่อไฟล์, IV ซ้ำ, ลำดับ ฯลฯ)
puopuy_units.py            ตัวช่วยหน่วย/Decimal
config.py / state.py       ค่าคงที่ (mappingproxy) + state กลาง
ปุ้มปุ้ย_ultimate_v9_modular.py   main entry (โหลดทั้งระบบ)
agents/                    ชั้น multi-agent (orchestrator/mesh/verification/…)
golden_master.py           คำนวณ snapshot hash (กันผลตรวจเพี้ยนเงียบ)
run_ci.sh / .github/       ชุด CI ([1]–[8] + coverage [3g]–[3l])
tests/fixtures/            ข้อมูลตัวอย่าง + baseline
test_*.py                  ชุดทดสอบ 14 ไฟล์ (standalone — รันตรง ไม่ใช่ pytest)
COVERAGE_SUMMARY_TH.txt    สรุป coverage ล่าสุด (รวม 98%)
```

## วิธีรัน

```bash
pip install -r requirements.txt -c constraints.txt    # numpy ต้อง 2.2.x

export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02   # ตรึงผลให้ reproducible

# CI ครบชุด (รวม regression เทียบ golden baseline)
bash run_ci.sh /path/to/excel_data

# ตรวจ golden hash อย่างเดียว
python3 golden_master.py . /tmp/out.json /path/to/excel_data
#   → ec61907fd8061bd314b4e4c573a40f4564184936e292c8d6323b5278239e4628

# รันเทสทีละไฟล์ (เช่น)
python3 test_rules_extra2.py
python3 test_parser_extra2.py
```

## หมายเหตุสำคัญ

- **เทสคือ "เพิ่มเท่านั้น"** — ไม่มีการแก้ซอร์สเอนจิน → golden hash คงเดิม
- เทสทุกไฟล์เป็น **standalone script** (มี harness + `sys.exit` ในตัว) ไม่ใช่ pytest
- `config.CFG` เป็น `mappingproxy` (อ่านอย่างเดียว) ป้องกันการแก้ค่าคงที่โดยไม่ตั้งใจ
- ข้อบกพร่องแฝง/โค้ดตายที่พบระหว่าง audit อยู่ใน `COVERAGE_RELIABILITY_REPORT_TH.md`
  (ส่งแยกนอกแพ็กเกจ) — ยังไม่แก้ในรอบนี้เพื่อคง baseline
