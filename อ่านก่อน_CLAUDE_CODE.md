# อ่านก่อน — ชุดส่งให้ Claude Code (ฉบับ < 30MB)

ชุดนี้คือ **ระบบปุ้มปุ้ย v9.3.4 ฉบับเต็ม (source + corpus + tests + INVARIANTS + baseline)** สำหรับป้อนเข้า **Claude Code** เพื่อ harden ต่อ.

## วิธีใช้
1. แตกไฟล์ด้วย Python `zipfile` (อย่าใช้ `unzip` — ชื่อไทยจะเพี้ยน):
   ```python
   import zipfile; zipfile.ZipFile('<ไฟล์นี้>.zip').extractall('puopuy')
   ```
2. เปิด Claude Code ที่โฟลเดอร์ที่แตก แล้ว **วางเนื้อหาไฟล์ `PROMPT_HARDEN_CLAUDE_CODE_TH.md` ทั้งก้อนเป็นพร้อมท์**.
3. Claude Code จะทำตามขั้น: ติดตั้ง dep (มีเน็ต) → ด่าน sanity (ต้องได้ golden `23b315e8`) → harden 3 รอบ → ผ่าน gate ครบ → re-vendor → `make_release` → ส่งระบบสมบูรณ์.

## ⚠️ สิ่งที่ถอดออก (เพื่อให้ไฟล์ < 30MB)
- `vendor/wheels/` (wheelhouse offline 73MB) **ถูกถอดออก**. Claude Code ติดตั้งจาก PyPI ด้วยเวอร์ชันตรึงใน `constraints.txt` แล้ว re-vendor กลับตอนทำ release สุดท้าย (ดู §3 และ §10 ในพร้อมท์).
- caches/artifacts (`__pycache__`, `.ruff_cache`, `.coverage*`, `snapshot.json`, `master_companies.json` stub) — regenerate เองได้.

ทุกอย่างที่จำเป็นต่อการ reproduce golden `23b315e8` (โค้ด + `corpus/` 148 ไฟล์ + `baseline.json` + `constraints.txt`) อยู่ครบในชุดนี้.

> รายละเอียดทั้งหมด + กฎเหล็ก (INVARIANTS) อยู่ใน `PROMPT_HARDEN_CLAUDE_CODE_TH.md`
