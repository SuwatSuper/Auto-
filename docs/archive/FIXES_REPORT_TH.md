# รายงานการแก้บั๊ก + ตรวจปุ่มหลอก — Kingdom Prime

วันที่: 2026-06-13 · ทุกการแก้ผ่านการทดสอบ 3 รอบ (pytest + ruff + mypy + ทดสอบ DOM จริงด้วย JSDOM + รันเซิร์ฟเวอร์จริง)

---

## สรุปผลทดสอบ (ก่อนส่งงาน)

| รายการ | ผล |
|--------|-----|
| pytest (ชุดทดสอบ Python) | ✅ 515 passed, 1 skipped |
| ruff (lint) | ✅ All checks passed |
| mypy (type check, strict) | ✅ no issues in 98 files |
| JSDOM dashboard harness (ทดสอบทุกปุ่ม/ทุกหน้าจริงในเบราว์เซอร์จำลอง) | ✅ 37/37 |
| รันเซิร์ฟเวอร์จริง + ยิงทุก endpoint (GET+POST) | ✅ ทั้งหมด |

---

## บั๊กรุนแรง (Critical / High)

### 1. หน้า Analytics แสดง `NaN` ทุกค่า
- **อาการ:** Sharpe / Sortino / Profit Factor แสดง `NaN`, กราฟว่างเปล่า
- **สาเหตุ:** `EQUITY_CURVE` เป็น array ว่าง (ตามนโยบาย "ห้ามข้อมูลปลอม") แต่โค้ดยังนำไปหาร → `0/0 = NaN`
- **แก้:** สร้าง **equity curve จากข้อมูลจริง** (เก็บค่า equity จาก `/api/status` แบบเรียลไทม์), ป้องกันการหารศูนย์ทุกจุด, ถ้าข้อมูลยังไม่พอแสดง `—` พร้อมข้อความ "กำลังเก็บข้อมูล" แทน `NaN`

### 2. ตัวเลขความเสี่ยงผิด 100 เท่า (อันตรายในระบบเทรด)
- **อาการ:** Backend ส่ง `daily_loss_pct`/`drawdown_pct` เป็น **เปอร์เซ็นต์อยู่แล้ว** (เช่น 2.0 = 2%) แต่ frontend คูณ 100 ซ้ำ → ขาดทุน 2% แสดงเป็น **200%**, เข็มเกจตีสุดสเกลตลอด
- **จุดที่ผิด:** `renderRisk()` (วิดเจ็ตหน้า Dashboard) และ `renderRiskPage()` (หน้า Risk)
- **แก้:** เลิกคูณ 100 ซ้ำ + แก้สูตรเข็มเกจให้อิงกับ limit ที่ตั้งไว้

---

## บั๊กระดับกลาง (Medium) + ปุ่มหลอก

### 3. กราฟวงกลม Portfolio Allocation (หน้า Portfolio) ไม่เคยถูกวาด
- **อาการ:** กล่อง `pf-donut` ว่างเปล่า เพราะฟังก์ชัน `initAllocDonut` ถูกประกาศไว้แต่ **ไม่เคยถูกเรียก**
- **แก้:** เขียน `renderAllocation()` วาดกราฟจาก **ข้อมูลจริง** (เงินสด + position จริง) ทั้งหน้า Dashboard และ Portfolio พร้อม legend

### 4. กราฟวงกลมหน้า Dashboard ใช้ข้อมูลปลอม
- **อาการ:** `ALLOC_DATA` hardcode (BTC 45% / ETH 25% / BNB 15% / Others 15%) — ผิดนโยบาย "ห้ามข้อมูลปลอม"
- **แก้:** ลบ `ALLOC_DATA` ทิ้ง ใช้สัดส่วนจากพอร์ตจริงแทน (ถ้าไม่มีข้อมูลแสดง "ยังไม่มีข้อมูลพอร์ต")

### 5. หน้า Risk: Exposure และ VaR เป็นค่าปลอม
- **อาการ:** Net Exposure คำนวณจาก `POSITIONS` (array ว่างเสมอ) → แสดง 0% ตลอด; VaR ใช้ค่าคงที่ปลอม `equity × 1.65%`
- **แก้:** คำนวณ exposure จาก position จริง (`market_value / equity`), VaR คำนวณแบบ historical 95% จาก equity curve จริง (ถ้าข้อมูลไม่พอแสดง `—`)

### 6. ปุ่ม Header "ค้นหา / ข้อความ" เป็นปุ่มหลอก (ปุ่มหลอกการทำงาน)
- **อาการ:** ปุ่ม Search และ Messages บนแถบบน กดแล้วเด้ง toast ข่าวเหมือนกันหมด **ไม่ได้ทำงานตามชื่อปุ่ม**
- **แก้:** ลบปุ่มหลอกทั้งสองออก คงไว้แต่ปุ่มกระดิ่ง "การแจ้งเตือน" ที่ทำงานจริง

### 7. ตัวเลขแจ้งเตือน (badge) เป็นเลขปลอม "3" ตายตัว
- **อาการ:** ป้ายแดงบนกระดิ่งแจ้งเตือน hardcode เป็น "3" ตลอด
- **แก้:** ทำระบบแจ้งเตือนจริง — กดกระดิ่งเปิด dropdown ที่ดึงเหตุการณ์จริงจากระบบ (EMERGENCY STOP / treasury halt / circuit breaker / agent ค้าง-พัง / ข้อความตก / sentiment ข่าว / สถานะบัญชี / ฟีดราคา) และ badge แสดง **จำนวนจริง** (ซ่อนเมื่อเป็น 0)

### 8. หน้า /classic: ปุ่มสลับโหมดยิง endpoint ผิด + ปุ่ม SIM หลอก
- **อาการ:** ปุ่ม mode ยิงไป `/api/switch_mode?mode=` ซึ่ง**ไม่มีอยู่จริง** → 404; ปุ่ม "SIM" ใช้โหมด simulator ที่ถูกถอดออกแล้ว
- **แก้:** เปลี่ยนเป็น endpoint จริง `/api/mode/{mode}` และลบปุ่ม SIM (ปุ่มหลอก) ออก

---

## บั๊กระดับต่ำ (Low)

### 9. CI พังเพราะ lint (ruff 3 errors)
- import ที่ไม่ได้ใช้ใน `test_credentials.py` (`os`), `test_manual_and_alerts.py` (`Decimal`) และ import ไม่เรียงใน `test_rest_ticker.py` → แก้ทั้งหมด

### 10. เมนู CEO ใช้แท็กไม่ตรงกับเมนูอื่น
- เดิมใช้ `<li>` ขณะเมนูอื่นใช้ `<a class="nav-item">` ทำให้สไตล์เพี้ยน → แก้ให้เหมือนกัน + ใส่ไอคอน

### 11. คีย์แปลภาษา CEO หาย
- `nav_ceo`, `pg_ceo_title`, `pg_ceo_sub`, `ceo_*` ไม่มีในตาราง i18n → เพิ่มครบทั้ง EN/TH

### 12. แกน Y กราฟ Equity หน่วยผิด
- เดิม fix หน่วยเป็น "M" (ล้าน) ทั้งที่ทุนจริงหลักพัน → เปลี่ยนเป็นเลขจริงตาม locale

---

## ผลตรวจปุ่มทุกหน้า (Button Audit)

| หน้า | ปุ่ม | สถานะ |
|------|------|--------|
| Header | กระดิ่งแจ้งเตือน | ✅ ทำงานจริง (ทำใหม่) |
| Header | Search, Messages | 🗑️ ปุ่มหลอก → ลบออก |
| Sidebar | LIVE, EMERGENCY STOP, RESET | ✅ ทำงานจริง |
| Dashboard | Start All / Stop All | ✅ ทำงานจริง |
| Trading | BUY/SELL toggle, ส่งคำสั่ง (ot-submit) | ✅ ทำงานจริง (POST /api/order) |
| Risk | EMERGENCY STOP / RESET | ✅ ทำงานจริง |
| Agents | Start All / Stop All | ✅ ทำงานจริง |
| Settings/Command Room | Connect, Login, Apply risk, PAPER/LIVE, breaker TRIP/RESET, BUY/SELL/Close/Close-all, ทดสอบแจ้งเตือน | ✅ ทำงานจริงทั้งหมด (ยิง endpoint จริง) |
| Settings | EN/TH, LIVE, toggle Notifications/Motion, สไลเดอร์ความเสี่ยง | ✅ ทำงานจริง |
| /classic | mode, SIM | 🔧 แก้ endpoint + ลบ SIM |

> หมายเหตุ: คำสั่งซื้อ/ขายจะตอบ "ยังไม่มีราคา" เมื่อยังไม่มีฟีดราคาจริง (เช่น รันในแซนด์บ็อกซ์ที่ปิดเน็ต) ซึ่งเป็นพฤติกรรมที่ถูกต้อง ไม่ใช่บั๊ก — เมื่อต่อ Bitkub จริงจะส่งคำสั่งได้
