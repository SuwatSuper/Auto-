# QUICKSTART — ปุ้มปุ้ย v9.3.4 บน VS Code (ฉบับ Offline)

คู่มือเริ่มใช้งานบนเครื่องตัวเอง ผ่าน VS Code แบบ **ออฟไลน์ล้วน** (ไม่ต้องต่อเน็ตหลังติดตั้ง deps ครั้งแรก).
ทุกอย่างกดผ่านเมนู **Terminal → Run Task…** (`Ctrl/Cmd+Shift+P` → "Run Task") ได้เลย ไม่ต้องจำคำสั่ง.

---

## 0) สิ่งที่ต้องมี (ครั้งเดียว)
- **Python 3.12** (สำคัญ — golden hash ผูกกับ 3.12). ตรวจ: `python3.12 --version` (Windows: `py -3.12 --version`)
- **VS Code** + ส่วนขยาย `ms-python.python` (เปิด workspace นี้แล้วกด "Install recommended extensions")
- **git** (ถ้าจะใช้ version control + pre-commit hook)

---

## 1) ติดตั้ง (Bootstrap) — Task `0`
`Run Task → "0. Bootstrap (สร้าง .venv Python 3.12 + ติดตั้ง deps ล็อก)"`

สร้าง virtualenv `.venv/` + ติดตั้ง dependency เวอร์ชันล็อกตาม `constraints.txt`
(หลังครั้งแรก ติดตั้งจาก cache ได้แบบออฟไลน์).

จากนั้น **เลือก interpreter**: `Ctrl/Cmd+Shift+P → Python: Select Interpreter → .venv`
(Windows เลือก `.venv\Scripts\python.exe`).

---

## 2) เช็คความพร้อม — Task `1` (Doctor)
`Run Task → "1. Doctor — ตรวจความพร้อมระบบ (เร็ว)"`

`doctor.py` บอกครบในจอเดียวว่า **พร้อมรันให้ผล reproduce ได้ไหม**:
Python ตรง 3.12 · deps ตรงล็อก · `PYTHONHASHSEED=0` · pre-commit hook · fixture ครบ
ถ้ามีปัญหา จะบอก "ต้องแก้อะไร" เป็นข้อ ๆ. เวอร์ชันเต็ม (+ tripwire จริง): Task `1b`.

---

## 3) ยืนยันระบบไม่พัง — Task `2` / `3`
- Task `2` — **tripwire** (~5s): golden fixture + pin (รันบ่อย ก่อน commit)
- Task `3` — **CI เต็ม**: version gate + invariants + smoke + เทสทั้งหมด + regression fixture + lint/coverage

> กฎเหล็ก: ถ้า hash ขยับโดยไม่ตั้งใจ = **หยุด ย้อน หาเหตุ ห้าม commit**

---

## 4) ใช้งานจริง (ตรวจบิล) — Task `4`
วางไฟล์ `.xls/.xlsx` ไว้ในโฟลเดอร์ (เช่น `data/` — ถูก gitignore ไม่ถูก push).

`Run Task → "4. รัน Audit จริง → รายงาน Excel (reports/)"` แล้วใส่ path โฟลเดอร์ข้อมูล
→ ได้รายงาน Excel ใน `reports/` + ไฟล์สรุป agent (`.txt`).

> โหมดนี้รัน pipeline **13 agent + 30 lenses** แบบไม่โต้ตอบ (ไม่ต้องพิมพ์เมนู).
> Task `4b` = โหมดพิสูจน์ (ไม่เขียนรายงาน). ทั้งคู่ใช้ **วันที่จริง** ตอน production (ไม่ปักวันที่).

---

## 5) ยืนยัน golden จริง (148 ไฟล์ `/mnt/project`) — Task `3b` / `5`
ครั้งแรกที่นำชุดข้อมูลทางการมา ให้ยืนยันว่าได้ hash `757751e7…`:
`Run Task → "5. Regression บนข้อมูลจริง"` → ใส่ path โฟลเดอร์ /mnt/project (148 ไฟล์)
ต้องเห็น `engine == agent == baseline ✅`.

---

## เครื่องมืออื่น (Tasks)
| Task | ทำอะไร |
|---|---|
| `6` | Coverage gate (line ≥90% / รายงาน branch) |
| `7` | Verify `serial == parallel` (ก่อนใช้ parallel จริง) |
| `8` | Format (black) + Lint (ruff) ไฟล์ที่เปิดอยู่ |
| `9` | ติดตั้ง git pre-commit hook (กัน golden พัง) |

## Debug (F5)
เมนู Run and Debug มี: 🩺 Doctor --full · ▶ รันระบบ · 🔒 Golden master · ✅ Regression · ⚡ Verify parallel · 🐞 Debug ไฟล์เทสที่เปิดอยู่.

---

## หมายเหตุความปลอดภัย (offline)
ระบบเป็น **offline ล้วน** (`offline_guard`) — ไม่มี outbound network ในเส้น audit.
ข้อมูลผู้เสียภาษีดิบ **ไม่ถูก commit** (โฟลเดอร์ `data/ reports/ audit_reports/` ถูก gitignore).
เวลารายงานผล/แชร์ ใช้ **hash/สรุป** ไม่ต้องแปะเนื้อข้อมูลดิบ.
