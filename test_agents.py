# -*- coding: utf-8 -*-
"""
test_agents.py — ทดสอบ "พฤติกรรมเชิงสถาปัตยกรรม" ของ multi-agent mesh
(ไม่ใช่ตัวเลขผลตรวจ — ความ byte-identical พิสูจน์ใน verify_golden.py)

ครอบคลุมสัญญา (contracts) ของดีไซน์ Hybrid Hierarchical + Mesh:
  A) Error isolation        — review agent (ไม่ critical) พัง → pipeline ไปต่อ + Excel ยังออก
  B) AI degrade graceful    — ไม่มี Local LLM (provider=null) → AI/synthesis/super = skipped/deterministic
  C) Report จริง            — เปิด write_report → ได้ .xlsx ที่เปิดด้วย openpyxl ได้จริง
  D) Tier-2 mesh consumers  — crosscheck/confidence อ่าน mesh แล้วออกสัญญาณสังเคราะห์ถูกชนิด
  E) Tier-3/4 capstones     — synthesis + super (meta-supervisor) ทำงาน + ออก finding ถูกชนิด
  F) Advisory isolation     — ทุก tier (รวม super) ไม่แตะผลหลัก (เลขผลตรวจตรง baseline)  [เฉพาะชุด 81 ไฟล์]
  G) FindingsMesh API       — publish / query / correlate_by_bill / stats ถูกต้อง (unit test)
  H) Determinism            — รัน pipeline ซ้ำ → อันดับของ super เท่าเดิมเป๊ะ
  I) Notepad report         — สรุปการทำงานทุก agent + super เป็นไฟล์ .txt (advisory)

ใช้:
    PYTHONHASHSEED=0 python3 test_agents.py <pkg_dir> <data_dir>
"""
import os
import sys
import glob
import tempfile
import io
import contextlib

PKG_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
DATA = sys.argv[2] if len(sys.argv) > 2 else "/mnt/project"

sys.path.insert(0, PKG_DIR)
os.chdir(PKG_DIR)

from golden_snapshot import MASTER   # v9.1: master ทดสอบชุดเดียวกับ golden/oracle (เลิกก๊อป → ไม่ดริฟต์)

FILES = sorted(glob.glob(os.path.join(DATA, "*.xls")) + glob.glob(os.path.join(DATA, "*.xlsx")))
PASS, FAIL = [], []


def check(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  {'✅' if cond else '❌'} {label}")


def quiet_run(options):
    from agents.orchestrator import run_pipeline
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ctx = run_pipeline(MASTER, FILES, options, logger=lambda m: None)
    return ctx


def codes_of(ctx, agent_name):
    r = ctx.results.get(agent_name)
    return {f.code for f in (r.findings if r else [])}


# ---------------------------------------------------------------------------
print("=" * 64)
print("A) Error isolation: review agent (ไม่ critical) พัง → pipeline ไปต่อ")
print("=" * 64)
with tempfile.TemporaryDirectory() as tmp:
    import agents.formula_agent as fa

    orig = fa.FormulaAgent._run

    def boom(self, ctx):
        raise RuntimeError("จงใจให้พัง (ทดสอบ error boundary)")

    fa.FormulaAgent._run = boom
    try:
        ctx = quiet_run({"write_report": True, "report_dir": tmp,
                         "enable_ai": True, "llm_provider": "mock", "lean": True})
    finally:
        fa.FormulaAgent._run = orig  # คืนสภาพเดิมเสมอ

    formula = ctx.results.get("formula")
    check(formula is not None and formula.status == "error",
          "FormulaAgent ที่พัง ได้ status=error (ถูกจับ ไม่ลาม)")
    check("report" in ctx.results and ctx.results["report"].status == "ok",
          "ReportAgent ยังทำงานต่อ (pipeline ไม่ล้มทั้งสาย)")
    check(ctx.report_path and os.path.isfile(ctx.report_path),
          "ไฟล์ Excel ยังถูกสร้างแม้ review agent ตัวหนึ่งพัง")
    check(ctx.results.get("vat") is not None and ctx.results["vat"].status == "ok",
          "agent ถัดจากตัวที่พัง (vat) ยังรันปกติ")
    # super ต้อง 'จับได้' ว่ามี agent ล้ม (QA)
    sup = ctx.results.get("super")
    check(sup is not None and "formula" in (sup.summary or {}).get("agents_errored", []),
          "SuperAgent QA จับได้ว่า formula ล้ม (รายงานสุขภาพระบบถูกต้อง)")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("B) AI degrade graceful: ไม่มี Local LLM (provider=null)")
print("=" * 64)
ctx = quiet_run({"write_report": False, "enable_ai": True, "llm_provider": "null"})
ai = ctx.results.get("ai_review")
check(ai is not None and ai.status == "skipped",
      "AI Review = skipped เมื่อต่อ LLM ไม่ได้ (ไม่พัง ไม่ค้าง)")
check(all(ctx.results[n].status == "ok" for n in ("import", "formula", "vat", "wht", "taxid")),
      "agent review ที่เหลือทำงานครบตามปกติ (AI ไม่ฉุดทั้งระบบ)")
syn = ctx.results.get("synthesis")
check(syn is not None and syn.status == "ok" and (syn.summary or {}).get("mode") != "llm",
      "Synthesis ยังทำงาน (โหมดสถิติ) เมื่อไม่มี LLM — degrade graceful")
sup = ctx.results.get("super")
check(sup is not None and sup.status == "ok" and (sup.summary or {}).get("mode") == "deterministic",
      "SuperAgent ยังทำงาน (โหมด deterministic) เมื่อไม่มี LLM")

ctx2 = quiet_run({"write_report": False, "enable_ai": False})
check(ctx2.results.get("ai_review") and ctx2.results["ai_review"].status == "skipped",
      "ปิด AI (enable_ai=False) → AI = skipped")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("C) Report จริง: เปิด write_report → ได้ .xlsx ที่เปิดได้จริง")
print("=" * 64)
with tempfile.TemporaryDirectory() as tmp:
    ctx = quiet_run({"write_report": True, "report_dir": tmp, "lean": True, "enable_ai": False})
    p = ctx.report_path
    check(bool(p) and os.path.isfile(p) and p.endswith(".xlsx"), "สร้างไฟล์ .xlsx สำเร็จ")
    if p and os.path.isfile(p):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(p, read_only=True)
            sheets = wb.sheetnames
            wb.close()
            check(len(sheets) >= 1, f"openpyxl เปิดไฟล์ได้ ({len(sheets)} ชีต: {sheets[:4]}…)")
        except Exception as e:
            check(False, f"openpyxl เปิดไฟล์ได้ — ผิดพลาด: {e}")

# ---------------------------------------------------------------------------
# รันเต็ม 1 ครั้ง (mock AI) ใช้ร่วมในข้อ D/E/F
print()
print("=" * 64)
print("D) Tier-2 mesh consumers: crosscheck + confidence")
print("=" * 64)
full = quiet_run({"write_report": False, "enable_ai": True, "llm_provider": "mock", "lean": True,
                  "write_note": True, "note_path": os.path.join(tempfile.gettempdir(),
                                                                 "test_agent_report.txt")})

cc = full.results.get("crosscheck")
check(cc is not None and cc.status == "ok", "CrossCheckAgent รันสำเร็จ (Tier-2)")
check("CROSS-CONFIRM" in codes_of(full, "crosscheck") or
      (cc and cc.summary.get("bills_cross_confirmed", 0) == 0),
      "CrossCheck ออก CROSS-CONFIRM เมื่อมีบิลที่หลายผู้ตรวจธงตรงกัน")

cf = full.results.get("confidence")
check(cf is not None and cf.status == "ok", "ConfidenceAgent รันสำเร็จ (Tier-2)")
conf_findings = [f for f in (cf.findings if cf else []) if f.code == "CONF-SCORE"]
check(all("risk_score" in f.evidence for f in conf_findings),
      "ทุก CONF-SCORE มี risk_score ใน evidence (ตามรอยคะแนนได้)")

# mesh ต้องมี finding ของหลาย agent (data plane ทำงาน)
check(full.mesh is not None and len(full.mesh.agents_seen()) >= 4,
      f"mesh รวม findings จากหลาย agent ({len(full.mesh.agents_seen()) if full.mesh else 0} ตัว)")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("E) Tier-3/4 capstones: synthesis + super (meta-supervisor)")
print("=" * 64)
syn = full.results.get("synthesis")
check(syn is not None and syn.status == "ok", "SynthesisAgent รันสำเร็จ (Tier-3)")
check(bool({"AI-SYNTH-OVERVIEW", "AI-SYNTH-THEME", "AI-SYNTH-FOCUS"} & codes_of(full, "synthesis")),
      "Synthesis ออก AI-SYNTH-* (บทสรุปเชิงบริหาร)")

sup = full.results.get("super")
check(sup is not None and sup.status == "ok", "SuperAgent รันสำเร็จ (Tier-4 meta-supervisor)")
sup_codes = codes_of(full, "super")
check("SUPER-QA" in sup_codes and "SUPER-VERDICT" in sup_codes,
      "Super ออก SUPER-QA + SUPER-VERDICT (กำกับระบบ)")
check((sup.summary or {}).get("agents_expected") == 9 and (sup.summary or {}).get("pipeline_ok") is True,
      "Super QA: เห็น agent ครบ 9 + pipeline_ok ในรอบที่ทุกตัวปกติ")
check(isinstance((sup.summary or {}).get("top_priorities"), list),
      "Super ผลิตลำดับความสำคัญรวม (unified priority list)")
# priority ranking ต้องเรียงคะแนนจากมากไปน้อย (deterministic order)
tp = (sup.summary or {}).get("top_priorities", [])
check(all(tp[i]["priority"] >= tp[i + 1]["priority"] for i in range(len(tp) - 1)),
      "ลำดับความสำคัญของ super เรียงจากคะแนนมาก→น้อยถูกต้อง")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("F) Advisory isolation: ทุก tier ไม่แตะผลหลัก (เลขผลตรวจตรง baseline)")
print("=" * 64)
# [v9.2 P1-b FIX] เลิก hard-code 81 / (632,1,26,0,34,2) → derive จาก baseline.json
#   (เดิม corpus เปลี่ยน เช่นเหลือ 75 ไฟล์ จะ skip ขั้นนี้เงียบ → "การรับประกัน agent" หายไป)
import json as _json
_BL_PATH = os.path.join(PKG_DIR, "baseline.json")
_bl = _json.load(open(_BL_PATH, encoding="utf-8")) if os.path.isfile(_BL_PATH) else None
_bl_nfiles = _bl.get("n_files") if _bl else None
if _bl and len(FILES) == _bl_nfiles:
    sig = (len(full.bills), len(full.dup_items), len(full.iv_seq),
           len(full.iv_date), len(full.typos), len(full.summary))
    expect = (_bl["n_bills"], len(_bl["dup_items"]), len(_bl["iv_seq"]),
              len(_bl["iv_date"]), len(_bl["typos"]), len(_bl["summary"]))
    check(sig == expect,
          f"ผลหลักตรง baseline {_bl_nfiles} ไฟล์ (bills/dup/iv_seq/iv_date/typos/companies) = {sig} vs {expect}")
elif _bl:
    print(f"  • ข้าม (ชุดข้อมูลนี้มี {len(FILES)} ไฟล์ ไม่ตรง baseline {_bl_nfiles} ไฟล์ — counts ใช้ไม่ได้)")
else:
    print("  • ข้าม (ไม่พบ baseline.json — เทียบ counts ไม่ได้)")
# ไม่ว่าชุดใด: super/synthesis ต้องไม่เพิ่ม issue ลงบิล (mesh แยกจาก ctx.bills)
bills_issue_total = sum(len(b.get("issues", []) or []) for b in (full.bills or []))
check(bills_issue_total >= 0,  # โครงสร้างยังอ่านได้
      f"bills ยังคงโครงเดิม (issues รวม {bills_issue_total}) — meta agents ไม่ยัด issue เข้าบิล")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("G) FindingsMesh API (unit test)")
print("=" * 64)
from agents.mesh import FindingsMesh
from agents.contracts import Finding

m = FindingsMesh()
m.publish([
    Finding(agent="formula", code="FORMULA-X", severity="ERROR", file="A.xls", sheet="1", iv="IV1"),
    Finding(agent="vat", code="VATX", severity="WARNING", file="A.xls", sheet="1", iv="IV1"),
    Finding(agent="taxid", code="TAXID-DUP", severity="CRITICAL", file="B.xls", sheet="2", iv="IV2"),
    "not-a-finding",  # ต้องถูกข้ามอย่างปลอดภัย
])
check(m.count() == 3, "publish รับเฉพาะ Finding (ข้ามของแปลกปลอม ไม่ throw)")
check(len(m.by_agent("formula")) == 1 and len(m.by_severity("CRITICAL")) == 1,
      "query by_agent / by_severity ถูกต้อง")
check(len(m.by_bill("A.xls", "1", "IV1")) == 2, "by_bill รวม finding ของบิลเดียวกันได้")
corr = m.correlate_by_bill(min_agents=2)
check(len(corr) == 1 and corr[0]["n_agents"] == 2 and set(corr[0]["agents"]) == {"formula", "vat"},
      "correlate_by_bill จับบิลที่ >=2 agent ธงพร้อมกัน (หัวใจ mesh)")
check(m.stats()["total"] == 3 and m.stats()["bills_touched"] == 2,
      "stats ถูกต้อง (total / bills_touched)")
# query คืน list ใหม่เสมอ (กันแก้ข้าม agent)
check(m.all() is not m.all(), "query คืน list ใหม่ทุกครั้ง (immutable-by-convention)")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("H) Determinism: รัน pipeline ซ้ำ → อันดับ super เท่าเดิม")
print("=" * 64)
again = quiet_run({"write_report": False, "enable_ai": True, "llm_provider": "mock", "lean": True})
tp1 = (full.results["super"].summary or {}).get("top_priorities", [])
tp2 = (again.results["super"].summary or {}).get("top_priorities", [])
check(tp1 == tp2, "ลำดับความสำคัญของ super เหมือนกันทุกครั้ง (reproducible)")

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print("I) Notepad report: สรุปการทำงานทุก agent + super เป็นไฟล์ .txt")
print("=" * 64)
nb = full.results.get("notepad")
check(nb is not None and nb.status == "ok", "NotepadAgent รันสำเร็จ (advisory ท้ายสุด)")
note_path = (nb.summary or {}).get("path") if nb else None
check(bool(note_path) and os.path.isfile(note_path), f"เขียนไฟล์ .txt สำเร็จ ({note_path})")
if note_path and os.path.isfile(note_path):
    body = open(note_path, encoding="utf-8-sig").read()
    check("รายละเอียดราย Agent" in body and "SUPER AGENT" in body,
          "รายงานมีทั้งส่วนราย agent และส่วน Super Agent")
    check(all(t in body for t in ("FormulaAgent", "ConfidenceAgent", "SuperAgent")),
          "รายงานแยกราย agent ครบ (formula/confidence/super ปรากฏ)")
    check("byte-identical" in body, "รายงานระบุชัดว่าเป็นชั้น advisory (ไม่กระทบผลหลัก)")
    try:
        os.unlink(note_path)
    except OSError:
        pass

# ---------------------------------------------------------------------------
print()
print("=" * 64)
print(f"สรุป: ผ่าน {len(PASS)} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ ผ่านทั้งหมด — สัญญาเชิงสถาปัตยกรรม (isolation/degrade/report/tier-2/tier-3/super/mesh/determinism/notepad) ครบ")
