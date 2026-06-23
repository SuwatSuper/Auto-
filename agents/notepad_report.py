# -*- coding: utf-8 -*-
"""
agents/notepad_report.py — ตัวสร้าง "รายงาน Notepad" (.txt) สรุปการทำงานของทุก agent

จุดประสงค์: สรุปผลการทำงานของแต่ละ agent **แยกเป็นตัว ๆ** (ทำหน้าที่อะไร, พบอะไร, สถานะ/เวลา)
+ ส่วนพิเศษของ SuperAgent (ผู้กำกับระบบ). เป็นข้อความล้วน อ่านใน Notepad ได้ทันที.

⚠️ ADVISORY ONLY — อ่าน ctx อย่างเดียว ไม่แตะผลตรวจหลัก. รายงานนี้เป็นไฟล์แยก ไม่เกี่ยวกับ
   ผล byte-identical (ซึ่งคิดจาก bills/summary เท่านั้น ไม่ใช่ข้อความรายงานนี้).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from ._shared import SEV_RANK as _SEV_RANK

# ลำดับการแสดง (ตามลำดับ pipeline) + ข้อมูลกำกับราย agent
_ORDER = ["import", "formula", "vat", "wht", "taxid",
          "crosscheck", "confidence", "verification", "ai_review", "synthesis", "super",
          "report", "notepad"]

_AGENT_INFO: Dict[str, Dict[str, str]] = {
    "import":     {"title": "ImportAgent",     "tier": "นำเข้า (critical)",
                   "role": "ค้นไฟล์ + แยกข้อมูลรายบิล (parse) → bills"},
    "formula":    {"title": "FormulaAgent",    "tier": "Tier 1 — ผู้ตรวจอิสระ",
                   "role": "ตรวจซ้ำเชิงเลขคณิตอย่างอิสระ (ยอดรวม/ภาษี)"},
    "vat":        {"title": "VatAgent",        "tier": "Tier 1 — ผู้ตรวจอิสระ",
                   "role": "รวบ/ชี้ประเด็น VAT จากผลตรวจหลัก (อ่านอย่างเดียว)"},
    "wht":        {"title": "WhtAgent",        "tier": "Tier 1 — ผู้ตรวจอิสระ",
                   "role": "ภาษีหัก ณ ที่จ่าย (ภงด.53)"},
    "taxid":      {"title": "TaxIdAgent",      "tier": "Tier 1 — ผู้ตรวจอิสระ",
                   "role": "เลขผู้เสียภาษี: ตรวจ checksum + เลขซ้ำข้ามบริษัท"},
    "crosscheck": {"title": "CrossCheckAgent", "tier": "Tier 2 — รวมผลข้าม agent",
                   "role": "จับบิลที่หลายผู้ตรวจอิสระธงตรงกัน (cross-validated)"},
    "confidence": {"title": "ConfidenceAgent", "tier": "Tier 2 — ให้คะแนน",
                   "role": "ให้คะแนนความเชื่อมั่นความเสี่ยงต่อบิล (จัดอันดับงานตรวจ)"},
    "verification": {"title": "VerificationAgent", "tier": "Tier 2 — ยืนยัน Error (consensus)",
                     "role": "verify Error ของ engine แต่ละตัวด้วยคลังผู้ตรวจ → CONFIRMED/REVIEW/FALSE-POS"},
    "ai_review":  {"title": "AiReviewAgent",   "tier": "Tier 2.5 — triage (Local LLM)",
                   "role": "จัดลำดับรายบิล + อธิบายให้คนเข้าใจ (advisory)"},
    "synthesis":  {"title": "SynthesisAgent",  "tier": "Tier 3 — สังเคราะห์ (capstone)",
                   "role": "บทสรุปเชิงบริหารของภาพรวมงานตรวจทั้งชุด"},
    "super":      {"title": "SuperAgent",      "tier": "Tier 4 — ผู้กำกับระบบ",
                   "role": "QA สายการผลิต + รวมสัญญาณทุก tier เป็นลำดับเดียว + จับสัญญาณขัดแย้ง"},
    "report":     {"title": "ReportAgent",     "tier": "ส่งออก (critical)",
                   "role": "เขียนรายงาน Excel (ผลตรวจหลัก — เหมือนเดิมทุกประการ)"},
    "notepad":    {"title": "NotepadAgent",    "tier": "ส่งออก (advisory)",
                   "role": "สรุปการทำงานของทุก agent เป็นไฟล์ .txt (รายงานนี้)"},
}

_LINE = "=" * 70
_SUB = "-" * 70


def _status_th(s: str) -> str:
    return {"ok": "สำเร็จ", "skipped": "ข้าม", "error": "ผิดพลาด"}.get(s, s)


def _fmt_bill(f) -> str:
    ref = "/".join(x for x in (f.file, f.sheet, f.iv) if x)
    return f"({ref}) " if ref else ""


def _top_findings(findings: List, k: int = 3) -> List:
    return sorted(findings, key=lambda f: (-_SEV_RANK.get(f.severity, 0),
                                           f.file, f.sheet, f.iv, f.code))[:k]


def _outcome_line(name: str, res) -> str:
    """สรุป 'ผลงาน' 1 บรรทัดต่อ agent จาก summary (รู้คีย์เฉพาะตัว + fallback)."""
    s = res.summary or {}
    n = len(res.findings)
    if name == "import":
        return f"นำเข้าบิลเข้าสู่ระบบเรียบร้อย (ดูจำนวนบิลรวมในส่วนหัวรายงาน)"
    if name in ("formula", "vat", "wht", "taxid"):
        return f"ตรวจแล้ว ออกข้อสังเกต {n} รายการ"
    if name == "crosscheck":
        return (f"พบบิลที่ผู้ตรวจหลายตัวเห็นตรงกัน {s.get('bills_cross_confirmed', 0)} ใบ "
                f"(จาก mesh รวม {s.get('mesh_total_findings', '-')} finding)")
    if name == "confidence":
        return (f"ให้คะแนน {s.get('scored_bills', 0)} บิล, ชูเด่น {s.get('flagged_bills', 0)} บิล "
                f"(threshold {s.get('min_score_threshold', '-')})")
    if name == "verification":
        llm = (s.get("llm_lens") or {}).get("used")
        return (f"ยืนยัน Error {s.get('errors_verified', 0)} จุด → "
                f"ชัดเจน(CONFIRMED) {s.get('confirmed', 0)}, "
                f"ต้องดู(REVIEW) {s.get('needs_review', 0)}, "
                f"น่าจะ false-positive {s.get('likely_false_positive', 0)}"
                f"{' [+LLM lens]' if llm else ''}")
    if name == "ai_review":
        if res.status == "skipped":
            return f"ข้าม — {s.get('reason', 'ไม่มี Local LLM / ปิดใช้งาน')}"
        mode = s.get("mode")
        return (f"triage รายบิล{f' (โหมด {mode})' if mode else ''} ออก {n} ข้อสังเกต")
    if name == "synthesis":
        themes = sum(1 for f in res.findings if f.code == "AI-SYNTH-THEME")
        focus = sum(1 for f in res.findings if f.code == "AI-SYNTH-FOCUS")
        return (f"สรุปภาพรวม (โหมด {s.get('mode', '-')}): "
                f"theme {themes}, focus {focus}, "
                f"บิล cross-validated {s.get('corroborated_bills', 0)} ใบ")
    if name == "super":
        return (f"กำกับระบบ: pipeline {'ครบ' if s.get('pipeline_ok') else 'ไม่ครบ'} "
                f"({s.get('agents_ok', '-')}/{s.get('agents_expected', '-')}), "
                f"จัดอันดับ {s.get('bills_ranked', 0)} บิล, "
                f"ควรตรวจก่อน {s.get('high_priority_bills', 0)} บิล")
    if name == "report":
        return "เขียนไฟล์ Excel สำเร็จ" if res.status == "ok" else f"สถานะ: {_status_th(res.status)}"
    if name == "notepad":
        return "กำลังสร้างรายงานนี้"
    # fallback: ดึง 2-3 คีย์แรกจาก summary
    bits = [f"{k}={v}" for k, v in list(s.items())[:3]]
    return ("; ".join(bits) if bits else f"ออก {n} ข้อสังเกต")


def _render_agent_block(idx: int, name: str, res) -> List[str]:
    info = _AGENT_INFO.get(name, {"title": name, "tier": "-", "role": "-"})
    out = [
        f"[{idx}] {info['title']}  ({name})",
        f"      Tier      : {info['tier']}",
        f"      หน้าที่    : {info['role']}",
        f"      สถานะ     : {_status_th(res.status)}   "
        f"|  เวลา {res.duration_s:.3f}s   |  ข้อสังเกต {len(res.findings)} รายการ",
        f"      สรุปผล    : {_outcome_line(name, res)}",
    ]
    if res.error:
        out.append(f"      ⚠ error  : {str(res.error).splitlines()[0][:120]}")
    tops = _top_findings(res.findings, 3)
    # ไม่ต้องโชว์ตัวอย่างของ super (มีส่วนแยกด้านล่าง) และ notepad
    if tops and name not in ("super", "notepad"):
        out.append("      ตัวอย่างที่พบ:")
        for f in tops:
            out.append(f"         • [{f.severity}] {_fmt_bill(f)}{f.message[:96]}")
        extra = len(res.findings) - len(tops)
        if extra > 0:
            out.append(f"         … และอีก {extra} รายการ")
    out.append("")
    return out


def _render_super_section(res) -> List[str]:
    if res is None:
        return []
    s = res.summary or {}
    out = [_LINE,
           "   SUPER AGENT — ผู้กำกับระบบ (Tier 4, meta-supervisor)",
           _LINE,
           f"   สถานะระบบ      : {'✅ ครบ' if s.get('pipeline_ok') else '⚠️ ไม่ครบ'} "
           f"(agent {s.get('agents_ok', '-')}/{s.get('agents_expected', '-')})"]
    if s.get("agents_errored"):
        out.append(f"   agent ที่ล้ม    : {', '.join(s['agents_errored'])}")
    if s.get("ai_fallback"):
        out.append(f"   AI โหมด fallback: {', '.join(s['ai_fallback'])}")
    out.append(f"   จัดอันดับบิล    : {s.get('bills_ranked', 0)} ใบที่มีสัญญาณ")
    out.append(f"   cross-confirmed : {s.get('cross_confirmed_bills', 0)} ใบ "
               f"(หลายผู้ตรวจเห็นตรงกัน)")
    out.append(f"   AI ชี้เพิ่ม      : {s.get('ai_only_bills', 0)} ใบ "
               f"(deterministic ไม่ธง — ใช้วิจารณญาณ)")

    tp = s.get("top_priorities", [])
    if tp:
        out.append("")
        out.append("   ▶ บิลที่ควรตรวจก่อน (priority รวมจากทุก tier):")
        for t in tp:
            ref = "/".join(x for x in (t.get("file", ""), t.get("sheet", ""), t.get("iv", "")) if x)
            # ป้องกัน None ทำ format crash (latent): cast เป็น str ก่อนจัดความกว้าง — ผลปกติเหมือนเดิม
            rank = t.get("rank", "-")
            prio = t.get("priority", "-")
            out.append(f"        อันดับ {str(rank):>2}  [{str(prio):>5}/100]  {ref}")

    if s.get("verdict"):
        out.append("")
        out.append("   ▶ คำตัดสินเชิงระบบ:")
        for ln in _wrap(s["verdict"], 64):
            out.append(f"        {ln}")

    # SUPER-BRIEF (ถ้ามี LLM)
    brief = next((f.message for f in res.findings if f.code == "SUPER-BRIEF"), None)
    if brief:
        out.append("")
        out.append("   ▶ คำแนะนำเชิงปฏิบัติการ (จาก Local LLM):")
        for ln in _wrap(brief, 64):
            out.append(f"        {ln}")
    out.append("")
    return out


def _render_inspection_board(res) -> List[str]:
    """ส่วน 'ทีมผู้ตรวจเชิงกลไก' — โชว์คลังเลนส์ + มติต่อ Error + evidence trail (SUMMARY HONESTY)."""
    out = [_LINE,
           "   ทีมผู้ตรวจเชิงกลไก (Inspection Bank) — ยืนยัน Error ทุกจุดก่อนฟันธง",
           _LINE]
    if res is None or res.status != "ok":
        out += ["   (ไม่มีผลจาก VerificationAgent ในรอบนี้)", ""]
        return out
    s = res.summary or {}
    roster = s.get("lens_roster", [])
    out.append(f"   ผู้ตรวจในคลัง : {s.get('inspectors', len(roster))} คน "
               "— แต่ละคนโหวตอิสระต่อ Error แต่ละจุด (+1 ยืนยัน / 0 งดออกเสียง / −1 ค้าน) แล้วลงมติร่วม")
    teams = [
        ("ยอดเงิน/เลขคณิต", {"arithmetic", "rounding_artifact", "vat_7pct_exact", "amount_completeness",
                            "money_triple", "line_sum_amount", "line_qty_price", "negative_sanity",
                            "magnitude_outlier"}),
        ("เลขภาษี/ทะเบียน", {"taxid_checksum", "taxid_format", "taxid_crosscompany", "master_known"}),
        ("เอกสาร/งวด/ลำดับ", {"doc_completeness", "period_match", "iv_prefix_match", "duplicate_signature"}),
        ("ความน่าเชื่อ/บริบท", {"provenance", "parse_trust", "peer_consistency", "rule_precision",
                              "language_model"}),
    ]
    for label, dims in teams:
        members = [r["id"] for r in roster if r.get("dimension") in dims]
        if members:
            out.append(f"      • {label} ({len(members)}): {', '.join(members)}")
    out.append("")
    out.append(f"   ผลลงมติต่อ Error {s.get('errors_verified', 0)} จุด (แยกชัด ไม่มีจุดใดถูกตัดทิ้งเงียบ):")
    out.append(f"      ✔ CONFIRMED  มั่นใจว่าเป็นปัญหาจริง        : {s.get('confirmed', 0)} จุด")
    out.append(f"      ? REVIEW     ก้ำกึ่ง ให้คนตัดสิน           : {s.get('needs_review', 0)} จุด")
    out.append(f"      ✘ FALSE-POS  น่าจะไม่ใช่ปัญหา (ลดความสำคัญ) : {s.get('likely_false_positive', 0)} จุด")
    llm = s.get("llm_lens") or {}
    out.append("      เลนส์ภาษา (LLM): "
               + ("ใช้งาน (local)" if llm.get("used") else "ปิด/ออฟไลน์ → งดออกเสียง")
               + " — ผลที่เหลือ deterministic")
    out.append("")

    by_v: Dict[str, List] = {"CONFIRMED": [], "NEEDS_REVIEW": [], "LIKELY_FALSE_POSITIVE": []}
    for f in res.findings:
        v = (f.evidence or {}).get("verdict")
        if v in by_v:
            by_v[v].append(f)
    label_map = {"CONFIRMED": "✔ CONFIRMED", "NEEDS_REVIEW": "? NEEDS_REVIEW",
                 "LIKELY_FALSE_POSITIVE": "✘ LIKELY_FALSE_POSITIVE"}
    caps = {"CONFIRMED": 10, "NEEDS_REVIEW": 6, "LIKELY_FALSE_POSITIVE": 6}
    for v in ("CONFIRMED", "NEEDS_REVIEW", "LIKELY_FALSE_POSITIVE"):
        items = by_v[v]
        if not items:
            continue
        out.append(f"   ▶ {label_map[v]} — {len(items)} จุด (พร้อมเหตุผลของผู้ตรวจ):")
        for f in items[:caps[v]]:
            e = f.evidence or {}
            out.append(f"        {_fmt_bill(f)}[{e.get('engine_code')}] คะแนนรวม {e.get('score', 0):+d}")
            for r in (e.get("reasons") or [])[:4]:
                out.append(f"            – {r}")
        if len(items) > caps[v]:
            out.append(f"        … และอีก {len(items) - caps[v]} จุด (finding เก็บครบทุกจุด)")
        out.append("")
    return out


def _wrap(text: str, width: int) -> List[str]:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def _render_unit_consistency(bills) -> List[str]:
    """[ADD-ON v9.2] ส่วนตรวจ "หน่วยสินค้า" เพิ่มเติม (advisory) — ตอบ 4 อาการที่ลูกค้าแจ้ง:
       (1) สรุปหน่วยที่พบต่อไฟล์ → ทำให้ 'ตรม.' และหน่วยอื่นปรากฏในรายงาน
       (2) เตือนไฟล์ที่ใช้หน่วยปนไทย+อังกฤษ (ความหมายเดียวกัน เช่น กก./kg, ตรม./sqm)
       (3) เตือนหน่วยสะกดผิด/รูปไม่มาตรฐาน (ปี๊ป→ปี๊บ, แกลอน/แกนลอน→แกลลอน ฯลฯ)
    อ่าน bills อย่างเดียว ไม่แตะผลตรวจหลัก/byte-identical. import แบบกัน (ไม่มีโมดูล → ข้ามเงียบ).
    """
    try:
        import unit_detection_ext as ux
    except Exception:
        return []

    out = [_LINE,
           "   หน่วยสินค้า — ตรวจเพิ่ม (Unit Consistency, advisory)",
           _LINE]
    bills = bills or []
    by_file = ux.summarize_units_by_file(bills)
    if not by_file:
        out += ["   (ไม่มีข้อมูลหน่วยสินค้าในรอบนี้)", ""]
        return out

    # (1) หน่วยที่พบต่อไฟล์ (เรียงตามจำนวนครั้ง มาก→น้อย)
    out.append("   หน่วยที่พบ (ต่อไฟล์):")
    for fname in sorted(by_file):
        units = by_file[fname]
        parts = [f"{u}×{n}" for u, n in sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))]
        shown = ", ".join(parts[:20]) + (" …" if len(parts) > 20 else "")
        out.append(f"      • {fname}: {shown}")
    out.append("")

    # (2) ปนภาษาไทย+อังกฤษ / หน่วยขาด — ราย "บริษัท" (ตรงกับหมายเหตุในสรุปบริษัท)
    comp_mix = ux.detect_company_unit_language_mix(bills)
    mixed_lang = [d for d in comp_mix if d["th"] and d["en"]]
    blank_any = [d for d in comp_mix if d["blank"]]
    if mixed_lang:
        out.append("   ⚠️ บริษัทที่ใช้หน่วยสินค้าปนภาษาไทย+อังกฤษ (ควรใช้รูปเดียวกัน):")
        for d in mixed_lang:
            out.append(f"      • {d['company']} — ไทย: {', '.join(d['th'])} · อังกฤษ: {', '.join(d['en'])}")
    else:
        out.append("   ✅ ไม่พบบริษัทที่ใช้หน่วยปนไทย+อังกฤษ")
    out.append("")

    # (2b) หน่วยขาด/ดึงไม่ครบ — ราย "บริษัท"
    if blank_any:
        out.append("   ⚠️ บริษัทที่มีหน่วยสินค้าขาด/ดึงมาไม่ครบ (ช่องหน่วยว่างในรายการคิดเงิน):")
        for d in blank_any:
            out.append(f"      • {d['company']} — {d['blank']} รายการไม่มีหน่วย")
    else:
        out.append("   ✅ ไม่พบหน่วยสินค้าขาด/ดึงไม่ครบ")
    out.append("")

    # (3) หน่วยสะกดผิด/รูปไม่มาตรฐาน
    typos = ux.collect_unit_typos(bills)
    if typos:
        out.append(f"   ⚠️ หน่วยที่อาจสะกดผิด/รูปไม่มาตรฐาน ({len(typos)} รายการ):")
        for t in typos[:30]:
            out.append(f"      • {t}")
        if len(typos) > 30:
            out.append(f"      … และอีก {len(typos) - 30} รายการ")
    else:
        out.append("   ✅ ไม่พบหน่วยที่สะกดผิด/รูปไม่มาตรฐาน")
    out.append("")
    return out


def render(ctx) -> str:
    """สร้างข้อความรายงานทั้งฉบับ (plain text)."""
    results = ctx.results or {}
    n_files = len(ctx.file_list or [])
    n_bills = len(ctx.bills or [])
    n_comp = len(ctx.summary or {})
    mesh_stats = ctx.mesh.stats() if ctx.mesh is not None else {}

    L: List[str] = []
    L.append(_LINE)
    L.append("   ปุ้มปุ้ย v9 — รายงานสรุปการทำงานของ Agent (Notepad)")
    L.append(_LINE)
    L.append(f"   สร้างเมื่อ : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"   ข้อมูล    : {n_files} ไฟล์  |  {n_bills} บิล  |  {n_comp} บริษัท")
    if mesh_stats:
        L.append(f"   mesh      : {mesh_stats.get('total', 0)} ข้อสังเกต "
                 f"จาก {mesh_stats.get('agents', 0)} agent "
                 f"(แตะ {mesh_stats.get('bills_touched', 0)} บิล)")
    if ctx.report_path:
        L.append(f"   Excel     : {ctx.report_path}")
    L.append("")

    # ---- ภาพรวมตาราง ----
    L.append(_SUB)
    L.append("   ภาพรวมสายการผลิต (เรียงตามลำดับการทำงาน)")
    L.append(_SUB)
    L.append(f"   {'#':>2}  {'agent':<12} {'สถานะ':<8} {'ข้อสังเกต':>9}  {'เวลา(s)':>8}")
    idx = 0
    for name in _ORDER:
        res = results.get(name)
        if res is None:
            continue
        idx += 1
        L.append(f"   {idx:>2}  {name:<12} {_status_th(res.status):<8} "
                 f"{len(res.findings):>9}  {res.duration_s:>8.3f}")
    L.append("")

    # ---- รายละเอียดราย agent ----
    L.append(_LINE)
    L.append("   รายละเอียดราย Agent (แยกเป็นตัว ๆ ว่าทำงานอะไร พบอะไร)")
    L.append(_LINE)
    L.append("")
    idx = 0
    for name in _ORDER:
        res = results.get(name)
        if res is None:
            continue
        idx += 1
        L.extend(_render_agent_block(idx, name, res))

    # ---- ส่วน SuperAgent ----
    L.extend(_render_super_section(results.get("super")))

    # ---- ส่วนทีมผู้ตรวจเชิงกลไก (Inspection Bank) ----
    L.extend(_render_inspection_board(results.get("verification")))

    # ---- [ADD-ON v9.2] ตรวจหน่วยสินค้าเพิ่มเติม (advisory) ----
    #   อ่าน ctx.bills อย่างเดียว → ไม่กระทบผลตรวจหลัก/byte-identical. ห่อ try กันส่วนเสริมล้มรายงาน.
    try:
        L.extend(_render_unit_consistency(ctx.bills))
    except Exception:
        pass

    # ---- footer ----
    L.append(_LINE)
    L.append("   หมายเหตุ")
    L.append(_LINE)
    L.append("   • รายงานนี้เป็นชั้นคำแนะนำ (advisory) — ไม่กระทบผลตรวจหลัก/ไฟล์ Excel")
    L.append("   • ผลตรวจที่เป็นทางการพิสูจน์ byte-identical แยกต่างหาก (golden_master/verify_golden)")
    L.append("   • finding ทั้งหมดให้คนเป็นผู้ตัดสินใจสุดท้าย")
    L.append(_LINE)
    return "\n".join(L)
