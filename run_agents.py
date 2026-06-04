#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_agents.py — ตัวรันระบบแบบ "ไม่โต้ตอบ" (ไม่มี input()) ผ่าน agent ทั้ง 7

ต่างจาก main() เดิม (ซึ่งถาม-ตอบทาง stdin) — ตัวนี้รับค่าจาก argument/ตัวแปรแวดล้อม
เหมาะกับการรันอัตโนมัติ / ใน CI / เรียกจากสคริปต์อื่น

ตัวอย่าง:
    # รันบนข้อมูลในโฟลเดอร์ แล้วออก Excel แบบคลีน (ค่าเริ่มต้น)
    python3 run_agents.py --data /path/to/bills --report-dir ./out

    # โหมดเต็ม + เปิด AI review ด้วย Ollama (Local LLM) ที่เครื่อง
    python3 run_agents.py --data ./bills --full --ai --llm-provider ollama \
        --llm-model llama3.1 --llm-base-url http://localhost:11434

    # เปิด AI review แบบ "จำลอง" (ทดสอบสายเชื่อมโดยไม่ต้องมีโมเดลจริง)
    python3 run_agents.py --data ./bills --ai --llm-provider mock

ผลลัพธ์:
    1) ไฟล์ Excel ผลตรวจ (เหมือนเดิม) ใน --report-dir
    2) ไฟล์ findings_<timestamp>.json — ข้อสังเกตเชิงคำแนะนำจากทุก agent (advisory)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime


def _load_master(path: str | None) -> dict:
    """โหลด master จากไฟล์ JSON (ถ้าระบุ/มีอยู่) — ไม่งั้นคืน dict ว่าง (ตรวจได้แต่ไม่ enrich)."""
    candidates = [path] if path else ["master_companies.json"]
    for p in candidates:
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  อ่าน master '{p}' ไม่ได้: {e}", file=sys.stderr)
    return {}


def _resolve_files(args) -> list:
    """หา file_list จาก --files หรือ glob --data (เรียงชื่อ เพื่อผลคงที่)."""
    if args.files:
        return list(args.files)
    data = args.data or "."
    files = sorted(glob.glob(os.path.join(data, "*.xls")) +
                   glob.glob(os.path.join(data, "*.xlsx")))
    return files


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ปุ้มปุ้ย v9 — สายการผลิตตรวจสอบบิลแบบ multi-agent (ไม่โต้ตอบ)")
    src = p.add_argument_group("แหล่งข้อมูล")
    src.add_argument("--data", default=os.environ.get("PUKPUI_DATA_DIR"),
                     help="โฟลเดอร์ที่มีไฟล์ .xls/.xlsx (จะ glob เรียงชื่อ)")
    src.add_argument("--files", nargs="*", help="ระบุไฟล์ตรงๆ (แทน --data)")
    src.add_argument("--master", default=os.environ.get("PUKPUI_MASTER"),
                     help="ไฟล์ master_companies.json (ค่าเริ่มต้น: ./master_companies.json ถ้ามี)")

    out = p.add_argument_group("ผลลัพธ์")
    out.add_argument("--report-dir", default=os.environ.get("PUKPUI_REPORT_DIR"),
                     help="โฟลเดอร์เก็บ Excel (ค่าเริ่มต้น: ./audit_reports)")
    out.add_argument("--full", action="store_true",
                     help="ออกรายงานแบบเต็ม (export_excel + ภงด.53) แทนแบบคลีน")
    out.add_argument("--no-report", action="store_true",
                     help="ไม่เขียน Excel (วิเคราะห์/พิมพ์ findings อย่างเดียว)")
    out.add_argument("--findings-out", default=None,
                     help="ที่เก็บไฟล์ findings JSON (ค่าเริ่มต้น: <report-dir>/findings_<ts>.json)")

    ai = p.add_argument_group("AI Review (Local LLM)")
    ai.add_argument("--ai", dest="ai", action="store_true",
                    help="เปิด AI Review Agent (ผู้ตรวจคนที่สอง — advisory)")
    ai.add_argument("--no-ai", dest="ai", action="store_false", help="ปิด AI Review (ค่าเริ่มต้น)")
    p.set_defaults(ai=False)
    ai.add_argument("--llm-provider", default=os.environ.get("LLM_PROVIDER", "ollama"),
                    choices=["ollama", "openai", "mock", "null"],
                    help="ชนิด provider (ollama=Local LLM, openai=llama.cpp/LM Studio, mock=จำลอง)")
    ai.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL"),
                    help="URL ของ LLM server (เช่น http://localhost:11434)")
    ai.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"),
                    help="ชื่อโมเดล (เช่น llama3.1)")
    ai.add_argument("--ai-max-items", type=int, default=int(os.environ.get("AI_MAX_ITEMS", "60")),
                    help="จำนวนรายการสูงสุดที่ส่งให้ LLM triage (กัน prompt ยาวเกิน)")

    p.add_argument("-q", "--quiet", action="store_true", help="ลด log ระหว่างรัน")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    # import ที่นี่ (หลัง parse) เพื่อให้ --help เร็ว และ error import อ่านง่าย
    from agents.orchestrator import run_pipeline
    from agents.base import AgentError

    master = _load_master(args.master)
    file_list = _resolve_files(args)
    if not file_list:
        print("❌ ไม่พบไฟล์ .xls/.xlsx — ระบุ --data <โฟลเดอร์> หรือ --files <ไฟล์...>",
              file=sys.stderr)
        return 2

    options = {
        "write_report": not args.no_report,
        "lean": not args.full,
        "report_dir": args.report_dir,
        "enable_ai": bool(args.ai),
        "llm_provider": args.llm_provider,
        "llm_base_url": args.llm_base_url,
        "llm_model": args.llm_model,
        "ai_max_items": args.ai_max_items,
        # หมายเหตุ: ตัวรันนี้ resolve file_list เองเสมอ (จาก --files/--data) แล้วส่งให้ pipeline
        #   → ImportAgent ใช้ file_list ตรง ๆ ไม่แตะสาขา 'source' (เดิมตั้ง source='drive'
        #     ซึ่งทั้ง dead และทำให้เข้าใจผิดว่าดึงจาก Google Drive). ละไว้เพื่อความตรงไปตรงมา.
    }

    logger = (lambda msg: None) if args.quiet else (lambda msg: print(msg))

    print(f"▶️  เริ่มตรวจ {len(file_list)} ไฟล์  "
          f"(โหมด={'เต็ม' if args.full else 'คลีน'}, AI={'เปิด' if args.ai else 'ปิด'})")
    try:
        ctx = run_pipeline(master, file_list, options, logger=logger)
    except AgentError as e:
        print(f"\n❌ หยุด: agent สำคัญล้มเหลว — {e}", file=sys.stderr)
        return 1

    # ---- สรุปผลแต่ละ agent ----
    print("\n" + "=" * 64)
    print("สรุปผลแต่ละ agent")
    print("=" * 64)
    for name, res in ctx.results.items():
        line = f"  {name:10s} : {res.status:8s}  ({len(res.findings)} findings, {res.duration_s:.3f}s)"
        if res.error:
            line += f"  ⚠️ {res.error.splitlines()[0]}"
        print(line)

    if ctx.report_path:
        print(f"\n📄 Excel: {ctx.report_path}")

    # ---- เขียน findings (advisory) เป็น JSON sidecar ----
    findings_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_files": len(file_list),
        "n_bills": len(ctx.bills),
        "report_path": ctx.report_path,
        "agents": {name: res.to_dict() for name, res in ctx.results.items()},
    }
    fout = args.findings_out
    if not fout:
        base_dir = (args.report_dir or os.path.join(os.getcwd(), "audit_reports"))
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            base_dir = os.getcwd()
        fout = os.path.join(base_dir, f"findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    try:
        with open(fout, "w", encoding="utf-8") as f:
            json.dump(findings_payload, f, ensure_ascii=False, indent=2)
        print(f"📝 ข้อสังเกต (advisory): {fout}")
    except Exception as e:
        print(f"⚠️  เขียน findings ไม่ได้: {e}", file=sys.stderr)

    # exit code = 0 เสมอถ้า pipeline ครบ (advisory findings ไม่ใช่ 'failure')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
