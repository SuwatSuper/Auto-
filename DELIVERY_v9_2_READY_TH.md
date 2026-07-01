# DELIVERY — ปุ้มปุ้ย v9.2 (พร้อมรัน) — สรุปสำหรับ build นี้

แตกซิป → เปิดโฟลเดอร์ใน VS Code → รันได้เลย. ไฟล์นี้คือ "อ่านก่อน 1 หน้า"; รายละเอียดเต็มดู
`QUICKSTART_VSCODE_TH.md` (วิธีใช้) และ `PARALLEL_MERGE_FOLLOWUP_TH.md` (สิ่งที่แก้รอบนี้).

---

## ✅ สถานะ build
- โค้ดทั้งหมด = v9.2 + **hardening parallel-merge รอบนี้** (3+1 latent bug แก้แล้ว, มี regression
  gate ใหม่กันถอยหลัง). รายละเอียด + RED→GREEN: `PARALLEL_MERGE_FOLLOWUP_TH.md`.
- **golden = `35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba`** (106 ไฟล์/834 บิล)
  — ก่อน/หลังแก้เป๊ะ. fix เป็น surgical ไม่แตะ business logic.
- CI เขียวครบ (เทสทั้งหมด + ruff + regression engine==agent==baseline).

## ⚡ ความเร็ว (วัดจริง บน 106 ไฟล์/834 บิล)
- รัน production จริง (Task 4) = **~13 วินาที** (≈15 ms/บิล) → **~3000 บิล ≈ 46 วินาที** สบาย ๆ
- parser กิน ~99% ของเวลา (รู้ไว้สำหรับ optimize ภายหลัง). ไม่ต้องเปิด parallel ก็ทันสำหรับวันละ 3000 บิล.
- ถ้าอยากเร็วขึ้นอีก (ข้อมูลเยอะมาก): เปิด process pool ผ่าน path หลัก —
  `PUOPUY_PARALLEL=<จำนวน core> python3 main.py` (ผลเท่า serial เป๊ะ; พิสูจน์ด้วย Task 7).

---

## 🚀 เริ่มใช้ (VS Code — กดผ่าน Run Task)
1. **Task 0** — Bootstrap: สร้าง `.venv` (Python 3.12) + ติดตั้ง deps ตาม `constraints.txt`
   จากนั้นเลือก interpreter เป็น `.venv` (`Ctrl/Cmd+Shift+P → Python: Select Interpreter`)
2. **Task 1** — Doctor: เช็คความพร้อม (Python/deps/env)
3. วางไฟล์ `.xls/.xlsx` ที่จะตรวจไว้ในโฟลเดอร์ (เช่น `data/`)
4. **Task 4** — รัน Audit จริง → ใส่ path โฟลเดอร์ข้อมูล → ได้รายงาน Excel ใน `reports/`
   + สรุปรายบริษัท `.txt`

รันแบบ CLI ก็ได้:
```bash
python3 run_agents.py --data /path/to/bills --report-dir reports     # ไม่โต้ตอบ, วันที่จริง
```

---

## ⚠️ เปลี่ยนแปลงสำคัญใน build นี้: วันที่ตรวจ (production = วันจริง)

เดิม `.env` และ `.vscode/tasks.json` **ปัก** `PUOPUY_AUDIT_DATE=2026-06-02` ให้ทุกการรัน รวม Task 4
→ การตรวจจริงรายวัน จะใช้วันที่ค้าง (กฎที่อิง "วันนี้" เพี้ยน). build นี้แก้ให้ถูกต้องเชิง production:

- **Task 4 / 4b (รันจริง) + การกด Run (.env)** → ใช้ **วันที่จริง** แล้ว (ถูกต้องสำหรับงานรายวัน)
- **Task 2 / 3 / 3b / 5 / 7 (เช็ค golden/regression)** → ยัง **ปักวันที่ 2026-06-02** ให้เอง
  → reproduce `35b2f7c8…` ได้เสมอ ไม่ว่ารันวันไหน

> หมายเหตุ: ตรวจแล้วว่า golden **ไม่ผูกกับวันที่** บน corpus นี้ (รันวันจริงก็ได้ `35b2f7c8…` เท่าเดิม)
> ถ้าต้องการปักวันที่ตอนรันจริง (เช่น ตรวจย้อนหลัง): ตั้ง env `PUOPUY_AUDIT_DATE=YYYY-MM-DD` ตอนรัน
> หรือเปิดคอมเมนต์บรรทัดใน `.env`.

---

## 🔒 กฎเหล็ก (อย่าลืม)
- ต้องรันบน **Python 3.12** + deps ตาม `constraints.txt` (golden ผูกกับชุดนี้)
- ทุกการเช็ค golden ตั้ง `PYTHONHASHSEED=0` (tasks/CI ตั้งให้แล้ว)
- ถ้า hash ขยับโดยไม่ตั้งใจ = **หยุด ย้อน หาเหตุ ห้าม commit**
- ก่อน commit: รัน **Task 3** (CI) หรือ `bash run_ci.sh` ให้เขียวก่อน

## ตรวจสุขภาพระบบเร็ว ๆ หลังแตกซิป
```bash
# 1) regression บนข้อมูลจริง 106 ไฟล์ (ต้องได้ 35b2f7c8 + engine==agent==baseline)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . /path/to/106files
# 2) parallel == serial
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_parallel.py /path/to/106files 4
# 3) เทส merge ใหม่ (กันถอยหลัง)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_parallel_merge_contract.py
```
