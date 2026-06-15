# Kingdom Prime — RECHECK & FIX REPORT (รีเช็คทั้งระบบ + แก้บั๊กคงค้าง)

> รีเช็คทั้งระบบแบบ adversarial · รันจริงทุกด้าน · แก้ทุกบั๊กที่เจอ (ร้าย/กลาง/ต่ำ)
> ผลสุดท้าย: **824 passed, 1 skipped · coverage 91.17% · ruff ✅ · mypy --strict ✅ (132 ไฟล์)**
> boot-from-zero ✅ · soak 25s RSS นิ่ง (60.6→60.7MB ไม่ leak) ✅ · kill+reboot → state_restored ✅

---

## 🔢 สรุป
- **บั๊กที่เจอรอบนี้: 3** (S2 ×1, gate-fail ×1, S3 ×1) → **แก้ครบ 3/3**
- ของเดิม report เก่าเขียนว่า "เหลือ S3 ×1 (ไม่แก้)" → **รอบนี้แก้แล้ว**
- ตรวจเพิ่ม: float-on-money ที่ route อื่น (ไม่มี), placeholder/TODO/bare-except (ไม่มีของค้าง — เป็น Protocol/abstract/cleanup ที่ถูกต้อง)

---

## 🐞 บั๊กที่แก้

### [F1] S2 — ระบบรัน TA **ผิดตัว**: pip `pandas_ta` บัง vendored stub → ละเมิด determinism
- **อาการ:** มี TA สองชุด — `src/pandas_ta/` (stub เขียนเองเพื่อ deterministic) และ pip `pandas-ta 0.4.71b0`.
  เพราะ `site-packages` มาก่อน `src` ใน `sys.path` → `import pandas_ta` วิ่งไปที่ตัว pip **ไม่ใช่ stub**.
- **หลักฐาน:** golden values ในเทสต์ (`rsi=58.599038`, `atr=542.048026`, `adx=11.395545`) **ตรงกับ stub เป๊ะทุกหลัก** →
  เจตนาเดิมคือใช้ stub แต่ของจริงรันตัว pip. เทสต์ผ่านได้เพราะ tolerance หลวม (±1.0/±10.0) กลบ drift ไว้.
- **ผลกระทบ:** indicator เปลี่ยนค่าตามเวอร์ชัน lib ที่บังเอิญติดตั้ง = ผิด mandate **Predictability / Backtest-Fidelity**
  (หัวใจของระบบ — "ผลต้อง repeatable").
- **การแก้ (collision-proof):**
  - rename `src/pandas_ta/` → `src/vendor_ta/` (ชื่อชนกันไม่ได้อีก ไม่ว่าใครจะ pip install อะไร)
  - `ta.py`: `import pandas_ta` → `import vendor_ta`
  - ถอด `pandas-ta` ออกจาก `requirements.txt` + `pyproject.toml` (ไม่พึ่ง lib ภายนอกที่เวอร์ชันลอย)
  - อัปเดต mypy `exclude`/override, pytest `filterwarnings`, และ whitelist ใน `test_layer_rules.py` (`pandas_ta`→`vendor_ta`)
- **ผลลัพธ์:** indicator ได้ค่าเดียวกันทุก environment เพราะ math อยู่ในซอร์สเราเอง 100%.
  รันใต้ `filterwarnings=error` แล้วไม่มี pandas-3.0 warning-as-error.

### [F2] gate-fail — coverage จริง 89.55% **ตก gate 90%** (report เก่าอ้าง 91.17%)
- **root cause:** เป็นอาการต่อเนื่องจาก F1 — `src/pandas_ta/__init__.py` (122 บรรทัด) ถูกนับใน `--cov=src`
  แต่ไม่เคยถูกรัน (โดน pip บัง) → โชว์ **0%** แล้วฉุดค่ารวมตก.
- **การแก้:** หลังแก้ F1 ตัว `vendor_ta` ถูกใช้จริง → coverage = **99%** ของไฟล์นั้น.
- **ผลลัพธ์:** total coverage **89.55% → 91.17%** (ตรงกับ report เดิมเป๊ะ = ยืนยันว่า stub คือ implementation ที่ตั้งใจ).

### [F3] S3 — `status()` แปลงเงิน Decimal→`float` ตอน serialize JSON → noise ระดับ < 1 สตางค์ (รอบเก่า "ไม่แก้")
- **อาการเดิม:** `screen.cash=49152.77083380553` vs `ledger.cash=49152.7708338055288750` (ต่างหลักที่ 14+).
- **การแก้ (ไม่พังของเดิม):** ที่ `runtime_status.py` —
  - field ตัวเลข (`equity`/`cash`/`pnl_today`/`realized_today`) → `float(quantize_price(...))` = **quantize เป็นสตางค์ (2dp)**
    → จอแสดงเลขสะอาด ไม่มีหาง float (ตัด noise S3 ทิ้ง)
  - เพิ่ม **string twin เต็มความละเอียด** ทุกตัว: `cash_str`, `pnl_today_str`, `realized_today_str` (ของเดิมมี `equity_str` แล้ว)
    = ช่อง reconcile ที่ **เป๊ะ 100% เทียบ ledger**
  - dashboard JS / เทสต์ที่อ่าน `float(s["cash"])` **ไม่ต้องแก้** (field ตัวเลขยังอยู่)
- **regression ใหม่:** `test_money_serialization_is_exact_and_satang_quantized` — settle trade ให้ cash เป็นค่าไม่กลม
  (`2234.443543211`) แล้วพิสูจน์ `cash_str` ตรง ledger เป๊ะ + numeric quantize เป็นสตางค์.
- **honesty guard เดิม** อัปเกรดให้ตรวจช่อง `_str` (exact) เพิ่ม → "ห้ามโกหก" แข็งขึ้นจริง.

---

## 🔬 ผลรันจริงหลังแก้
```
ruff check src tests        → All checks passed!
mypy --strict src/          → no issues found in 132 source files
pytest (full + coverage)    → 824 passed, 1 skipped · coverage 91.17% (gate 90)
boot-from-zero              → GET / =200 · GET /api/status =200 · สร้าง data/state.db เอง
  · equity=cash=1000 · execution_engine=paper (default ปลอดภัย)
  · cash_str/pnl_today_str/realized_today_str โผล่ใน response จริง (S3 fix live)
soak 25s                    → RSS 60.6→60.7MB (โต 0.1MB = bounded ไม่ leak) · 0 traceback
kill -TERM + reboot         → state_restored=True · equity_str/cash_str กลับครบ
```

## 📁 ไฟล์ที่แก้
- `src/pandas_ta/` → `src/vendor_ta/` (rename ทั้งโฟลเดอร์)
- `src/domain/analytics/ta.py` (import vendor_ta)
- `src/orchestration/runtime_status.py` (quantize เงิน + เพิ่ม `_str` twins)
- `requirements.txt`, `pyproject.toml` (ถอด pandas-ta, อัปเดต mypy/warnings)
- `tests/architecture/test_layer_rules.py` (whitelist vendor_ta)
- `tests/architecture/test_honesty_guard.py` (ตรวจ `_str` + regression S3 ใหม่)

---

## ⚠️ ข้อจำกัดที่ยังคงต้องบอกตามจริง (ไม่เปลี่ยนจากเดิม)
- **paper-only ยังล็อกไว้โดยตั้งใจ** — `execution_engine` default = `paper`; ห้ามถอด.
  การเปิดเงินจริงต้องผ่าน **paper track record ต่อเนื่อง + edge validation (walk-forward/OOS)** ก่อนเสมอ.
- soak ที่รันรอบนี้ = 25 วินาที (พิสูจน์ RSS นิ่ง + reboot) — ระดับหลายชั่วโมง/หลายวัน wall-clock ยังไม่ได้รัน.
- price feed จริงของ Bitkub ในแซนด์บ็อกซ์นี้ถูกบล็อก (network allowlist ไม่มี `api.bitkub.com`) → คืน 403,
  ระบบ degrade graceful (retry + log) ไม่ crash. บนเครื่องจริงที่เน็ตเปิด price feed จะทำงานปกติ.
- **ห้ามสรุปว่า "ไม่มีบั๊ก / ปลอดภัย 100% / พร้อมเทรดเงินจริง"** — เขียนได้แค่ที่ verify จริง.

## ▶️ วิธีรัน
```bash
# Linux / macOS
bash start.sh                      # ตั้ง venv + ติดตั้ง deps + เปิด http://localhost:8000

# Windows
start.bat        (หรือ)  start.ps1

# รันเทสต์เอง
pip install -e ".[dev]" && pytest
```
