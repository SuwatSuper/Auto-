# 👑 KINGDOM PRIME — Live-Data, Paper-Execution Trading System (Production Migration)

ระบบเทรด **ราคา LIVE จาก Bitkub** + **execution ยังเป็น paper** (ปลอดภัย — ยังไม่ส่งออเดอร์จริง)
สถาปัตยกรรม 3 ชั้น + CEO Agent (audit trail). Production Migration: ลบ mock data, ลบ simulator, เหลือ live data path เท่านั้น.

---

## 🚀 วิธีรัน (3 ขั้นตอน)

### Windows
1. **แตกไฟล์ zip** ไปไว้ที่ไหนก็ได้ (เช่น `C:\kingdom-prime`)
2. **ดับเบิลคลิก `start.bat`** (หรือคลิกขวา `start.ps1` → Run with PowerShell)
3. รอสักครู่ → **เบราว์เซอร์เด้งเปิด** `http://localhost:8000/` อัตโนมัติ ✅

ครั้งแรกจะติดตั้ง environment อัตโนมัติ (ใช้ wheels ที่แนบมา — ไม่มีเน็ตก็ติดตั้งได้ ถ้าใช้ Python 3.12 x64 — ตรงกับเครื่องคุณ;
Python เวอร์ชันอื่นจะ fallback ไปโหลดออนไลน์ให้เอง) — โปรเจกต์นี้ pin ที่ Python ≥ 3.12

### เปิดจาก VS Code
1. แตกไฟล์ → **File → Open Folder** เลือกโฟลเดอร์นี้
2. เปิด Terminal ใน VS Code (`` Ctrl+` ``) แล้วพิมพ์:
   ```
   .\start.bat        (Windows)
   ./start.sh         (macOS / Linux)
   ```
3. แดชบอร์ดเด้งขึ้นมาเอง

### รันมือ (ทุก OS)
```bash
python -m venv venv
venv/bin/pip install -r requirements.txt        # Windows: venv\Scripts\pip
PYTHONPATH=src venv/bin/python -m uvicorn main:app --port 8000
# เปิด http://localhost:8000/
```

---

## 🖥 หน้าจอ

| URL | คืออะไร |
|---|---|
| `http://localhost:8000/` | **Kingdom Prime** dashboard (หลัก) |
| `http://localhost:8000/classic` | Anime Ops Center (แดชบอร์ดเดิม) |
| `/api/status` | สถานะระบบ (JSON) |
| `/healthz`, `/metrics` | liveness + Prometheus metrics |

## 🤖 เอเจนต์ทั้ง 7 (ของจริง 1:1 ไม่มีตัวหลอก — กฎ H5)

| Chibi บนจอ | คลาสจริง | หน้าที่ |
|---|---|---|
| Market Analyst | `EntryExitAgent` | สัญญาณ EMA-cross จากราคาจริง |
| News Intelligence | `NewsSentimentAgent` | สกอร์ sentiment (รอ feed ข่าวใน V4) |
| Risk Management | `RiskAgent` | เช็คลิมิตออเดอร์/drawdown |
| Probability Lab | `ProbabilityAgent` | ความน่าจะเป็นจาก RSI |
| Historical Research | `HistoricalResearchAgent` | สถิติราคาย้อนหลัง rolling 1000 จุด |
| Paper Execution | `SimulationAgent` | backtest จำลองรวมค่าธรรมเนียม+slippage |
| Supreme Commander | `SupremeAgent` | รวมสัญญาณ ตัดสินใจขั้นสุดท้าย |

ตัวเลข Win Rate บนจอ = ผลจาก rolling paper backtest จริง (ไม่ใช่ตัวเลขแต่ง)
Equity เริ่มที่ `INITIAL_CAPITAL` และจะขยับเมื่อ pipeline เทรดจำลองเต็มรูปแบบ (เฟส P9–P10 ตามคู่มือ V3) ถูกสร้างต่อ

## 🔐 API Key

`.env` มี `DASHBOARD_API_KEY` — ทุกคำสั่งควบคุม (เปลี่ยนโหมด, start/stop agent, EMERGENCY STOP)
ต้องส่ง header `X-API-Key` ตรงกับคีย์นี้ (แดชบอร์ดใส่ให้อัตโนมัติ)
**⚠ คีย์นี้เคยถูกส่งในแชท — ถ้าเป็นคีย์ที่ใช้ที่อื่นด้วย (เช่น exchange) ควร rotate ทันที**
เปลี่ยนคีย์: แก้ใน `.env` แล้วรีสตาร์ต

## 🧪 ตรวจสุขภาพระบบ

```bash
PYTHONPATH=src python -m pytest -q      # ทุกเทสต้องเขียว
python -m ruff check src tests scripts
python -m mypy --config-file pyproject.toml
```

## 📁 โครงสร้าง

```
src/domain/          Layer 1 — กฎธุรกิจล้วน (Decimal, ไม่มี framework)
src/orchestration/   Layer 2 — runtime + 7 agents + supervisors
src/infrastructure/  Layer 3 — FastAPI, WS, SQLite, gateways, dashboard
tests/               202+ เทส (domain / orchestration / web / architecture)
docs/                ARCHITECTURE, RUNBOOK, EVENTS, ADRs, SECURITY
CLAUDE_CODE_*.md     คู่มือเฟสถัดไป (P7–P16) สำหรับรันใน Claude Code
```

## ⏭ ทำต่อ (ตามคู่มือ)

เปิดโฟลเดอร์นี้ใน **Claude Code** → วาง `CLAUDE_CODE_MASTER.md` ทั้งไฟล์ → ระบบจะไล่สร้าง
P7–P16 (governance 3/5% band, multi-symbol, optimizer, meetings ฯลฯ) ต่อจากฐานที่ผสานแล้วนี้


## เฟส 4 — ระบบเทรดจำลอง งบ 1,000 บาท (PAPER ONLY)

- **Paper Trader**: เปิดไม้ long พร้อม stop-loss + take-profit อัตโนมัติทุกไม้ (ถอดไม่ได้) คิดค่าธรรมเนียม 0.25% + slippage ทั้งขาเข้า-ออก
- **Account Guardian (Agent บัญชีคุมเงิน)**: ถือเงินสดแต่ผู้เดียว — กันพอร์ตไม่ให้ต่ำกว่า 700฿ (Survival Floor 70%), หยุดเทรดอัตโนมัติเมื่อขาดทุนวันละเกิน 50฿ (5%)
- **บันทึกอัตโนมัติ**: บัญชี + ไม้ค้าง ลง `data/state.db` — ปิดโปรแกรมแล้วเปิดใหม่ เงินไม่รีเซ็ต
- **Watchdog**: เอเจนต์ตัวไหนตาย ระบบบันทึกสาเหตุ + ปลุกขึ้นมาใหม่เอง แดชบอร์ดโชว์ 💥 CRASHED / 🧊 FROZEN ตามจริง
- **ไม่มีทางเทรดจริง**: มีเทสสแกนซอร์สโค้ดทั้งระบบ ถ้าใครเติมโค้ดส่งคำสั่งซื้อจริง เทสจะแดงทันที

ปรับงบ/ความเสี่ยงได้ใน `.env`: `INITIAL_CAPITAL`, `RISK_PER_TRADE_PCT`, `STOP_PCT`, `TAKE_PROFIT_PCT`
