# ปุ้มปุ้ย v9.1 — Reliability Pass (ชุดประกอบรวม)

เอกสารนี้สรุป **ทุกการเปลี่ยนแปลง** ในชุดนี้ + วิธีรัน/พิสูจน์ บนเครื่องตัวเอง (VS Code, offline)

> **หลักประกันสำคัญ:** GOLDEN MASTER ไม่เปลี่ยน — ผลตรวจหลัก hash =
> `ec61907fd8061bd314b4e4c573a40f4564184936e292c8d6323b5278239e4628`
> ทั้งเส้น engine และเส้น agent (พิสูจน์แล้วทุกการแก้ใน README นี้)

---

## 1) สิ่งที่แก้/เพิ่ม (16 ไฟล์)

### A. OBJ-1A — แก้สูตร `_vat_tolerance` (bugfix สำคัญ)
- ไฟล์: `puopuy_units.py`, `test_pinned_logic.py`, `smoke_test.py`, `REBUILD_STATUS_TH.md`, `P3_FOLLOWUP_TH.md`
- เดิมเป็นสูตรประมาณ `max(1.00, 0.005·|subtotal|)` → **หลวมเกินจริง 83–484 เท่า** (false-negative landmine)
- แก้กลับเป็นสูตรที่เอกสารกำหนด: **`0.5 + |subtotal| / 100000`**
- พิสูจน์: บิลจริง 631 ใบ reconcile ≤1e-10 → VAT001 fire = 0 ทั้งสองสูตร → **hash ไม่เปลี่ยน**

### B. FINDING #1 — matplotlib import แบบ optional
- ไฟล์: `ปุ้มปุ้ย_ultimate_v9_modular.py`
- เดิม import matplotlib แบบ hard ทั้งที่ version_gate จัดเป็น "degradeable" → จะ crash ถ้าไม่มี
- แก้: ห่อ try/except → `plt=None` + guard (ตรงกับ pattern ของ `reporting.py`)
- พิสูจน์: มี matplotlib → hash เท่าเดิม; จำลองไม่มี → import ผ่าน parse ได้ไม่ crash

### C. OBJ-1D — ชุดทดสอบความทนทาน + coverage
ไฟล์ใหม่:
- `test_parser_negative.py` (23) — ไฟล์เสีย/ว่าง/ขยะ/xlsx พัง → ไม่ crash + SYS001; good+bad ปนกัน → บิลดีอยู่ครบ
- `test_parser_helpers.py` (60) — unit ฟังก์ชันบริสุทธิ์ของ parser (parse_filename, _cell_to_num, IV/taxid/address, _detect_vat_rows, _is_tor_format ...) + edge/fuzz
- `test_rules_coverage.py` (9) — ขับ `run_rules` ด้วยบิลบกพร่อง 37 แบบ → ไม่มีกฎ throw + กฎสำคัญ fire ถูกจังหวะ + เรียกกฎที่ปิดอยู่ตรง ๆ
- `test_validators.py` (20) — IV sequence/date/period mismatch/typo/duplicate ถูกต้อง + ทนทาน

**Coverage ปัจจุบัน** (วัดรวม golden_master + unit tests):

| โมดูล | ก่อน | ตอนนี้ | เป้า |
|---|---|---|---|
| puopuy_units.py | 91% | **91%** ✅ | ≥90 |
| validators.py | 86% | **89%** | ≥90 |
| parser.py | 76% | **82%** | ≥90 |
| rules_engine.py | 72% | **81%** | ≥90 |

> parser/rules_engine ยังไม่ถึง 90% — บรรทัดที่เหลือเป็น branch ลึก (layout xlsx แปลก/เงื่อนไขกฎหายาก)
> ต้องสร้าง fixture เต็มใบเฉพาะทาง = งานโฟกัสรอบถัดไป (ไม่ปั๊มด้วย test ขยะ)

### D. ฟีเจอร์ใหม่ — VerificationAgent ("ยืนยัน Error ก่อนฟันธง")
- ไฟล์: `agents/verification_agent.py` (ใหม่), `agents/orchestrator.py` (wire เข้า Tier-2), `agents/notepad_report.py` (แสดงผล), `test_verification_agent.py` (8)
- เอา Error ของ engine แต่ละตัวมาผ่าน **6 เลนส์อิสระ → supervisor รวมเป็น consensus per-Error**
  - L1 recompute · L2 provenance · L3 parse-confidence · L4 peer-consistency · L5 rule-class · **L6 LLM (opt-in)**
  - ผล: `CONFIRMED` (score≥+2) / `NEEDS_REVIEW` / `LIKELY_FALSE_POSITIVE` (≤−1)
- **ADVISORY ล้วน** — ไม่แตะ `b['issues']`/ผลหลัก → hash ไม่เปลี่ยน (พิสูจน์: agent_hash = ec61907f)
- บนข้อมูลจริง: 18 Error → 2 CONFIRMED / 16 NEEDS_REVIEW / 0 false-positive
- **L6 (LLM lens) offline-safe:** เปิดด้วย `options['verify_use_llm']=True` เท่านั้น + ต้อง probe LLM ติด
  เครื่อง offline → L6 งดออกเสียงเสมอ → consensus/hash เท่าเดิม (ถ้าต่อ Ollama เมื่อไหร่ค่อยทำงาน)

### E. CI
- `run_ci.sh` + `.github/workflows/ci.yml`: เพิ่มด่าน `[3b]`–`[3f]` (negative/fuzz, rules, verification, helpers, validators)

---

## 2) วิธีรัน / พิสูจน์บนเครื่องตัวเอง (offline)

ตั้ง env ให้ผลนิ่ง (สำคัญ): `PYTHONHASHSEED=0` และ `PUOPUY_AUDIT_DATE=2026-06-02`
แทน `<DATA>` ด้วยโฟลเดอร์ที่มีไฟล์ .xls/.xlsx จริง (78+3 ไฟล์)

### macOS / Linux
```bash
export PYTHONHASHSEED=0
export PUOPUY_AUDIT_DATE=2026-06-02
python3 test_pinned_logic.py            # ต้องเห็น PINNED: ผ่าน 49
bash run_ci.sh                          # ต้องเขียวทุกด่าน
python3 regression_full.py . "<DATA>"   # ต้องเห็น RESULT ✅ (engine==agent==baseline)
```

### Windows (PowerShell)
```powershell
$env:PYTHONHASHSEED="0"
$env:PUOPUY_AUDIT_DATE="2026-06-02"
python test_pinned_logic.py
python regression_full.py . "<DATA>"
```

ผลที่ต้องเห็น: `PINNED ผ่าน 49`, hash `ec61907f…`, `RESULT ✅`

### (ทางเลือก) เปิด LLM lens — เฉพาะถ้ามี Ollama รันอยู่
ส่ง option ตอนเรียก pipeline: `options={'verify_use_llm': True}` (ค่าปริยายปิด/offline = ปลอดภัย)

---

## 3) QA ที่ทำก่อนส่ง (3 รอบ)
- **flaky check:** unit 7 ชุด × 3 รอบ = 196 checks เหมือนกันเป๊ะทุกรอบ — ไม่ flaky
- **determinism:** golden hash 2 รอบ + agent = `ec61907f` ทุกครั้ง, snapshot byte-identical
- **integration:** `run_ci.sh` 11 ด่านเขียวหมด
- **agent audit:** ทุก tier ทำงาน; wht=0 พิสูจน์ว่าไม่มีงานบริการจริง (ไม่ใช่บั๊ก); ai_review skip = ถูกต้อง (offline)
- **perf:** คอขวด = parsing 35s (99%); ชั้น agent <0.01s — เป้าเร่งความเร็วอยู่ที่ parser (OBJ-2)

---

## 4) ลำดับ commit แนะนำ (rollback ง่าย)
```
1) fix(reliability): restore _vat_tolerance 0.5+|sub|/100000 [OBJ-1A]
2) test+fix: parser fuzz/negative + helpers + validators + rules + matplotlib optional [OBJ-1D]
3) feat(agents): VerificationAgent 6-lens consensus + notepad display [verify ec61907f]
4) feat(agents): optional LLM lens (L6, offline-safe) + CI wiring 3b-3f
```

## 5) งานที่ยังเหลือ (roadmap)
- ดัน coverage `parser.py` 82→90 และ `rules_engine.py` 81→90 (ต้อง fixture เต็มใบ) — OBJ-1D ปิดเกณฑ์
- OBJ-2 performance: optimize parser (คอขวด 35s), output-preserving, ≥30% เร็วขึ้น, hash เท่าเดิม
- OBJ-3 scalability / OBJ-4 polish (DRY, mypy+ruff ใน CI)
