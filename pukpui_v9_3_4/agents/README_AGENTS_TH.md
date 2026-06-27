# สถาปัตยกรรม Multi-Agent — ปุ้มปุ้ย v9

เอกสารนี้อธิบายการแปลงระบบตรวจสอบบิล "ปุ้มปุ้ย v9" ให้เป็นสถาปัตยกรรม **7 agent**
ตามที่ขอ โดยคงหลักการสำคัญ: **ผลลัพธ์ใน Excel เหมือนเดิมเป๊ะ (พิสูจน์ได้)** และ
**เพิ่มความแม่นยำ** ผ่านการตรวจทานหลายชั้น

> สรุปสั้นสุด: เราไม่ได้เขียนเครื่องยนต์ใหม่ เรา **ห่อ** เครื่องยนต์เดิมที่พิสูจน์แล้ว
> ด้วยชั้น agent บาง ๆ — ผลตรวจที่ออก Excel ยังวิ่งผ่านโค้ดเดิมชุดเดียว ลำดับเดิมเป๊ะ
> ส่วน agent ตรวจทานทำหน้าที่ "ผู้ตรวจคนที่สอง" ที่ออกได้แค่ **คำแนะนำ (advisory)**

---

## 1. ข้อค้นพบสำคัญที่ต้องเข้าใจก่อน (ตรงไปตรงมา)

**การจัดระเบียบโค้ด deterministic ชุดเดิมใหม่เป็น agent — โดยตัวมันเอง — ทำให้ "ตัวเลขแม่นขึ้น" ไม่ได้**
นี่คือเหตุผลเดียวกับที่ทำให้ "ผลเหมือนเดิมใน Excel" เป็นไปได้: ถ้า logic เท่าเดิม input เท่าเดิม
ผลย่อมเท่าเดิม การหั่นงานใส่กล่อง agent ไม่เปลี่ยนเลขคณิต

ดังนั้น "ความแม่นขึ้น" ที่ทำได้จริงมาจาก 2 ทางที่ **ไม่แตะผลตรวจหลัก**:

1. **การตรวจสอบไขว้อย่างอิสระ (independent cross-validation)** — Formula/VAT/TaxID agent
   คำนวณซ้ำ/ตรวจซ้ำในมุมที่กฎแบบ single-pass อาจมองข้าม (เช่น บิลที่ระบบหลักไม่ขึ้น issue
   แต่ยอดถูก "อนุมาน" มา — agent ชี้ให้คนไปดู) และตรวจข้ามบิล (เช่น เลขผู้เสียภาษีซ้ำข้ามบริษัท)
   ซึ่ง single-pass ทำไม่ได้
2. **AI Review Agent เป็นความเห็นที่สอง (second opinion)** — ช่วย "จัดลำดับความเสี่ยง + อธิบาย"
   ให้คนตรวจไปดูจุดสำคัญก่อน

ทั้งสองทางออกผลเป็น **findings เชิงคำแนะนำ** ให้มนุษย์ตัดสินใจ — ไม่มีตัวไหนไปแก้ตัวเลขใน Excel
นี่คือเหตุผลที่ทำให้ทั้ง "เหมือนเดิม" และ "ช่วยให้แม่นขึ้น" อยู่ด้วยกันได้โดยไม่ขัดกัน

---

## 2. แผนผัง 7 Agent (DAG)

```
                 reset_run_state()  (ล้าง cache ที่ใช้ร่วม)
                        │
            ┌───────────▼────────────┐
            │  1. ImportAgent (CRIT) │  ค้นไฟล์ + parse → บิล + filename_issues
            └───────────┬────────────┘
                        │
        ╔═══════════════▼════════════════════════════════╗
        ║      _run_audit_core()  ⭐ ครั้งเดียว เท่านั้น    ║   ← ผลตรวจ "ทางการ" (ที่ออก Excel)
        ║  check_duplicate_items → run_all_rules →        ║      ลำดับเป๊ะตาม main()/golden_master
        ║  check_invoice_sequence + check_iv_date_sequence ║      จึง byte-identical
        ║  → check_product_typos → summarize_by_company    ║
        ║  → apply_iv_period_crosscheck                    ║
        ║  → apply_sheet_date_crosscheck                   ║
        ╚═══════════════╤════════════════════════════════╝
                        │   (อ่านอย่างเดียว — ไม่แก้บิล)
        ┌───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼
  2.FormulaAgent   3.VatAgent      4.WhtAgent      5.TaxIdAgent     (review, ไม่ critical)
        └───────────────┴───────┬───────┴───────────────┘
                                ▼
                       6. AiReviewAgent (Local LLM, ไม่ critical)   ← อ่าน findings ข้างบน + triage
                                │
                                ▼
                       7. ReportAgent (CRIT)   ← เขียน Excel (เหมือนเดิม)
```

| # | Agent | ชนิด | critical | หน้าที่ | แก้บิล? |
|---|-------|------|:--------:|--------|:------:|
| 1 | **ImportAgent** | Python | ✓ | ห่อ `parse_all_files` + `compute_bill_confidence`; ตรวจไฟล์หาย/ว่าง | เขียน ctx.bills |
| 2 | **FormulaAgent** | Python | ✗ | ตรวจซ้ำ: Σ(items)≈subtotal, subtotal×7%≈vat, subtotal+vat≈total, ธงยอด "อนุมาน" | ❌ อ่านอย่างเดียว |
| 3 | **VatAgent** | Python | ✗ | รวบผล VAT* จากกฎหลัก + ชี้ false-clean (vat อนุมาน แต่ไม่มี issue) | ❌ |
| 4 | **WhtAgent** | Python | ✗ | ห่อ `addon_check_withholding` เดิม (ภงด.53) → candidates | ❌ |
| 5 | **TaxIdAgent** | Python | ✗ | checksum mod-11 อิสระ + เลขภาษีซ้ำข้ามบริษัท (cross-bill) | ❌ |
| 6 | **AiReviewAgent** | Local LLM | ✗ | จัดลำดับความเสี่ยง + อธิบายรายการที่ถูกธง (advisory) | ❌ |
| 7 | **ReportAgent** | Python | ✓ | ห่อ `build_clean_report`/`export_excel` → ไฟล์ Excel | ❌ |

**critical = ✓** หมายถึง พังแล้วหยุดทั้งสาย (ไม่มีบิล/เขียนรายงานไม่ได้ = ส่งงานไม่ได้)
**critical = ✗** หมายถึง พังแล้ว log + ไปต่อ (review/AI เป็นส่วนเสริม ทิ้งได้) — สะท้อนปรัชญา
`P1-FIX-ISOLATION` ของระบบเดิมที่แยก try/except ราย validator

---

## 3. ทำไมจึง "เหมือนเดิมเป๊ะ" — และพิสูจน์อย่างไร

ผลตรวจที่กลายเป็น Excel วิ่งผ่าน **`_run_audit_core()` ในไฟล์ `agents/orchestrator.py`**
ซึ่งคัดลอกลำดับการเรียกฟังก์ชันมาจาก `main()` (บรรทัด ~4782–4844) และ `golden_master.py`
**บรรทัดต่อบรรทัด** — ไม่มีการรันกฎซ้ำ ไม่มีการสลับลำดับ

agent ฝั่ง review อ่าน `bill['issues']` ที่กฎหลักตรวจแล้ว (ผ่าน `issues_with_prefix`) แทนการ
รันกฎเอง — เพราะลำดับ issue เป็นส่วนหนึ่งของ "สัญญา byte-identical" ถ้ารันใหม่จะสลับลำดับ → hash เปลี่ยน

### พิสูจน์ด้วย `verify_golden.py`

```bash
PYTHONHASHSEED=0 python3 verify_golden.py . baseline.json /path/to/data
```

สคริปต์นี้:
1. รัน **orchestrator เต็ม** (เปิด agent review ครบ + AI review แบบ mock)
2. ดึงผลจาก ctx มา serialize ด้วย `canonical()` **ชุดเดียวกับ `golden_master.py`**
3. คำนวณ SHA256 สูตรเดียวกัน แล้วเทียบกับ baseline (ที่ทำจาก "ทางเดิม")

**ผลที่ได้จริงกับข้อมูลจริง 81 ไฟล์ / 632 บิล:**

```
SHA256 (agent)  : 7b60b01fa76438c6fd1db795da6f8b8b9ad62e2a63de6fc1f92a2feb8cf04e5d
SHA256 baseline : 7b60b01fa76438c6fd1db795da6f8b8b9ad62e2a63de6fc1f92a2feb8cf04e5d
✅ ผ่าน — hash ตรงทุก field
```

เพราะ hash ยังตรง **ทั้งที่รัน agent review + AI ครบแล้ว** จึงพิสูจน์ได้ 2 อย่างพร้อมกัน:
ผลหลักเหมือนเดิม **และ** agent ตรวจทาน/AI ไม่ได้ไปแก้ไขบิลแม้แต่ field เดียว

---

## 4. AI Review Agent — สัญญาความปลอดภัย (advisory เท่านั้น)

AI agent ออกแบบให้ "ช่วยคน" ไม่ใช่ "แทนกฎ" มีกติกาเหล็ก 5 ข้อ (บังคับในโค้ด):

1. **ไม่แก้ ctx.bills / ไม่แตะ Excel** — ผลออกเป็น findings (`AI-SUMMARY`, `AI-TRIAGE`) เท่านั้น
2. **ห้าม LLM คำนวณยอด หรือชี้ผ่าน/ไม่ผ่านแทนกฎ** — ทำได้แค่จัดลำดับ + อธิบาย (กำหนดใน system prompt)
3. **degrade graceful** — ถ้าต่อ Local LLM ไม่ได้ (probe ไม่ผ่าน) → `status=skipped`, pipeline เดินต่อปกติ
4. **คำตอบ LLM = ข้อความที่ไม่เชื่อถือ (untrusted)** → parse แบบกันพัง (ทน ```json / ข้อความนำ)
5. **จำกัดขนาด prompt** — ส่งเฉพาะรายการที่ถูกธงแล้ว (default สูงสุด 60 รายการ) ไม่ dump ทุกบิล

### Provider ที่รองรับ (`agents/llm_provider.py`, ใช้ stdlib ล้วน ไม่เพิ่ม dependency)

| provider | ใช้กับ | endpoint | หมายเหตุ |
|----------|--------|----------|---------|
| `ollama` (ค่าเริ่มต้น) | **Ollama** (Local LLM) | `http://localhost:11434/api/chat` | แนะนำสำหรับเครื่อง local |
| `openai` | **llama.cpp / LM Studio** | `/v1/chat/completions` | OpenAI-compatible |
| `mock` | ทดสอบ | – | คืน JSON จำลอง deterministic (ไม่ต้องมีโมเดล) |
| `null` | offline | – | available()=False → AI skipped |

ตัวอย่างเปิดใช้ Local LLM จริง:

```bash
python3 run_agents.py --data ./bills --ai \
    --llm-provider ollama --llm-model llama3.1 \
    --llm-base-url http://localhost:11434
```

> ⚠️ **ข้อจำกัดการทดสอบ:** ในแซนด์บ็อกซ์ที่สร้างระบบนี้ **ทดสอบกับ Local LLM จริงไม่ได้**
> (ไม่มี Ollama ติดตั้ง ไม่มี weight ของโมเดล และเครือข่ายถูกจำกัด) จึงพิสูจน์ "สายเชื่อม"
> ด้วย `MockProvider` (จบ end-to-end ได้ JSON → findings) และพิสูจน์ "เส้นทาง degrade"
> ด้วย `NullProvider` (skipped อย่างสง่างาม) — เมื่อนำไปรันบนเครื่องที่มี Ollama จริง
> เพียงตั้ง `--llm-provider ollama` ก็ทำงานทันที

---

## 5. การทดสอบเชิงสถาปัตยกรรม (`test_agents.py`)

```bash
PYTHONHASHSEED=0 python3 test_agents.py . /path/to/data
```

ครอบคลุม (ผ่านทั้งหมด 9/9 กับข้อมูลจริง):

- **A) Error isolation** — บังคับให้ FormulaAgent พัง → ได้ `status=error`, แต่ VatAgent และ
  ReportAgent **ยังทำงาน**, Excel **ยังออก** (พิสูจน์ว่า agent เสริมพังไม่ล้มงานหลัก)
- **B) AI degrade** — `provider=null` → AI `skipped`, agent อื่นครบ; ปิด AI ก็ `skipped`
- **C) Report จริง** — เปิด `write_report` → ได้ `.xlsx` ที่เปิดด้วย openpyxl ได้จริง (9 ชีต)

---

## 6. ข้อค้นพบระหว่างทาง: path รายงานใน main() ยัง hardcode

`HANDOVER.md` ระบุว่าได้แก้ path รายงานที่ผูกกับ Windows แล้ว แต่จริง ๆ ใน `main()`
(บรรทัด ~4834 ของ `ปุ้มปุ้ย_ultimate_v9_modular.py`) **ยังมี** ค่าเริ่มต้นเป็น
`r'C:\Users\User\Desktop\รีพอร์ต'` (มี env override แต่ default ยังเป็น path Windows)

`ReportAgent` ใหม่จึงใช้ค่าเริ่มต้นแบบ **พกพาได้** แทน ลำดับความสำคัญ:
`options['report_dir']` → env `PUKPUI_REPORT_DIR` → `./audit_reports`

นี่เป็น **config ไม่ใช่ logic** จึงไม่กระทบผลตรวจ (golden_master จับ fingerprint ของ "ข้อมูลผล"
ก่อนขั้นเขียนไฟล์) — แต่ทำให้ระบบรันข้ามเครื่อง/ข้าม OS ได้โดยไม่ต้องแก้โค้ด

---

## 7. วิธีใช้งานโดยสรุป

```bash
# ตรวจโฟลเดอร์ แล้วออก Excel แบบคลีน (ค่าเริ่มต้น) + ไฟล์ findings (advisory)
python3 run_agents.py --data ./bills --report-dir ./out

# โหมดเต็ม (export_excel + ภงด.53)
python3 run_agents.py --data ./bills --full --report-dir ./out

# เปิด AI review (ต้องมี Ollama/LM Studio ที่เครื่อง)
python3 run_agents.py --data ./bills --ai --llm-provider ollama --llm-model llama3.1

# พิสูจน์ว่าเหมือนเดิม (เทียบ baseline)
PYTHONHASHSEED=0 python3 verify_golden.py . baseline.json ./bills

# ทดสอบสถาปัตยกรรม
PYTHONHASHSEED=0 python3 test_agents.py . ./bills
```

**โครงไฟล์ที่เพิ่ม** (ของเดิมไม่ถูกแก้ logic):

```
agents/
  __init__.py          export ทุก agent + orchestrator
  contracts.py         PipelineContext / AgentResult / Finding (โครงข้อมูลกลาง)
  base.py              Agent ABC (error-boundary + timing สม่ำเสมอ)
  core_access.py       ประตูเดียวสู่เครื่องยนต์เดิม + import gate
  import_agent.py      (1) Import
  formula_agent.py     (2) Formula
  vat_agent.py         (3) VAT
  wht_agent.py         (4) WHT
  taxid_agent.py       (5) TaxID
  report_agent.py      (7) Report
  llm_provider.py      ตัวเชื่อม Local LLM (ollama/openai/mock/null) — stdlib ล้วน
  ai_review_agent.py   (6) AI Review
  orchestrator.py      ⭐ ร้อย DAG + _run_audit_core (ลำดับศักดิ์สิทธิ์)
run_agents.py          entrypoint ไม่โต้ตอบ (แทน main() ที่ใช้ input())
verify_golden.py       พิสูจน์ byte-identical (เทียบ baseline)
test_agents.py         ทดสอบ isolation / degrade / report
```
