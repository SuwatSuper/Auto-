# -*- coding: utf-8 -*-
"""test_mesh_contract.py — ทดสอบสัญญาผู้ผลิต Tier-1 ของ mesh (P2)

พิสูจน์ว่า "การเพี้ยนเงียบของ Tier-2 เมื่อ Tier-1 ล้ม" ถูกจับได้:
  A) happy path — ผู้ตรวจ Tier-1 ครบ 4 ตัว สถานะ ok → contract.ok True, ไม่มี MESH-CONTRACT
  B) failure    — บังคับ Tier-1 ตัวหนึ่งให้ล้ม → contract รายงาน errored + crosscheck ออก MESH-CONTRACT
  C) unit       — verify_producers จำแนก missing/errored/skipped/silent ถูกต้อง (ไม่พึ่ง pipeline)

เร็ว (ใช้ fixture เล็ก) → ใส่ CI ได้:
    PYTHONHASHSEED=0 python3 test_mesh_contract.py [pkg_dir=.] [fixture_dir=tests/fixtures]
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import glob
import io
import contextlib

PKG = sys.argv[1] if len(sys.argv) > 1 else "."
FIXDIR = sys.argv[2] if len(sys.argv) > 2 else "tests/fixtures"

sys.path.insert(0, PKG)
os.chdir(PKG)

import mesh_contract

MASTER = {
    "ทดสอบ": {"name": "บริษัท ทดสอบ การค้า จำกัด", "tax_id": "0105000000012",
              "branch": "สำนักงานใหญ่", "address": "-", "iv_prefix": "IV"}
}
FILES = sorted(glob.glob(os.path.join(FIXDIR, "*.xlsx")) + glob.glob(os.path.join(FIXDIR, "*.xls")))
PASS, FAIL = [], []


def check(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  {'✅' if cond else '❌'} {label}")


def run(options):
    from agents.orchestrator import run_pipeline
    with contextlib.redirect_stdout(io.StringIO()):
        return run_pipeline(MASTER, FILES, options, logger=lambda m: None)


print("=" * 64)
print("MESH CONTRACT — สัญญาผู้ผลิต Tier-1 (formula/vat/wht/taxid)")
print("=" * 64)
check(len(FILES) >= 1, f"พบ fixture อย่างน้อย 1 ไฟล์ ({len(FILES)} ไฟล์ใน {FIXDIR})")

# ── C) unit test ของ verify_producers (ไม่พึ่ง pipeline) ────────────────────
print("\n[C] verify_producers จำแนกสถานะถูกต้อง (unit)")


class _R:  # stub AgentResult (มีแค่ .status)
    def __init__(self, status):
        self.status = status


class _Mesh:
    def __init__(self, seen):
        self._seen = seen

    def agents_seen(self):
        return list(self._seen)


# ครบ + ทุกตัวโพสต์ → ok
rep = mesh_contract.verify_producers(
    {"formula": _R("ok"), "vat": _R("ok"), "wht": _R("ok"), "taxid": _R("ok")},
    _Mesh(["formula", "vat", "wht", "taxid"]))
check(rep["ok"] and not rep["violations"], "ครบ+ทุกตัวโพสต์ → ok ไม่มี violation")

# รัน ok แต่ไม่โพสต์ (silent) → ยัง ok (ไม่นับละเมิด)
rep = mesh_contract.verify_producers(
    {"formula": _R("ok"), "vat": _R("ok"), "wht": _R("ok"), "taxid": _R("ok")},
    _Mesh(["formula", "vat"]))   # wht/taxid รัน ok แต่ 0 finding
check(rep["ok"] and set(rep["silent"]) == {"wht", "taxid"},
      "รัน ok แต่ 0 finding = silent (ไม่ใช่ละเมิด)")

# ตัวหนึ่ง error → violation
rep = mesh_contract.verify_producers(
    {"formula": _R("ok"), "vat": _R("error"), "wht": _R("ok"), "taxid": _R("ok")},
    _Mesh(["formula", "wht", "taxid"]))
check((not rep["ok"]) and rep["errored"] == ["vat"] and "vat" in rep["violations"],
      "ตัวหนึ่ง status=error → ละเมิดสัญญา (errored)")

# ตัวหนึ่งหาย (ไม่ได้รัน) → violation
rep = mesh_contract.verify_producers(
    {"formula": _R("ok"), "vat": _R("ok"), "taxid": _R("ok")},   # ไม่มี wht
    _Mesh(["formula", "vat", "taxid"]))
check((not rep["ok"]) and rep["missing"] == ["wht"], "ตัวหนึ่งไม่ได้รัน → ละเมิดสัญญา (missing)")

# skipped = เตือน ไม่ใช่ละเมิดเข้ม
rep = mesh_contract.verify_producers(
    {"formula": _R("ok"), "vat": _R("ok"), "wht": _R("skipped"), "taxid": _R("ok")},
    _Mesh(["formula", "vat", "taxid"]))
check(rep["ok"] and rep["skipped"] == ["wht"], "status=skipped → ไม่นับละเมิด (อยู่ใน skipped)")

# ── A) happy path บน fixture ────────────────────────────────────────────────
print("\n[A] happy path: Tier-1 ครบ → ไม่มี MESH-CONTRACT")
if FILES:
    ctx = run({"write_report": False, "enable_ai": True, "llm_provider": "mock", "lean": True})
    cc = ctx.results.get("crosscheck")
    cf = ctx.results.get("confidence")
    statuses = {n: r.status for n, r in ctx.results.items()}
    check(all(statuses.get(a) == "ok" for a in ("formula", "vat", "wht", "taxid")),
          f"ผู้ตรวจ Tier-1 รันครบ+ok ({[statuses.get(a) for a in ('formula','vat','wht','taxid')]})")
    check(cc is not None and cc.summary.get("tier1_contract", {}).get("ok") is True,
          "crosscheck: tier1_contract.ok = True")
    cc_codes = {f.code for f in (cc.findings if cc else [])}
    check("MESH-CONTRACT" not in cc_codes, "ไม่มี finding MESH-CONTRACT ใน happy path")
    check(cf is not None and cf.summary.get("tier1_contract", {}).get("ok") is True,
          "confidence: tier1_contract.ok = True (คะแนนเชื่อถือได้)")

# ── B) failure path: บังคับ Tier-1 ตัวหนึ่งล้ม ──────────────────────────────
print("\n[B] failure path: vat ล้ม → contract จับได้ + crosscheck ออก MESH-CONTRACT")
if FILES:
    import agents.vat_agent as va
    orig = va.VatAgent._run

    def _boom(self, ctx):
        raise RuntimeError("จงใจให้ vat พัง (ทดสอบสัญญา mesh)")

    va.VatAgent._run = _boom
    try:
        ctx = run({"write_report": False, "enable_ai": True, "llm_provider": "mock", "lean": True})
    finally:
        va.VatAgent._run = orig   # คืนสภาพเสมอ

    check(ctx.results.get("vat") is not None and ctx.results["vat"].status == "error",
          "vat ถูก error boundary จับ (status=error) — pipeline ไปต่อ")
    cc = ctx.results.get("crosscheck")
    con = (cc.summary or {}).get("tier1_contract", {}) if cc else {}
    check(con.get("ok") is False and "vat" in con.get("errored", []),
          "crosscheck: tier1_contract จับได้ว่า vat ล้ม (ok=False, errored มี vat)")
    mc = [f for f in (cc.findings if cc else []) if f.code == "MESH-CONTRACT"]
    check(len(mc) == 1 and mc[0].severity == "ERROR",
          "crosscheck ออก finding MESH-CONTRACT (severity ERROR) พอดี 1 อัน")
    check(bool(mc) and "vat" in (mc[0].evidence.get("errored") or []),
          "MESH-CONTRACT evidence ชี้ชัดว่า vat คือตัวที่หาย")
    # ต้องไม่ออกซ้ำจาก confidence (กันธงซ้ำ) — confidence เก็บแค่ในสรุป
    cf = ctx.results.get("confidence")
    cf_mc = [f for f in (cf.findings if cf else []) if f.code == "MESH-CONTRACT"]
    check(len(cf_mc) == 0, "confidence ไม่ออก MESH-CONTRACT ซ้ำ (ยกธงที่ crosscheck ที่เดียว)")
    # super (QA) ต้องเห็นว่ามี agent ล้มด้วย
    sup = ctx.results.get("super")
    check(sup is not None and "vat" in (sup.summary or {}).get("agents_errored", []),
          "SuperAgent QA จับได้ว่า vat ล้ม (สอดคล้องกับ mesh-contract)")

# ── สรุป ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"สรุป: ผ่าน {len(PASS)} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ ผ่านทั้งหมด — สัญญาผู้ผลิต Tier-1 บังคับใช้แล้ว (Tier-2 ไม่เพี้ยนเงียบเมื่อ Tier-1 ล้ม)")
sys.exit(0)
