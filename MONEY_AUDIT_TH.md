# MONEY_AUDIT_TH — ตรวจบั๊กเส้นทางเงิน (รอบ LIVE)

ตอบคำถาม "ค้นหาบั๊กก่อนส่งหรือยัง": รอบนี้ทำ **adversarial bug-hunt เจาะจงโค้ดใหม่ +
เส้นทางเงิน LIVE (ที่เพิ่งเปิด)** ด้วย agent 2 ตัว + ตรวจเอง + repro จริง แล้วแก้ทุกตัว

## ✅ ที่ตรวจแล้ว "ถูกต้อง" (ยืนยันด้วยการรัน)
- เพดานต่อไม้บังคับจริง, hard-cap reject (NaN/Inf/เกิน → ปฏิเสธ ไม่ trim), treasury veto ก่อนจ่ายจริง,
  protective-exit cap ตาม balance จริง, ค่าธรรมเนียมสองขา 0.25%, **ไม่มี float บนเส้นทางเงิน**,
  auto-key ปลอดภัย (loopback เท่านั้น, non-loopback ปิดตาย), rate-limit กัน remote, ไม่มี header spoof,
  buffer bounded, ไม่มีคำสั่งฝาก/ถอน

## 🔧 บั๊กที่เจอและแก้ (รอบนี้)

| ID | ระดับ | อาการ | แก้ | ไฟล์ |
|----|------|-------|-----|------|
| L-01 | **S1** | HARD_CAP (฿1,000) ถูก**ข้าม**เมื่อ cap=0 (เช่น .env=live แต่ state.db หาย) → ออเดอร์ live อาจเกินเพดาน | clamp HARD_CAP **เสมอ** ไม่ว่า operator cap จะเท่าไหร่ | runtime_live.py |
| L-02 | **S1** | SELL กลับสัญญาณใช้ qty paper ที่เกิน balance จริง → Bitkub reject → **ไม้จริงค้างเปิด** | cap ask ตาม BTC จริงใน wallet | runtime_live.py |
| L-03 | **S1** | paper mirror คำนวณ qty/ราคาเข้าใหม่ ไม่ใช้ fill จริง → holdings/PnL เพี้ยนทุกไม้ | mirror **qty/rate/THB จริง** จาก exchange ack (มี fallback ถ้า ack ไม่ส่ง) | execution_agent.py, paper_trader.py |
| L-04 | **S1** | ตอน LIVE: equity/cash/% โชว์ฐาน paper ฿1,000 ไม่ใช่ wallet จริง → % เพี้ยน ~50 เท่า | seed ทุนจาก **THB จริง** ตอน arm + ป้ายกำกับสลับ (live=เงินจริง / paper=ลม) | runtime_risk.py, mini.html |
| L-05 | S2 | `/api/trades`, `/api/prices/history` **ไม่มี auth** → leak สถานะบัญชีให้ remote | ใส่ check_api_key (loopback เชื่อใจ, remote ต้องมี key) | public.py |
| L-06 | S2 | `_recent_trades_loop` **ตายเงียบ**ถ้าเจอ JSON ไม่ใช่ dict → ตารางไม้ค้างถาวร | isinstance guard + except กว้าง ไม่ให้ loop ตาย | runtime.py |
| L-07 | S3 | เขียน .env ไม่สำเร็จ → เงียบ | log warning | runtime_risk.py |
| L-08 | S3 | innerHTML กับ ev.qty/ev.reason (ยังไม่ exploit ได้) | escape (defense-in-depth) | mini.html |

regression test ใหม่ทุกตัว (fail-ก่อน/pass-หลัง): hard-cap-เสมอ, SELL-cap, fill-mirror, seed-capital,
endpoint-auth, loop-survives-bad-frame

## ผลรวม (รันจริง)
- ruff ✅ · mypy --strict ✅ · pytest **858 passed / 1 skipped / coverage 91.36%**
- e2e uvicorn จริง: auto-key ฝังหน้า, ปุ่มเดียว arm live (all gates open), ไม่มี key → 401

## ความจริงที่ verify ไม่ได้ (พูดตามตรง)
- ต่อ Bitkub จริง (network ถูกบล็อกใน sandbox) — เทสต์ live ใช้ mock gateway/ฉีด balance
- ยอด wallet จริงตอน live จะ seed เมื่อ "เชื่อมบัญชีแล้ว + มี THB ใน wallet" — ตอนนี้ wallet คุณ ฿0
  ต้องเติมเงินก่อน เลขถึงจะขยับเป็นเงินจริง
