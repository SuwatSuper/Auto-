# 🏰 KINGDOM PRIME — เริ่มใช้งาน (ฉบับสมบูรณ์)

ระบบเทรด paper-first + เกตนิรภัยเงินจริง + เรียนรู้จากผลจริง + เก็บ track record ครบ.
**สถานะ (หลัง Phase 10 + Release Gate):** `pytest 823 ผ่าน / 1 skip` · `ruff` ✅ ·
`mypy --strict` ✅ (132 ไฟล์) · cov 91.2% · boot จริง `GET /`=200 · soak 60s ไม่ crash/leak ·
เลขจอ = ledger = `trades_*.csv` reconcile เป๊ะ (ระดับสตางค์). เป้า **กำไรสุทธิ 5%/วัน (หลังหัก
ค่าธรรมเนียม)** — เป็น "เป้าที่ไล่ตาม" ไม่ใช่การการันตี (ดูหัวข้อ "ความจริง" ท้ายไฟล์).

**Phase 10 (ความฉลาดเพิ่ม — ใต้รั้วความเสี่ยงเดิม):** order-book microstructure (READ-ONLY),
ML win-probability (numpy ล้วน + walk-forward/OOS), swarm meta-learner ตาม regime,
multi-timeframe, adaptive regime weights, news-sentiment sizing, Kelly ใต้ hard-cap.
ดูรายละเอียด `PHASE10_AGENT_POWER_REPORT_TH.md` และผลตรวจ `RELEASE_AUDIT_REPORT_TH.md`.

---

## 1) ติดตั้ง (Python 3.12)
**คำสั่งเดียว:** ดับเบิลคลิก/รัน `start.bat` (Windows) · `./start.sh` (mac/Linux) · `start.ps1` (PowerShell)
— สคริปต์จะสร้าง venv, ติดตั้ง deps, สร้างโฟลเดอร์ `data/`, แล้วรันเซิร์ฟเวอร์ให้

ทำเองทีละขั้นก็ได้:
```
python -m venv .venv
.venv\Scripts\activate          # Windows  (mac/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
```

## 2) ตั้งค่า `.env`
คัดลอก `.env.example` → `.env` แล้วกรอกเอง (ค่าปริยายปลอดภัยหมด: paper, ทุน 1,000฿):
- `DASHBOARD_API_KEY` — token คุมแดชบอร์ด (endpoint อันตรายต้องใช้ **แม้บนเครื่องตัวเอง**)
- `DASHBOARD_PASSWORD` — รหัส operator (ใช้ปุ่ม Login บนจอแลกเป็น token); จำเป็นถ้า bind 0.0.0.0
- `INITIAL_CAPITAL=1000` · `TARGET_DAILY_PROFIT_PCT=5`
- `BITKUB_API_KEY/SECRET` — เฉพาะเมื่อจะต่อบัญชีจริง (สร้างเองจาก Bitkub API Management — **ห้ามแชร์**)

## 3) รัน + เปิดแดชบอร์ด
```
PYTHONPATH=src python scripts/run.py     # เปิด http://127.0.0.1:8000/
pytest -q                                # เช็คสุขภาพระบบเมื่อไรก็ได้ — ต้องเขียวหมด
```

## 4) ใช้แต่ละปุ่มบนแดชบอร์ด (แท็บ Command Room ⚙️)
| อยากทำอะไร | ทำยังไง |
|---|---|
| **ตั้งทุนเริ่มต้น** | กรอก "ทุนตั้งต้น" → Apply (เซฟลง .env) |
| **ตั้งเป้ากำไร/วัน** | การ์ด 🎯 — กรอก "เป้า %/วัน" → Apply · แถบความคืบหน้าโชว์ % จริง vs เป้า; ถึงเป้า = ล็อกกำไร หยุดเปิดไม้ใหม่ |
| **เปิด/ปิดกลยุทธ์ + จูน param** | การ์ด 🎛️ — กดปิด = หยุดส่งสัญญาณ; แก้ param (min_gap/RSI/channel) → บันทึก |
| **KILL SWITCH** | การ์ด 🔴 — เปิด = บล็อก live ถาวร (ข้าม restart) จนกดปิด |
| **สลับ paper ⇄ live** | การ์ด 🚦 — พิมพ์ confirm token แล้วกด LIVE (ต้องผ่าน 4 ประตู) |
| **ตั้งความเสี่ยง** | การ์ด ⚖️ — risk%/stop/TP/loss-cap/cap-ต่อไม้ → Apply |
| **สั่งซื้อ/ขายเอง** | การ์ด 📋 — BUY/SELL/ปิด position |
| **ดูใครสั่งอะไร** | การ์ด 🧾 Control audit (รีเฟรชอัตโนมัติ) |
| **หยุดฉุกเฉิน** | ปุ่ม Emergency Stop / Trip breaker |

## 5) โหมดเงินจริง (LIVE) — อ่าน `docs/LIVE_TRADING_RUNBOOK.md` ก่อนเสมอ
ต้องครบ **4 ประตู**: `EXECUTION_ENGINE=live` + confirm token + ไม่มี `data/KILL_SWITCH` + breaker ปิด.
เพดานต่อไม้ถูกล็อกในโค้ดที่ **1,000฿** (config ทะลุไม่ได้ — เกินถูก reject + log CRITICAL).
แนะนำ: รัน paper หลายวันให้ `data/daily_summary.csv` พิสูจน์ edge ก่อนค่อยเปิด live ด้วยทุนน้อยสุด.

## 6) ข้อมูล / track record
- `data/trades_YYYYMMDD.csv` — ทุกไม้: fee_paid, pnl_gross, pnl_net, strategy_id, regime, win_prob
  (บันทึกอัตโนมัติทุกครั้งที่ปิดไม้ — เป็นทั้งหลักฐานเลขจอและข้อมูลฝึกโมเดล ML)
- `data/daily_summary.csv` — รายวัน: pnl_net, fees_total, win_rate, pct_return_net, target_reached
- `data/state.db` — สถานะ (SQLite WAL) ปิด-เปิดใหม่ไม่หาย
- **ตรวจ edge ของโมเดล ML (out-of-sample):** `PYTHONPATH=src python scripts/validate_winprob.py`
  — อ่าน `data/trades_*.csv` จริงถ้ามี (≥30 ไม้) แล้วรายงาน walk-forward expectancy เทียบ rule;
  ยังไม่มีไม้จริงจะโชว์เดโม synthetic ที่ติดป้ายชัดว่าไม่ใช่ผลเทรดจริง

## 7) Deploy 24/7 (Linux)
ดู `deploy/DEPLOY.md` (systemd + logrotate).

---

## ⚠️ ความจริง (เจ้าของสั่ง: ห้ามโกหก)
ระบบ **ไล่ตามเป้า 5%/วันและรายงานเลขจริงสุทธิหลังค่าธรรมเนียมเสมอ** (ทุกตัวเลขมาจาก ledger จริง —
มี honesty guard บังคับเป็นโค้ด) แต่ **"ไล่เป้า" ≠ "การันตี 5% ทุกวัน"** ผลจริงตลาดเป็นผู้กำหนด.
**ห้ามเชื่อว่า "พร้อมเทรดเงินจริง" จนกว่า paper track record + edge validation (walk-forward/OOS) จะพิสูจน์.**
