# อ่านก่อน — ชุดส่งให้ Claude Code (งาน: แก้ master-join · ฉบับ < 30MB)

ชุดนี้ = **ระบบปุ้มปุ้ย v9.3.4 ฉบับ hardened ล่าสุด (ADR ถึง 145)** + corpus + tests สำหรับป้อนเข้า **Claude Code** เพื่อแก้เส้นทาง master ให้พร้อมใช้ 5 ปี.

## 👉 พร้อมท์ของงานนี้
เปิดไฟล์ **`PROMPT_FIX_MASTER_JOIN_CLAUDE_CODE_TH.md`** แล้ววางทั้งก้อนเป็นพร้อมท์ใน Claude Code.
(สรุปงาน: 🔴 เปลี่ยน join master จาก fuzzy-name → tax_id · 🟡 เพิ่ม identity-golden coverage · 🟡 เสริม test parse ภ.พ.20 — ทั้งหมด golden-neutral, main golden `23b315e8` ห้ามขยับ)

## วิธีใช้
1. แตกด้วย Python `zipfile` (อย่าใช้ `unzip` — ชื่อไทยเพี้ยน):
   ```python
   import zipfile; zipfile.ZipFile('<ไฟล์นี้>.zip').extractall('puopuy')
   ```
2. ติดตั้ง dep (มีเน็ต, เวอร์ชันตรึง):
   ```bash
   pip install -r requirements.txt -c constraints.txt --break-system-packages
   ```
3. **ด่าน sanity ก่อนแตะโค้ด** — ต้องได้ golden `23b315e8`:
   ```bash
   find . -name __pycache__ -type d -exec rm -rf {} + ; find . -name '*.pyc' -delete
   PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 python3 regression_full.py . corpus
   ```
4. วาง `PROMPT_FIX_MASTER_JOIN_CLAUDE_CODE_TH.md` → Claude Code ทำตาม → ผ่าน gate → `make_release` → ส่งระบบ.

## ⚠️ ที่ถอดออก (เพื่อให้ < 30MB)
- `vendor/wheels/` (wheelhouse offline 73MB) — ติดตั้งจาก PyPI ด้วย `constraints.txt` แล้ว re-vendor กลับตอน release สุดท้าย (ดู §6 ในพร้อมท์หลัก `PROMPT_HARDEN_CLAUDE_CODE_TH.md`).
- caches/artifacts (`__pycache__`, `.ruff_cache`, `.coverage*`, จาก golden run) — regenerate เองได้.

ทุกอย่างที่จำเป็นต่อ golden `23b315e8` (โค้ด ADR-145 + `corpus/` 148 + `baseline.json` + `.vscode/` + `constraints.txt`) อยู่ครบ.

## บริบทเพิ่มเติม (ในชุดมีให้)
- `PROMPT_HARDEN_CLAUDE_CODE_TH.md` — กฎเหล็ก/INVARIANTS เต็ม + ขั้น re-vendor + make_release
- `INVARIANTS/DECISIONS.md` — ADR ledger (append-only, ถึง ADR-145)
