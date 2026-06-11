# คู่มือ Mesh — สถาปัตยกรรม Multi-Agent ของปุ้มปุ้ย v9

> คู่มือเชิงลึกของชั้น `agents/` — โดยเฉพาะ **FindingsMesh** (กระดานคำแนะนำกลาง) และวิธีต่อยอด.
> ภาพรวมทั้งระบบ + diagram อยู่ใน `HANDOVER_TH.md`.

---

## 1. Mesh คืออะไร และทำไมต้องมี

สถาปัตยกรรมนี้เป็นแบบ **Hybrid Hierarchical + Mesh** สองระนาบ:

- **Control plane** = `orchestrator.py` — ลำดับชั้น/ดีเทอร์มินิสติก ตัดสิน *"ใครรันเมื่อไหร่"*
- **Data plane** = `mesh.py` (`FindingsMesh`) — ตาข่าย/แนวราบ ตัดสิน *"ใครเห็นผลของใคร"*

**ปัญหาเดิม:** agent อ่านผลเพื่อนผ่าน `ctx.results["ชื่อ"].findings` แบบ ad-hoc → เปราะ
(พิมพ์ชื่อผิด = เงียบ), ไม่มี query แบบ by-bill/by-severity, ไม่มี dedup/provenance, ขยายยาก.

**Mesh แก้โดย:** ให้ "กระดานกลาง" (blackboard) ที่ทุก agent โพสต์/อ่าน finding ผ่าน API เดียว
โดย **ขนเฉพาะ `Finding` (advisory)** — ไม่แตะ `ctx.bills`/ผลตรวจหลัก → Excel ยัง byte-identical.

คุณสมบัติ: *immutable-by-convention* (query คืน list ใหม่เสมอ กันแก้ข้าม agent) และ
*deterministic* (ลำดับ publish ถูกกำหนดโดย orchestrator → ผล query คงที่ ทำซ้ำได้).

---

## 2. โครงสร้างข้อมูล (`contracts.py`)

### Finding — ข้อสังเกตเชิงคำแนะนำ 1 รายการ
```python
Finding(
    agent: str,            # ชื่อ agent ที่ออก (เช่น "formula")
    code: str,             # รหัสภายใน (เช่น "FORMULA-MISMATCH", "CONF-SCORE")
    severity: str = "INFO",# CRITICAL | ERROR | WARNING | INFO
    message: str = "",     # ข้อความภาษาคน
    file: str = "", sheet: str = "", iv: str = "",   # pointer กลับไปยังบิล
    evidence: dict = {},   # ตัวเลข/บริบทประกอบ (ตามรอยได้)
)
```
**กุญแจอ้างอิงบิล** = `f"{file}|{sheet}|{iv}"` — ใช้จับ cross-agent correlation.

### AgentResult — ผลมาตรฐานของ agent ทุกตัว
```python
AgentResult(name, status, summary: dict, findings: list[Finding], error, duration_s)
# status: "ok" | "skipped" | "error"
```

### PipelineContext — สายพานข้อมูลเส้นเดียว
ฟิลด์สำคัญ: `master, file_list, options, bills, summary, iv_issues, iv_seq, iv_date,
typos, dup_items, filename_issues, results{name→AgentResult}, mesh`.
- `ctx.opt(key, default)` — อ่าน option
- `ctx.record(result)` — บันทึกผล **และ publish findings เข้า mesh อัตโนมัติ** (ลำดับ = ลำดับ record)

---

## 3. FindingsMesh API (อ้างอิง)

```python
mesh.publish(findings: list[Finding]) -> int
    # โพสต์เข้า mesh, คืนจำนวนที่รับ. ของที่ไม่ใช่ Finding ถูกข้าม (ไม่ throw)

# ---- query (คืน list ใหม่เสมอ) ----
mesh.all() -> list[Finding]                     # ทุก finding ตามลำดับ publish
mesh.by_agent(*names) -> list[Finding]          # ของ agent ที่ระบุ
mesh.by_severity(*sev) -> list[Finding]         # เช่น by_severity("CRITICAL","ERROR")
mesh.by_code(*codes) -> list[Finding]           # ตรง code
mesh.by_code_prefix(*prefixes) -> list[Finding] # code ขึ้นต้นด้วย (เช่น "AI-","VAT")
mesh.by_bill(file, sheet, iv) -> list[Finding]  # ทุก finding ของบิลใบเดียว
mesh.since(seq: int) -> list[Finding]           # ตั้งแต่ index seq (อ่าน "ของใหม่")
mesh.count() -> int                             # จำนวนปัจจุบัน (ใช้เป็น cursor ให้ since)
mesh.agents_seen() -> list[str]                 # รายชื่อ agent ที่โพสต์ (เรียง)

# ---- correlation (หัวใจ mesh) ----
mesh.correlate_by_bill(min_agents=2) -> list[dict]
    # จับบิลที่ >= min_agents ธงพร้อมกัน. คืน (เรียง: agent มาก→น้อย, severity, bill key):
    #   {"file","sheet","iv","agents":[...],"n_agents":k,
    #    "codes":[...],"max_severity":"...","findings":[Finding...]}

mesh.stats() -> dict
    # {"total","agents","bills_touched","sev_CRITICAL","sev_ERROR",...}
```

**ตัวอย่าง:** หาบิลที่ ≥3 ผู้ตรวจอิสระเห็นตรงกัน และมีอย่างน้อยหนึ่ง CRITICAL
```python
for row in ctx.mesh.correlate_by_bill(min_agents=3):
    if row["max_severity"] == "CRITICAL":
        print(row["file"], row["sheet"], row["iv"], row["agents"])
```

---

## 4. โมเดล Tier (ใครอ่าน/เขียนอะไร)

| Tier | agents | อ่านจาก | เขียน (publish) |
|---|---|---|---|
| 1 | formula, vat, wht, taxid | `ctx.bills` + issue หลัก | findings ของตน → mesh |
| 2 | crosscheck, confidence | **mesh** (ผล Tier-1) | `CROSS-CONFIRM` / `CONF-SCORE` |
| 2.5 | ai_review | mesh (รวม Tier-2) + bills | findings AI (รายบิล) |
| 3 | synthesis | **ทั้ง mesh** (ตกผลึก) | `AI-SYNTH-*` (สรุปเชิงบริหาร) |
| 4 | super | mesh + `ctx.results` | `SUPER-*` (กำกับระบบ) |

ลำดับนี้ "คงที่" ใน `orchestrator.py` เพื่อให้ผล mesh เสถียร (เช่น confidence ต้องเห็น cross-confirm
ก่อน, super ต้องเห็นครบทุก tier ก่อน).

---

## 5. สารบบรหัส finding (codes)

| code | agent | ความหมาย |
|---|---|---|
| `FORMULA-*` | formula | ผลรวม/ภาษีไม่ตรงเชิงเลขคณิต |
| `VATX` ฯลฯ | vat | ประเด็น VAT |
| `WHT-*` | wht | ภาษีหัก ณ ที่จ่าย |
| `TAXID-*` | taxid | checksum/ซ้ำข้ามบริษัท |
| `CROSS-CONFIRM` | crosscheck | บิลที่หลายผู้ตรวจอิสระธงตรงกัน |
| `CONF-SCORE` | confidence | คะแนนความเชื่อมั่นความเสี่ยง 0..100 (`evidence.risk_score`) |
| `AI-SYNTH-OVERVIEW/THEME/FOCUS` | synthesis | บทสรุปเชิงบริหาร |
| `SUPER-QA` | super | สุขภาพสายการผลิต (agent ครบ/ล้ม, AI fallback) |
| `SUPER-PRIORITY` | super | ลำดับ "ควรตรวจก่อน" (คะแนนรวมทุก tier) |
| `SUPER-NOVEL` | super | บิลที่ AI ชี้แต่ไม่มีผู้ตรวจ deterministic ธง |
| `SUPER-VERDICT` | super | คำตัดสินเชิงระบบ 1 บรรทัด |
| `SUPER-BRIEF` | super | บทสรุปเชิงปฏิบัติการจาก LLM (ถ้ามี) |
| `NOTE-REPORT` | notepad | บันทึกว่าได้สร้างไฟล์รายงาน .txt แล้ว |

---

## 6. วิธีเพิ่ม agent ใหม่ (ทีละขั้น)

**กฎเหล็ก:** agent ใหม่ที่เป็น review/analysis ต้อง **advisory** — อ่าน `ctx`/`mesh` เท่านั้น
ห้าม mutate `ctx.bills`/ผลตรวจหลัก (มิฉะนั้น byte-identical พัง).

### 6.1 โครงคลาส
```python
# agents/myrule_agent.py
from __future__ import annotations
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status

class MyRuleAgent(Agent):
    name = "myrule"
    description = "อธิบายสั้น ๆ ว่า agent นี้ดูอะไร"
    critical = False          # advisory: พัง = pipeline ไปต่อ

    def _run(self, ctx: PipelineContext) -> AgentResult:
        mesh = ctx.mesh
        if mesh is None:
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "ไม่มี mesh"})
        findings = []
        # อ่านผลเพื่อนผ่าน mesh (อย่าฮาร์ดโค้ด ctx.results["..."])
        for row in mesh.correlate_by_bill(min_agents=2):
            findings.append(Finding(
                agent=self.name, code="MYRULE-X", severity=Severity.WARNING.value,
                message=f"พบสัญญาณที่บิลนี้จาก {row['n_agents']} ผู้ตรวจ",
                file=row["file"], sheet=row["sheet"], iv=row["iv"],
                evidence={"agents": row["agents"]}))
        return AgentResult(self.name, Status.OK.value,
                           summary={"flagged": len(findings)}, findings=findings)
```

### 6.2 ลงทะเบียนใน orchestrator
ใส่ในตำแหน่ง tier ที่เหมาะ (เช่น Tier-2 = อ่าน Tier-1):
```python
# agents/orchestrator.py
from .myrule_agent import MyRuleAgent
# ... ใน Orchestrator.run() ตามลำดับที่ต้องการ:
self._dispatch(MyRuleAgent(self.logger), ctx)
```

### 6.3 export ใน `agents/__init__.py`
เพิ่ม `from .myrule_agent import MyRuleAgent` + ใส่ใน `__all__`.

### 6.4 พิสูจน์ว่าไม่ทำผลเพี้ยน
```bash
PYTHONHASHSEED=0 python3 verify_golden.py . out.json /mnt/project   # ต้อง 7b60b01f…
PYTHONHASHSEED=0 python3 test_agents.py . /mnt/project              # ต้องยังผ่านครบ
```
(เพิ่มเคสทดสอบของ agent ใหม่ใน `test_agents.py` ด้วยจะดีที่สุด)

---

## 7. การ degrade ของ AI (graceful)

AI ผ่าน `agents/llm_provider.py` → `make_provider(ctx.options)` (Ollama / OpenAICompat / Null / Mock).
- `enable_ai=False` หรือ provider ต่อไม่ได้ → `ai_review` = **skipped**,
  `synthesis` = โหมด **สถิติ**, `super` = โหมด **deterministic**.
- ทุกกรณี **ไม่พัง ไม่ค้าง** และ byte-identical ไม่เปลี่ยน (ทดสอบใน `test_agents.py` ข้อ B).

---

## 8. SuperAgent (Tier-4) — เชิงลึก

`super_agent.py` คือ **ผู้กำกับระบบ (meta-supervisor)** — ฉลาดเรื่อง "ตัวระบบ" ไม่ใช่เนื้อหา audit
(จึงไม่ซ้ำกับ synthesis ที่สรุปเนื้อหา). ทำงาน **deterministic** เป็นหลัก + LLM เป็นทางเลือก.

### หน้าที่ 4 อย่าง
1. **Pipeline QA** (`SUPER-QA`) — จาก `ctx.results`: agent ครบ 9 ตัวไหม, ตัวใด error/skipped,
   AI ตกโหมด fallback ไหม (อ่าน `summary.mode` ของ synthesis/ai_review).
2. **Unified priority** (`SUPER-PRIORITY`) — รวมสัญญาณทุก tier ต่อบิลเป็น "คะแนนเดียว" แล้วจัดอันดับ:
   ```
   raw = severity_weight(max ของหลักฐานต้นทาง)        # CRITICAL40/ERROR25/WARNING12/INFO4
       + (n_tier1 - 1) * 8     ถ้า n_tier1 >= 2         # ผู้ตรวจอิสระเห็นพ้อง
       + confidence_risk_score * 0.4                    # คะแนน Tier-2 (cross-aware แล้ว)
       + 8   ถ้า ai_review ก็ธงบิลนี้                   # AI เห็นพ้อง
   priority = round(raw / max_raw * 100, 1)            # normalize เชิงอันดับ 0..100
   ```
   เรียง `(-priority, -severity_rank, bill_key)` (deterministic) → top-N (`super_top_n`, default 10).
3. **Divergence** (`SUPER-NOVEL`) — บิลที่ `ai_review` ชี้ แต่ไม่มี Tier-1 ธง = สัญญาณใหม่/อาจ false positive.
4. **System verdict** (`SUPER-VERDICT`) — สรุป 1 บรรทัด + (ถ้า `enable_ai` และต่อ LLM ได้)
   `SUPER-BRIEF` = คำแนะนำเชิงปฏิบัติการระดับระบบ (degrade เป็น deterministic ถ้าไม่มี LLM).

### options ที่เกี่ยวข้อง
`super_top_n` (default 10), `super_novel_n` (default 10), `enable_ai`, `llm_provider`.

### advisory เต็มตัว
อ่าน `ctx.results`/`ctx.mesh`/`ctx.bills` อย่างเดียว, ออกเฉพาะ `SUPER-*` + `AgentResult.summary`
(`pipeline_ok`, `top_priorities`, `cross_confirmed_bills`, `ai_only_bills`, `verdict`).
**ไม่แตะ `ctx.bills`** → ReportAgent ไม่อ่าน mesh → Excel byte-identical (พิสูจน์: `verify_golden` = `7b60b01f…`).

### ตัวอย่างผลจริง (ชุด 81 ไฟล์, mock AI)
```
pipeline_ok=True, agents 9/9, ai_fallback=[synthesis]
ranked 315 บิล · top-2 = 100.0/100 (ผู้ตรวจ 3 ตัว + confidence 100 + cross-confirmed = CRITICAL)
311 cross-confirmed · 2 AI-only (novel) · 2 high-priority
findings: SUPER-QA×1, SUPER-PRIORITY×10, SUPER-NOVEL×2, SUPER-VERDICT×1
```
