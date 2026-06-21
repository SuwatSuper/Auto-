# -*- coding: utf-8 -*-
"""
agents/ — สถาปัตยกรรม multi-agent ที่ "ห่อ" เครื่องยนต์เดิม (ปุ้มปุ้ย v9) ทั้งชุด

7 agent ตามที่ออกแบบ:
  1. ImportAgent    (Python ปกติ)  — ค้นไฟล์ + parse → บิล
  2. FormulaAgent   (Python ปกติ)  — ตรวจซ้ำเชิงเลขคณิตอย่างอิสระ (advisory)
  3. VatAgent       (Python ปกติ)  — รวบ/ชี้ประเด็น VAT (advisory)
  4. WhtAgent       (Python ปกติ)  — ภาษีหัก ณ ที่จ่าย / ภงด.53 (advisory)
  5. TaxIdAgent     (Python ปกติ)  — เลขผู้เสียภาษี: checksum + ซ้ำข้ามบริษัท (advisory)
  6. ReportAgent    (Python ปกติ)  — เขียน Excel (เหมือนเดิม 100%)
  7. AiReviewAgent  (Local LLM)    — ผู้ตรวจคนที่สอง: triage/อธิบาย (advisory)

หลักการ: ผลตรวจที่ออก Excel วิ่งผ่าน "เครื่องยนต์เดิมชุดเดียว" ใน orchestrator
→ byte-identical พิสูจน์ได้ด้วย golden_master. agent review ทุกตัวอ่านอย่างเดียว.

──────────────────────────────────────────────────────────────────────────────
⚠️ [P-DECOUPLE] โหลดแบบ lazy (PEP 562 __getattr__)
   เดิม __init__.py นี้ import ทุก agent ทันที → การ `import agents.contracts`
   เพียงตัวเดียวก็ลาก core_access (เครื่องยนต์หลักทั้งก้อน) มาด้วย. ผลคือ:
     • โมดูล "บริสุทธิ์" (contracts/base/mesh/llm_provider/_shared) import ไม่ได้
       ถ้าไม่มี engine ครบ — แม้มันไม่พึ่ง engine เลย
     • engine ขาด symbol เดียว = ทั้ง namespace `agents` ล่ม (รวมเทสต์/เครื่องมือ)
   แก้: ผูกชื่อ → ชื่อโมดูลย่อย แล้วค่อย import ตอนถูกเรียกใช้จริง:
     - `from agents import FindingsMesh`  → โหลด .mesh (ไม่แตะ engine)
     - `from agents import ImportAgent`   → โหลด .import_agent (พึ่ง engine จริง — ถูกต้อง)
     - `import agents.contracts`          → __init__ เบา ๆ + contracts (ไม่แตะ engine)
"""
import importlib

# ชื่อสาธารณะ → โมดูลย่อยที่นิยามมัน (lazy: import เมื่อถูกอ้างถึงครั้งแรกเท่านั้น)
_LAZY = {
    # base / contracts (บริสุทธิ์ — ไม่พึ่ง engine)
    "Agent": "base", "AgentError": "base", "bill_ref": "base", "issues_with_prefix": "base",
    "AgentResult": "contracts", "Finding": "contracts", "PipelineContext": "contracts",
    "Severity": "contracts", "Status": "contracts",
    # data plane (บริสุทธิ์)
    "FindingsMesh": "mesh",
    # agents — Tier-1 review (import_agent/formula/vat/wht/taxid พึ่ง core_access → engine)
    "ImportAgent": "import_agent", "FormulaAgent": "formula_agent",
    "VatAgent": "vat_agent", "WhtAgent": "wht_agent", "TaxIdAgent": "taxid_agent",
    # agents — Tier-2 mesh consumers (บริสุทธิ์)
    "CrossCheckAgent": "crosscheck_agent", "ConfidenceAgent": "confidence_agent",
    # agents — AI / synthesis / supervisor (บริสุทธิ์ — ใช้ llm_provider)
    "AiReviewAgent": "ai_review_agent", "SynthesisAgent": "synthesis_agent",
    "SuperAgent": "super_agent",
    # agents — output (report พึ่ง engine; notepad/vendor_report บริสุทธิ์)
    "ReportAgent": "report_agent", "resolve_report_dir": "report_agent",
    "NotepadAgent": "notepad_agent",
    "VendorReportAgent": "vendor_report_agent",
    "build_vendor_reports": "vendor_report",
    # orchestration (พึ่ง engine ผ่าน core_access)
    "Orchestrator": "orchestrator", "run_pipeline": "orchestrator",
    "_run_audit_core": "orchestrator",
    # llm (บริสุทธิ์)
    "LLMProvider": "llm_provider", "OllamaProvider": "llm_provider",
    "OpenAICompatProvider": "llm_provider", "NullProvider": "llm_provider",
    "MockProvider": "llm_provider", "make_provider": "llm_provider",
}

__all__ = list(_LAZY.keys())


def __getattr__(name):
    """PEP 562: เรียกเมื่อ attribute ไม่อยู่ใน namespace → import โมดูลย่อยที่เกี่ยวข้องตอนนี้."""
    mod_name = _LAZY.get(name)
    if mod_name is None:
        raise AttributeError(f"module 'agents' has no attribute {name!r}")
    module = importlib.import_module(f".{mod_name}", __name__)
    attr = getattr(module, name)
    globals()[name] = attr      # cache: ครั้งถัดไปเจอใน namespace ไม่ต้องวิ่ง __getattr__ ซ้ำ
    return attr


def __dir__():
    return sorted(list(globals().keys()) + __all__)
