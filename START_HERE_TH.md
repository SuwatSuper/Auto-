# 🏰 KINGDOM PRIME — เริ่มใช้งาน (ฉบับย่อ)

ระบบรวมครบทุกเฟสแล้ว: Hotfix ราคา (P0) + Risk เต็มระบบ (P1) + Bitkub REST แบบมีประตูนิรภัย (P2) + อินดิเคเตอร์/กลยุทธ์ (P3) + Reliability/Deploy (P4) + CEO มีชีวิต
สถานะตรวจรับ: เทสต์ผ่าน 428 รายการ, บูตจริงทุก endpoint ตอบ 200, ไม่มี traceback

## 1) ติดตั้ง (ต้องเป็น Python 3.12)
```
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -e ".[dev]"
```

## 2) ตั้งค่า .env
คัดลอก `.env.example` → `.env` แล้วกรอกค่าเอง
- คีย์ Bitkub (ถ้าจะใช้): สร้างคู่ Key+Secret ใหม่จากหน้า API Management แล้วพิมพ์ใส่ `BITKUB_API_KEY` / `BITKUB_API_SECRET` เอง **ห้ามแชร์ไฟล์นี้ / ห้ามวางคีย์ในแชทเด็ดขาด**
- ค่าเริ่มต้นทั้งหมดปลอดภัย: `EXECUTION_ENGINE=paper` (ไม่ยิงออเดอร์จริง)

## 3) ทดสอบสัญญาณราคา (ครั้งแรกแนะนำ)
```
python scripts/ws_probe.py      # ต้องเห็นราคา THB_BTC วิ่งและจบด้วย exit 0
```

## 4) รันระบบ
```
python scripts/run.py           # แล้วเปิด http://127.0.0.1:8000/
pytest -q                       # เช็คสุขภาพระบบเมื่อไรก็ได้ ต้องเขียวหมด
```
บนแดชบอร์ดจะเห็นราคา BTC จริง, agent ทั้ง 10, และ CEO เดินสั่งงาน/บ่นเป็นภาษาไทย (ปุ่ม 👑 ซ่อน/โชว์, ปุ่ม 🔊 เปิดเสียงพูด — เสียงไทยขึ้นกับเบราว์เซอร์ของเครื่อง)

## 5) โหมดเงินจริง (LIVE) — อ่านก่อนเปิด
ค่าปกติคือ paper เสมอ การยิงออเดอร์จริงจะเกิดได้ต่อเมื่อครบ **ทั้ง 4 ประตู**:
1. `.env`: `EXECUTION_ENGINE=live`
2. `.env`: `LIVE_TRADING_CONFIRM=I_ACCEPT_REAL_MONEY_RISK`
3. ไม่มีไฟล์ `data/KILL_SWITCH` (สร้างไฟล์นี้เมื่อไร = หยุดออเดอร์ใหม่ทันที: `type nul > data\KILL_SWITCH` บน Windows หรือ `touch data/KILL_SWITCH`)
4. Circuit breaker ต้องไม่ถูกทริป (ทริปแล้วต้องรีเซ็ตด้วยมือเท่านั้น)
แนะนำ: รัน paper ต่อเนื่องหลายวันจน PnL/พฤติกรรมนิ่งก่อนค่อยเปิด live ด้วยทุนน้อยที่สุด

## 6) Deploy 24/7 บน Linux
ดู `deploy/DEPLOY.md` (systemd `deploy/kingdom_prime.service` + logrotate) — หมายเหตุ: โฟลเดอร์ wheels เดิมเป็นของ Windows, บน Linux ติดตั้งจาก PyPI ตามคู่มือ

## 7) ส่งงานกลับให้ตรวจ
```
python scripts/make_zip.py <ชื่อรอบ>   # ได้ kingdom_prime_<ชื่อรอบ>.zip (ไม่รวม .env อัตโนมัติ)
```
