# ปุ้มปุ้ย v9.1 — เอกสารส่งต่อ (SESSION HANDOFF)
> สำหรับเริ่มแชทใหม่ต่อจากเซสชันนี้ — สรุปสถานะ "ล่าสุดที่ประกอบร่างแล้ว + ทดสอบแล้ว"

## 0) วิธีรัน (ต้องตั้ง env ทุกครั้ง — deterministic)
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02     # Windows: $env:PYTHONHASHSEED='0'; $env:PUOPUY_AUDIT_DATE='2026-06-02'
pip install pandas xlrd openpyxl rapidfuzz --break-system-packages          # deps แกน
pip install coverage ruff black mypy pip-audit --break-system-packages      # tooling (OBJ-TEST)
PYTHON=python3 bash run_ci.sh /mnt/project     # รันทั้งชุด (corpus ทางการ = 152 ไฟล์, รันขั้น 7-8)
```

## 1) ค่าคงที่ที่ต้องไม่ขยับ (Golden / Invariants)
- **golden hash จริง (152 ไฟล์ `/mnt/project`) = `f05358aa`** · **fixture = `72cb832c…`** (เต็ม: `72cb832c9b667e796b86a78ec5e1b0556c9f19b50d15d7756df1cbd0a58e1f0a`)
- คงเส้น: `engine_hash == agent_hash == baseline_hash` เสมอ (ชั้น agent/advisory ห้ามเปลี่ยนผลตรวจหลัก)
- คอร์ปัสทางการ = **152 ไฟล์ (`/mnt/project`)** → golden `f05358aa…` (engine==agent==baseline). สาย 81 ไฟล์ปลดระวาง (ดู ADR-019).

## 2) กฎโดเมนที่ล็อก (ground truth — นักบัญชี)
- **VAT = 7% เป๊ะ**: `vat == round(subtotal × 0.07, 2)` (ROUND_HALF_UP) ยอมต่างแค่ปัดเศษ ≤ 0.50 — **ห้ามใช้ "แถบ %"**
- ใช้ใน engine `r_vat002` (rules_engine.py) และเลนส์ `L8_vat_7pct` (verification_lenses.py)

## 3) สถาปัตยกรรม (ย่อ)
Hybrid Hierarchical (orchestrator DAG) + Mesh (FindingsMesh) + Agents + Inspection-Bank.
- คำตัดสินจริง = `run_audit_core` (engine, แช่แข็งด้วย golden) → Excel
- งานเพิ่มทั้งหมด = **advisory** (findings VERIFY-*) ห้ามแตะ `b['issues']` → hash ไม่ขยับ
- LLM = Local Ollama opt-in เท่านั้น + อยู่นอกเส้น deterministic/CI (offline → งดออกเสียง)

## 4) สิ่งที่ทำเสร็จ + ทดสอบแล้วในเซสชันนี้ (อยู่ในแพ็กนี้)
- **OBJ-A** — คลังผู้ตรวจ Inspection Bank 6 → **22 ผู้ตรวจ** (precision-first, งดออกเสียงถ้าข้อมูลไม่พอ)
  - `agents/verification_lenses.py` (คลัง 22 + index ข้ามบิล) · `agents/verification_agent.py` (supervisor consensus ≥+2/≤−1)
  - presenter ใน `agents/notepad_report.py` (โชว์ทีมผู้ตรวจ + มติต่อ Error + evidence trail)
  - เทส: `test_verification_lens_pin.py` (pin 14/14) · `test_verification_lenses_unit.py` (42/42)
- **OBJ-OFFLINE** — ออฟไลน์ล้วน (กฎเหล็กข้อ 1) พิสูจน์ "zero outbound ในเส้น audit"
  - `offline_guard.py` (สวิตช์เดียวทั้งระบบ: env `PUOPUY_ALLOW_NETWORK`, localhost อนุญาตเสมอ)
  - `webverify.py` (web_request ปิดเป็นค่าตั้งต้น + fix NameError `confidence_tier`) · `agents/llm_provider.py` (บล็อก LLM remote เว้น opt-in)
  - `file_guard.py` (กัน zip-bomb/ไฟล์ใหญ่ผิดปกติ — wired ใน parse_all_files) · pip-audit ใน CI
  - เทส: `test_offline_audit.py` (11/11) · `test_input_hardening.py` (18/18)
- **OBJ-TEST** — ตาข่ายคุณภาพใน CI
  - `coverage_gate.py` (core ≥90%: parser 95.1 / rules 95.0 / validators 93.5 / units 100)
  - `pyproject.toml` (ruff+black) · `mypy.ini` (ขอบเขต contracts/base+โมดูลใหม่) · `test_validators_coverage.py`
- **OBJ-PERF (ส่วนปลอดภัย)** — `parser.py`: scalar `iloc[r,c]→iat[r,c]` 34 จุด (ค่าเท่ากันเป๊ะ, golden ไม่ขยับ) ~18% end-to-end (micro-bench iat เร็วกว่า ~1.3x/cell)
  - ⚠️ เคยลอง materialize sheet→numpy (`_FastFrame`) เพื่อทะลุ 30% → **บิลร่วง 836→52 + hash เปลี่ยน → revert ทิ้งแล้ว** (ไม่อยู่ในแพ็กนี้)

## 5) ค้างอยู่ (roadmap ที่เหลือ)
- **OBJ-0** *(รอผู้ใช้)* — เปลี่ยน VAT002 tolerance `1.00 → 0.50` (ผู้ใช้เลือก 0.50 แล้ว แต่ยังไม่ลงมือ)
  - ผลกระทบข้อมูลจริง: **0 ใบ** (golden ไม่ขยับบนข้อมูลปัจจุบัน) ; ถ้าใช้ 0.01 = ฟ้องเพิ่ม 4 ใบ (ต้อง regen baseline)
  - **patch** (`rules_engine.py` ใน `r_vat002`):
    ```diff
    -     if diff < Decimal('1.00'):
    +     if diff < Decimal('0.50'):   # OBJ-0: ตรงกฎ "ยอมต่างปัดเศษ ≤0.50"
              return []
    ```
  - ขั้นตอน: รัน `regression_full.py . /mnt/project` → ถ้า hash เท่าเดิม จบ ; ถ้าเปลี่ยน(กรณี 0.01) และยอมรับ → `python golden_master.py . baseline.json /mnt/project` (regen + บันทึกเหตุผล)
- **ชุดเสริมเกราะ (เสนอไว้ — ความเสี่ยง golden = 0)** ลำดับแนะนำ P1→P3→P2→P4:
  - **P1**: `INVARIANTS/DECISIONS.md` + golden เป็น git pre-commit hook
  - **P2**: เปิด `coverage --branch` บน 4 โมดูลแกน + ปรับ gate (ตัวเลขจะตกจาก line→branch — วัดก่อนตั้งเกณฑ์)
  - **P3**: parse-rate canary (เตือนถ้าจำนวนบิล/อัตรา parse ร่วง >X% — จับ regression แบบ 836→52 โดยไม่พึ่ง golden)
  - **P4**: OBJ-0 (ข้างบน)
- **OBJ-PERF (เต็ม)** — materialization แบบ instrument ทีละ pandas op (รอบเฉพาะ, golden-verify ทุกก้าว) + parallel mode (serial==parallel)
- **OBJ-MAINT** *(ท้ายสุด ตามที่ผู้ใช้กำหนด)* — ซอย parser/rules_engine/reporting ให้ ≲600/ไฟล์ (pure extraction + re-export, golden-verify)

## 6) กฎการทำงาน (ต้องรักษา)
1. ทำทีละ step → commit → **ผู้ใช้รันยืนยันผลจริง** → ค่อยไปต่อ ; **ห้ามอ้างว่า test/hash ผ่านจนผู้ใช้วางผลกลับ**
2. ส่งไฟล์เต็ม/diff (ระบุ path+บรรทัด) + คำสั่ง terminal (ระบุ OS)
3. ห้ามเปลี่ยน business logic เงียบ ๆ (กฎโดเมน/threshold = ผู้ใช้ตัดสิน) ; เปลี่ยน engine/baseline = ผู้ใช้สั่งเท่านั้น
4. ตอบเป็นไทยเสมอ ; persona = Principal Architect + Reliability Engineer + Code Auditor (ดูแล 10 ปี)
5. เกราะตัวจริง = **golden master + pin tests** (coverage วัด "บรรทัดถูกรัน" ไม่ใช่ "บั๊กถูกจับ")

## 7) แผนที่ไฟล์สำคัญ
```
ปุ้มปุ้ย_ultimate_v9_modular.py   engine (parse_all_files มี file_guard ; run_audit_core แช่แข็ง)
parser.py / rules_engine.py / validators.py / puopuy_units.py   โมดูลแกน (coverage ≥90%)
reporting.py                      เขียน Excel (ผลตรวจหลัก)
agents/                           orchestrator, mesh, contracts, base, *_agent, verification_lenses, llm_provider, notepad_report
offline_guard.py / file_guard.py  นโยบายออฟไลน์ + กันไฟล์ untrusted
webverify.py                      product-verification (offline gate)
golden_master.py / verify_golden.py / regression_full.py / coverage_gate.py   ตาข่าย
run_ci.sh                         รันทุกขั้น ([1]-[6],[3*],[9]pip-audit,[10]-[13] coverage/ruff/black/mypy,[7-8] real data)
pyproject.toml / mypy.ini         config lint/type
tests/fixtures/                   fixture_invoices.xlsx + baseline_fixture.json
master_companies.json             ทะเบียนบริษัท (ภ.พ.20)
```
