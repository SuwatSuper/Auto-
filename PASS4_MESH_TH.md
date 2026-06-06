# พาส 4 — Hybrid Hierarchical + Mesh (ยกระดับ agent ทั้งระบบ)

เอกสารนี้สรุปงานพาส 4: ยกระดับสถาปัตยกรรม multi-agent จาก **Hierarchical ล้วน**
(orchestrator → review อิสระ → report) ให้เป็น **Hybrid Hierarchical + Mesh** ที่ agent
"คุยกันได้" ผ่านกระดานกลาง (mesh) เพื่อให้ฉลาดขึ้น/แม่นขึ้น โดย **ผลตรวจหลักเหมือนเดิม 100%**.

> **พิสูจน์แล้ว 3 ด่าน (ชุดข้อมูล /mnt/project — 32 ไฟล์ / 192 บิล):**
> - oracle หลัก `41cf259a…` ✅ (บิล + issue + summary)
> - oracle ขยาย `168891d7…` ✅ (system_issues + rules state)
> - agent path (verify_golden) ✅ — รัน agent ครบ 9 ตัว, hash ตรง baseline
>
> agent ทุกตัวฝั่ง review/synthesis เป็น **advisory (read-only)** → Excel byte-identical.

---

## 1. ภาพรวมสถาปัตยกรรม: 2 ระนาบ (plane)

```
                         CONTROL PLANE (Hierarchical)
                         orchestrator คุมลำดับแบบ deterministic
                         → ลำดับรันคงที่ → hash ผลตรวจไม่แกว่ง
   ┌─────────────────────────────────────────────────────────────────┐
   │  reset_run_state                                                  │
   │    └─ ImportAgent (critical) ──► _run_audit_core ⭐ (รันครั้งเดียว) │
   │         │                         = ผลที่ออก Excel (byte-identical) │
   │         ├─ Tier-1: formula · vat · wht · taxid   (review อิสระ)    │
   │         ├─ Tier-2: crosscheck · confidence       (correlation)     │
   │         ├─ Tier-2.5: ai_review                   (triage รายบิล)   │
   │         ├─ Tier-3: synthesis                     (สรุปภาพรวม) ★    │
   │         └─ ReportAgent (critical)                (เขียน Excel)      │
   └─────────────────────────────────────────────────────────────────┘
                                   │ publish/subscribe (Finding เท่านั้น)
                                   ▼
                         DATA PLANE (Mesh)
                         FindingsMesh — กระดานกลาง append-only
                         index หลายมิติ: by_agent / by_bill / by_severity / by_code
```

**แยก 2 ระนาบทำไม:**
- *Control plane (ลำดับ)* คงที่ → รับประกัน reproducibility ของผลตรวจ (hash)
- *Data plane (mesh)* ให้ agent เห็นงานของกันและกัน → ฉลาดขึ้น โดยไม่ไปยุ่งกับลำดับ/ผลหลัก

---

## 2. Mesh (data plane) — `agents/mesh.py`

`FindingsMesh` = กระดานกลางที่ทุก agent publish "findings" (ข้อสังเกตเชิงคำแนะนำ) เข้าไป
และ query ได้หลายมิติ. **ขนส่งเฉพาะ Finding — ไม่เคยถือ/แตะ `ctx.bills`** → ปลอดภัยต่อ byte-identical.

คุณสมบัติเด่น:
- **append-only ต่อรอบ**: publish ได้ ลบไม่ได้ → agent ตัวหลังไม่ "ลบ/แก้" งานตัวหน้า (กันผลแกว่ง)
- **publish อัตโนมัติ**: `ctx.record(result)` ใน orchestrator publish findings เข้า mesh ให้เลย
  → ลำดับ publish = ลำดับ record (deterministic ตาม control plane)
- **query deterministic**: ทุกเมธอดเรียงผลด้วย key คงที่ → tier-2/3 ที่อ่าน mesh ทำซ้ำได้
- **error-isolated**: mesh พัง = `record()` กลืน ไม่ล้ม pipeline (เป็น advisory plane)

เมธอดสำคัญ:
| เมธอด | ใช้ทำอะไร |
|---|---|
| `publish(findings)` | ลง findings + อัปเดต index ทุกมิติ |
| `by_agent(*names)` / `by_bill(f,s,iv)` / `by_severity(*s)` / `by_code_prefix(*p)` | query ตามมิติ |
| `correlate_by_bill(min_agents=2)` | **หัวใจ mesh**: บิลที่ ≥N ผู้ตรวจอิสระธงตรงกัน → priority สูง |
| `since(seq)` / `count()` | cursor: อ่าน "ของใหม่หลังจุดหนึ่ง" |
| `stats()` | สรุปเชิงตัวเลขลง summary |

---

## 3. agent ใหม่ที่เพิ่ม (ยกระดับทั้งระบบ)

### Tier-2 — correlation (mesh consumers)
- **CrossCheckAgent** (`crosscheck_agent.py`): อ่าน mesh หาบิลที่หลาย Tier-1 ธงตรงกัน →
  ออก finding `CROSS-CONFIRM` (cross-validated = น่าเชื่อกว่า single agent)
- **ConfidenceAgent** (`confidence_agent.py`): ให้ "คะแนนความเชื่อมั่นรวมต่อบิล" จากหลักฐานทั้ง mesh
  (ถ่วงน้ำหนัก severity + จำนวน agent + parser confidence) → ออก `CONF-SCORE`, จัดอันดับงานตรวจ.
  **สูตรโปร่งใส ตามรอยได้ ไม่ใช่กล่องดำ.**

### Tier-3 — synthesis capstone (mesh + Local LLM)
- **SynthesisAgent** (`synthesis_agent.py`): อ่าน mesh ที่ "ตกผลึกแล้ว" (รวมสัญญาณ Tier-2)
  แล้วสังเคราะห์เป็น **บทสรุปเชิงบริหารทั้งงานตรวจ** — `AI-SYNTH-OVERVIEW / -THEME / -FOCUS`
  - มี LLM → เขียนบทสรุปเชิงบริหารภาษาคน (headline / overview / themes / focus)
  - ไม่มี LLM → **statistical mode** (degrade graceful): สรุปจากสถิติ mesh แบบ deterministic
  - ต่างจาก ai_review: ai_review = triage *รายบิล*, synthesis = ภาพรวม *ทั้งชุดงาน*

---

## 4. ทำไม "แม่นขึ้น / ฉลาดขึ้น" (ไม่ใช่แค่เพิ่มไฟล์)

1. **Cross-agent corroboration** — ประเด็นที่ผู้ตรวจอิสระหลายตัวเห็นตรงกัน ถูกยกเป็น priority
   อัตโนมัติ (เช่น บิลที่ทั้ง formula+vat+taxid+confidence+crosscheck ธาย = ดูก่อน). เดิมแต่ละ
   finding แยกกัน คนต้องรวมหัวเอง.
2. **คะแนนเดียวต่อบิล** — ConfidenceAgent รวมหลักฐานเป็นคะแนนเทียบกันได้ → จัดคิวงานตรวจได้ทันที.
3. **สรุปเชิงบริหาร** — SynthesisAgent ยกจาก "รายการ findings ดิบ" เป็น "ข้อสรุปที่ลงมือต่อได้"
   (รูปแบบปัญหาเด่น, จุดที่ควรโฟกัส).
4. **AI second opinion** — ai_review + synthesis ใช้ Local LLM (privacy: ไม่ส่งข้อมูลออกเครื่อง)
   ช่วยจับ false-clean ที่กฎ deterministic มองข้าม — แต่ **ไม่มีสิทธิ์ตัดสินผ่าน/ไม่ผ่าน** (กฎคือกฎ).

---

## 5. กฎเหล็กที่ยังคงไว้ (ความปลอดภัย)

- ผลตรวจที่ออก Excel วิ่งผ่าน `_run_audit_core` **ครั้งเดียว** ในลำดับศักดิ์สิทธิ์ → hash คงที่.
- agent ฝั่ง review/synthesis **อ่านอย่างเดียว** — แตะแค่ findings (advisory) ไม่ mutate bills.
- error-isolation: agent ไม่ critical พัง → log + ไปต่อ; mesh พัง → กลืน ไม่ล้ม pipeline.
- LLM degrade graceful: ไม่มี/ต่อไม่ได้ → ระบบยังรันครบ (synthesis ใช้ statistical mode).
- ทุกการเปลี่ยนแปลงพิสูจน์ด้วย dual-oracle (`41cf259a…` + `168891d7…`) + agent path.

---

## 6. การพิสูจน์ซ้ำ

```bash
# oracle หลัก + ขยาย (ผลตรวจ byte-identical)
python3 golden_master.py    . out.json  /path/to/data   # ต้องได้ 41cf259a…
python3 golden_master_v2.py . out2.json /path/to/data   # ต้องได้ 168891d7…

# agent path เต็ม (รัน 9 agent + ยืนยัน hash + เห็น synthesis ทำงาน)
PYTHONHASHSEED=0 python3 verify_golden.py . out.json /path/to/data
```
