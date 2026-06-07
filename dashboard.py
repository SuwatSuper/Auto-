# -*- coding: utf-8 -*-
"""dashboard.py — ปุ้มปุ้ย Dashboard (โปรแกรมหน้าต่างเดียว คลิกทีเดียวตรวจจบ)

เป้า: ผู้ใช้ดับเบิลคลิก .exe → เลือกโฟลเดอร์ไฟล์บิล → กด "เริ่มตรวจ" → เห็นผล + เปิดรายงานได้เลย
  โดย **ไม่ต้องเปิด VS Code / เทอร์มินัล / Python**. คุมทุกอย่างจากหน้าต่างนี้.

สถาปัตยกรรม (สำคัญ — กันพังตอน build .exe + ให้เทสแบบ headless ได้):
  • `run_audit(...)` = controller ล้วน (ไม่ใช้ tkinter) → เรียก agents.orchestrator.run_pipeline
    (ตรรกะตรวจเดิม → golden ไม่ขยับ) คืน dict สรุป + path รายงาน. ทดสอบได้โดยไม่ต้องมีจอ.
  • `launch()` = ชั้น GUI (import tkinter แบบ lazy ข้างใน) → เครื่องที่ไม่มี Tk ยัง `import dashboard` ได้.
  • รันแบบ in-process (ไม่ subprocess) → ทำงานได้ทั้งตอนเป็นสคริปต์และตอนเป็น .exe (PyInstaller frozen).

⚠️ ADVISORY UI ONLY: ไม่แตะ engine/ผลตรวจ — แค่ "หน้าควบคุม" ที่เรียก pipeline เดิม.
   build เป็น .exe: ดู BUILD_EXE_TH.md (รัน build.bat บน Windows ครั้งเดียว).
"""
from __future__ import annotations

import glob
import io
import os
import sys
import threading
import traceback
from datetime import datetime

APP_TITLE = "ปุ้มปุ้ย — ตรวจใบกำกับภาษี (Dashboard)"


# ──────────────────────────────────────────────────────────────────────────
# CONTROLLER (ไม่มี tkinter — เทส headless ได้)
# ──────────────────────────────────────────────────────────────────────────
def resolve_files(data_dir):
    """หาไฟล์ .xls/.xlsx ในโฟลเดอร์ (เรียงชื่อ → ผลคงที่ เหมือน run_agents)."""
    data = data_dir or "."
    return sorted(glob.glob(os.path.join(data, "*.xls")) +
                  glob.glob(os.path.join(data, "*.xlsx")))


def _load_master(path):
    import json
    for p in ([path] if path else ["master_companies.json"]):
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}


def _summarize(bills, master_present):
    """นับ บริษัท/ตรง/รีเช็ค จาก super_ultra_viewer (advisory) — ไม่ล้มถ้าโมดูลมีปัญหา."""
    try:
        import super_ultra_viewer as SUV
        rows = SUV.build(bills, master_present=master_present)
        n = len(rows)
        clean = sum(1 for r in rows if r.get("clean"))
        return {"n_companies": n, "n_clean": clean, "n_recheck": n - clean}
    except Exception:
        return {"n_companies": 0, "n_clean": 0, "n_recheck": 0}


def run_audit(data_dir, report_dir=None, master_path=None, full=False, log=None):
    """รันสายตรวจครบ (parse → rules → agents → เขียน Excel + รายงานลูกค้า .txt).

    คืน dict: ok / error / report_path / report_dir / n_files / n_bills /
              n_companies / n_clean / n_recheck. **ไม่ throw** (จับ error ใส่ dict).
    """
    log = log or (lambda m: None)
    out = {"ok": False, "error": "", "report_path": "", "report_dir": "",
           "n_files": 0, "n_bills": 0, "n_companies": 0, "n_clean": 0, "n_recheck": 0}
    try:
        files = resolve_files(data_dir)
        out["n_files"] = len(files)
        if not files:
            out["error"] = "ไม่พบไฟล์ .xls/.xlsx ในโฟลเดอร์ที่เลือก"
            return out
        report_dir = report_dir or os.path.join(os.getcwd(), "audit_reports")
        os.makedirs(report_dir, exist_ok=True)
        out["report_dir"] = report_dir

        from agents.orchestrator import run_pipeline
        master = _load_master(master_path)
        options = {
            "write_report": True, "lean": not full, "report_dir": report_dir,
            "write_vendor_report": True, "vendor_report_dir": report_dir,
            "vendor_report_memo": None, "enable_ai": False,
            "llm_provider": "null", "llm_base_url": None, "llm_model": None,
            "ai_max_items": 60,
        }
        log(f"▶ เริ่มตรวจ {len(files)} ไฟล์ …")
        ctx = run_pipeline(master, files, options, logger=log)
        out["n_bills"] = len(getattr(ctx, "bills", []) or [])
        out["report_path"] = getattr(ctx, "report_path", "") or ""
        out.update(_summarize(getattr(ctx, "bills", []) or [], bool(master)))
        out["ok"] = True
        log(f"✅ เสร็จ — {out['n_companies']} บริษัท · ตรง {out['n_clean']} · "
            f"รีเช็ค {out['n_recheck']}")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        log("❌ ผิดพลาด: " + out["error"])
        log(traceback.format_exc())
    return out


def open_path(path):
    """เปิดไฟล์/โฟลเดอร์ด้วยโปรแกรมเริ่มต้นของ OS (Windows/mac/Linux)."""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)               # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────
# GUI (tkinter — import แบบ lazy ให้ headless import ได้)
# ──────────────────────────────────────────────────────────────────────────
class _LogRedirect(io.TextIOBase):
    """ดัก stdout/stderr ของ pipeline (มี print/tqdm) ส่งเข้า callback — กัน .exe แบบ
       no-console ที่ sys.stdout=None แล้ว print ครัช."""
    def __init__(self, cb):
        self._cb = cb

    def write(self, s):
        s = (s or "").rstrip("\n")
        if s.strip():
            try:
                self._cb(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        pass


def launch():  # pragma: no cover  (ต้องมีจอ/Tk — เทสครอบ run_audit แทน)
    import tkinter as tk
    from tkinter import filedialog, ttk

    state = {"data": "", "master": "", "result": None}
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("720x540")

    frm = ttk.Frame(root, padding=14)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="ปุ้มปุ้ย — ตรวจใบกำกับภาษี", font=("TH Sarabun New", 18, "bold")).pack(anchor="w")
    data_var = tk.StringVar(value="(ยังไม่ได้เลือกโฟลเดอร์)")
    master_var = tk.StringVar(value="(ไม่ใช้ master)")

    def pick_data():
        d = filedialog.askdirectory(title="เลือกโฟลเดอร์ไฟล์บิล (.xls/.xlsx)")
        if d:
            state["data"] = d
            n = len(resolve_files(d))
            data_var.set(f"{d}   ({n} ไฟล์)")

    def pick_master():
        f = filedialog.askopenfilename(title="เลือกไฟล์ master_companies.json (ถ้ามี)",
                                       filetypes=[("JSON", "*.json"), ("ทั้งหมด", "*.*")])
        if f:
            state["master"] = f
            master_var.set(f)

    row1 = ttk.Frame(frm); row1.pack(fill="x", pady=(12, 4))
    ttk.Button(row1, text="📁 เลือกโฟลเดอร์ไฟล์บิล", command=pick_data).pack(side="left")
    ttk.Label(row1, textvariable=data_var).pack(side="left", padx=10)
    row2 = ttk.Frame(frm); row2.pack(fill="x", pady=4)
    ttk.Button(row2, text="🗂 master (ไม่บังคับ)", command=pick_master).pack(side="left")
    ttk.Label(row2, textvariable=master_var).pack(side="left", padx=10)

    bar = ttk.Progressbar(frm, mode="indeterminate")
    status = tk.StringVar(value="พร้อมตรวจ")
    result_var = tk.StringVar(value="")
    log_box = tk.Text(frm, height=12, wrap="word")

    def set_busy(busy):
        for w in (btn_run, btn_xlsx, btn_dir):
            w.config(state="disabled" if busy else "normal")
        if busy:
            bar.pack(fill="x", pady=8); bar.start(12)
        else:
            bar.stop(); bar.pack_forget()

    def log(msg):
        root.after(0, lambda: (log_box.insert("end", str(msg) + "\n"), log_box.see("end")))

    def worker():
        old = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = _LogRedirect(log)
        try:
            res = run_audit(state["data"], master_path=(state["master"] or None), log=log)
        finally:
            sys.stdout, sys.stderr = old
        state["result"] = res

        def done():
            set_busy(False)
            if res["ok"]:
                status.set("เสร็จแล้ว ✅")
                result_var.set(f"{res['n_companies']} บริษัท · ตรง {res['n_clean']} · "
                               f"รีเช็ค {res['n_recheck']}  (จาก {res['n_files']} ไฟล์ / "
                               f"{res['n_bills']} บิล)")
            else:
                status.set("ผิดพลาด ❌")
                result_var.set(res["error"])
        root.after(0, done)

    def start():
        if not state["data"]:
            status.set("⚠ ยังไม่ได้เลือกโฟลเดอร์ไฟล์บิล"); return
        log_box.delete("1.0", "end")
        status.set("กำลังตรวจ … (อย่าปิดหน้าต่าง)")
        set_busy(True)
        threading.Thread(target=worker, daemon=True).start()

    rowb = ttk.Frame(frm); rowb.pack(fill="x", pady=10)
    btn_run = ttk.Button(rowb, text="✅ เริ่มตรวจ", command=start)
    btn_run.pack(side="left")
    btn_xlsx = ttk.Button(rowb, text="📂 เปิด Excel",
                          command=lambda: open_path((state["result"] or {}).get("report_path", "")))
    btn_xlsx.pack(side="left", padx=6)
    btn_dir = ttk.Button(rowb, text="📁 เปิดโฟลเดอร์รายงาน",
                         command=lambda: open_path((state["result"] or {}).get("report_dir", "")))
    btn_dir.pack(side="left")

    ttk.Label(frm, textvariable=status, font=("TH Sarabun New", 12)).pack(anchor="w", pady=(6, 0))
    ttk.Label(frm, textvariable=result_var, font=("TH Sarabun New", 13, "bold")).pack(anchor="w")
    log_box.pack(fill="both", expand=True, pady=(8, 0))
    log("พร้อมใช้งาน — เลือกโฟลเดอร์ไฟล์บิลแล้วกด 'เริ่มตรวจ'")
    root.mainloop()


if __name__ == "__main__":
    try:
        from hashseed_guard import enforce_hashseed
        enforce_hashseed()           # ผลตรวจตรงเงื่อนไข golden แม้รันนอก VS Code
    except Exception:
        pass
    launch()
