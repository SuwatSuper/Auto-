# ปุ้มปุ้ย v9.1 — ระบบตรวจใบกำกับภาษี (offline VAT audit)

ระบบตรวจสอบใบกำกับภาษีจากไฟล์ Excel แบบ deterministic (ผลตรวจ reproduce ได้ด้วย golden hash)
รันแบบ **โมดูล** — ตัวหลัก `ปุ้มปุ้ย_ultimate_v9_modular.py` import โมดูลอื่น (parser / rules_engine / reporting / …)

---

## เปิดใน VS Code

1. เปิดโฟลเดอร์นี้ (`File → Open Folder`)
2. ติดตั้งส่วนขยายที่แนะนำ (VS Code จะถามให้เอง): **Python**, **Python Debugger**
3. เลือก Python interpreter (`Ctrl/Cmd+Shift+P → Python: Select Interpreter`) — แนะนำ venv:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```
4. รัน Task **"1. ติดตั้ง dependencies"** (`Ctrl/Cmd+Shift+P → Tasks: Run Task`)
   หรือสั่งเอง:
   ```bash
   pip install -r requirements.txt -c constraints.txt
   ```

> ⚠️ ต้องใช้เวอร์ชันที่ล็อกใน `constraints.txt` (pandas 2.2.2 / xlrd 2.0.1 / openpyxl 3.1.5 /
> rapidfuzz 3.10.1) มิฉะนั้น golden hash อาจไม่ตรง. `version_gate.py` จะเตือนถ้าเวอร์ชันต่าง.

---

## รัน / ทดสอบ (ผ่าน VS Code)

**Run/Debug** (กด F5 เลือก config):
- ▶ **รันระบบ (production)** — ใช้ "วันที่จริง"
- 🔒 **Golden master** — สร้าง snapshot + hash (sandbox)
- ✅ **Regression บนข้อมูลจริง** — ถามโฟลเดอร์ข้อมูล แล้วตรวจว่าได้ `35b2f7c8…`
- ⚡ **Verify parallel == serial**
- 🐞 **Debug ไฟล์เทสที่เปิดอยู่**

**Tasks** (`Tasks: Run Task`):
| Task | ทำอะไร |
|---|---|
| 1. ติดตั้ง dependencies | `pip install` เวอร์ชันล็อก |
| 2. CI เต็ม | gate + invariants + smoke + เทส + regression(fixture) — *Default Test Task* |
| 2b. CI + ข้อมูลจริง | เพิ่ม regression เต็มบนโฟลเดอร์ที่ระบุ (`35b2f7c8`) |
| 3. Golden (sandbox) | golden hash → `35b2f7c8` |
| 4. Invariant tripwire | golden fixture + pin (เร็ว) |
| 5. Coverage gate | line ≥ 90% / รายงาน branch |
| 6. Verify parallel | พิสูจน์ parallel == serial |

สั่งจากเทอร์มินัลก็ได้ (อย่าลืม env):
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02
bash run_ci.sh                       # CI เต็ม
python3 regression_full.py . <โฟลเดอร์ข้อมูลจริง>    # ต้องได้ 35b2f7c8 ทั้ง 3 บรรทัด
```

---

## ตัวแปรสภาพแวดล้อม (สำคัญ)

| env | ค่า | ผล |
|---|---|---|
| `PYTHONHASHSEED` | `0` | จำเป็นต่อการ reproduce hash (ตั้งให้แล้วใน terminal/tasks) |
| `PUOPUY_AUDIT_DATE` | `YYYY-MM-DD` | ปัก "วันที่ตรวจ" เพื่อให้กฎวันที่นิ่ง — **โหมดทดสอบ/golden** ใช้ `2026-06-02` ; **production ไม่ต้องตั้ง** (ใช้วันนี้) |
| `PUOPUY_COV_MIN` | `90` | เกณฑ์ line coverage |
| `PUOPUY_COV_BRANCH_MIN` | (ไม่ตั้ง) | เปิดบังคับ branch coverage เมื่อกำหนด (เช่น `79`) |

---

## Invariants (ห้ามขยับโดยไม่ตั้งใจ)

> 📌 สับสนเรื่องค่า hash? ดู **`GOLDEN.md`** — แหล่งอ้างอิงเดียวที่อธิบายทุกค่า (ปัจจุบัน/ปลดระวาง/fixture/report).

| สิ่ง | hash | ตรวจด้วย |
|---|---|---|
| Golden ทางการ (106 ไฟล์ `/mnt/project`, 834 บิล) | `35b2f7c8…` | `regression_full.py . /mnt/project` |
| Fixture เร็ว (3 บิล, ไม่ต้องใช้ข้อมูลจริง) | ดู `tests/fixtures/baseline_fixture.json` | `INVARIANTS/check_invariants.py` |
| Golden fixture (3 บิล, เร็ว) | `d8bcde85…` | `INVARIANTS/check_invariants.py` |
| Report (normalize timestamp) | `fff69fc6…` | `verify_report_det.py` |

มี **pre-commit hook** (`hooks/pre-commit`, ติดตั้งด้วย `INVARIANTS/install_hooks.sh`) บล็อก commit
ที่ทำ fixture golden หรือ pin test พัง. รายละเอียดการตัดสินใจ/ADR ทั้งหมดอยู่ใน **`INVARIANTS/DECISIONS.md`**

---

## ที่ปรับปรุงในเวอร์ชันนี้ (สรุป)

- **OBJ-MAINT**: ซอย `rules_engine.py`/`parser.py`/`reporting.py` → ทุกไฟล์ ≤ 600 บรรทัด (byte-identical, golden ไม่ขยับ)
- **OBJ-PERF**: parse `46.9s → ~9s ≈ 5.3×` (single-core, ผลทุกชั้น byte-identical) + `parallel_audit.py` (ขนานหลายคอร์, opt-in)
- เครื่องมือใหม่: `verify_report_det.py`, `verify_parallel.py`

> `parse_all_files_parallel` (ใน `parallel_audit.py`) เป็น opt-in ไม่แตะ path เดิม.
> ก่อนใช้จริงให้รัน Task 6 / `verify_parallel.py <data> <workers>` ยืนยัน `serial == parallel` บนข้อมูลของคุณ
> (sandbox ที่นี่ system-issues = 0 จึงยังไม่ stress path การ merge issues — ข้อมูลจริงคือบททดสอบ).

---

## โครงสร้างย่อ

```
ปุ้มปุ้ย_ultimate_v9_modular.py   ตัวหลัก (orchestrator)
parser.py + parser_p0..p2.py       อ่าน/แยกบิลจาก Excel
rules_engine.py + _base/_rules_a..c.py   เครื่องกฎตรวจ
reporting.py + reporting_p0..p2.py  สร้างรายงาน Excel
validators.py / config.py / state.py / puopuy_*.py / thai_text.py / diagnostics.py
golden_*.py / verify_*.py / regression_full.py / coverage_gate.py / run_ci.sh   ตาข่ายความปลอดภัย
INVARIANTS/DECISIONS.md            บันทึก ADR + invariants
```
