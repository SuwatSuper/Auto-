# 🖥️ สร้างโปรแกรม .EXE (แดชบอร์ดคลิกทีเดียว) — คู่มือ

> ปุ้มปุ้ย Dashboard = หน้าต่างโปรแกรมเดียว: เลือกโฟลเดอร์ไฟล์บิล → กด **เริ่มตรวจ** →
> เห็นผล (กี่บริษัท/ตรง/รีเช็ค) → กดเปิด Excel หรือโฟลเดอร์รายงานได้เลย.
> **ไม่ต้องเปิด VS Code / เทอร์มินัล / Python** หลัง build เสร็จ.

---

## ⭐ ง่ายสุด (แนะนำ) — ไม่ต้อง build .exe เลย

1. ลง **Python 3.12** ครั้งเดียว (ติ๊ก ☑ **Add python.exe to PATH**) — https://www.python.org/downloads/
2. **ดับเบิลคลิก `START.bat`**
   - ครั้งแรกมันลงไลบรารีให้อัตโนมัติ (รอสักครู่)
   - แล้ว **หน้าต่างโปรแกรมเปิดเลย** → เลือกโฟลเดอร์ → กดเริ่มตรวจ
3. ครั้งต่อไป: ดับเบิลคลิก `START.bat` → เปิดทันที

> วิธีนี้ **ไม่ต้องสร้าง .exe** — เร็ว ง่าย ไม่ต้องรอ build. เหมาะถ้าใช้เครื่องตัวเอง.
> อยากได้ไฟล์ .exe เดี่ยว ๆ ไว้แจกเครื่องที่**ไม่มี Python** → ทำตามหัวข้อล่าง.

---

## 🧱 ทางเลือก: ทำเป็นไฟล์ .EXE เดี่ยว (ไว้แจกเครื่องที่ไม่มี Python)

---

## ⚠️ อ่านก่อน (สำคัญ)
- **.exe ต้อง build บน Windows เท่านั้น** — สร้างจากเครื่อง Linux/Mac ให้เป็น .exe ไม่ได้
  (PyInstaller ไม่ใช่ตัว cross-compile). build บนเครื่อง Windows ที่จะเอาไปใช้ → ชัวร์สุด.
- build **ครั้งเดียว** ก็พอ. หลังจากนั้นแจกไฟล์ `PukpuiDashboard.exe` ให้ใครก็ได้ ดับเบิลคลิกใช้ได้เลย
  (เครื่องปลายทาง **ไม่ต้องลง Python**).

---

## วิธีทำ (3 ขั้น บน Windows)

### 1) ลง Python 3.12
โหลดจาก https://www.python.org/downloads/ → ตอนติดตั้ง **ติ๊ก ☑ "Add python.exe to PATH"**

### 2) ดับเบิลคลิก `build.bat`
มันจะทำให้อัตโนมัติ: ลงไลบรารี (ตรึงเวอร์ชันตรง golden) → ลง PyInstaller → สร้าง .exe
(ครั้งแรกใช้เวลา ~2–5 นาที + ต้องต่อเน็ต)

### 3) ได้ไฟล์ที่ `dist\PukpuiDashboard.exe`
ดับเบิลคลิกใช้ได้เลย 🎉

> ถ้าไม่อยากใช้ build.bat สั่งเองก็ได้:
> ```
> pip install -r requirements.txt -c constraints.txt pyinstaller
> pyinstaller --noconfirm pukpui_dashboard.spec
> ```

---

## วิธีใช้โปรแกรม
1. กด **📁 เลือกโฟลเดอร์ไฟล์บิล** → ชี้ไปโฟลเดอร์ที่มี .xls/.xlsx
2. (ถ้ามี) กด **🗂 master** เลือก `master_companies.json` เพื่อเทียบชื่อ/เลขภาษี
3. กด **✅ เริ่มตรวจ** → รอแถบความคืบหน้า
4. เห็นผลสรุป → กด **📂 เปิด Excel** / **📁 เปิดโฟลเดอร์รายงาน** (มีทั้ง Excel + สรุปลูกค้า .txt)

---

## แก้ปัญหาที่พบบ่อย
| อาการ | แก้ |
|---|---|
| Antivirus เตือน/ลบ .exe | เป็น false-positive ของ PyInstaller — กด allow/exclude ; spec ปิด UPX แล้ว (ลดโอกาสโดน) |
| เปิดแล้วเด้งปิดทันที | build ใหม่โดยแก้ `console=False` → `console=True` ใน `pukpui_dashboard.spec` เพื่ออ่าน error |
| `ModuleNotFoundError` ตอนรัน .exe | เพิ่มชื่อโมดูลที่ขาดใน `hiddenimports` ของ `pukpui_dashboard.spec` แล้ว build ใหม่ |
| pythainlp/ฟอนต์ไทยเพี้ยน | ลง `pip install pythainlp==5.0.5` ให้ครบก่อน build (build.bat ทำให้แล้ว) |
| .exe ใหญ่ (200–400MB) | ปกติ (รวม pandas/numpy/pythainlp). อยากเล็ก/เร็วขึ้น → เปลี่ยนเป็นโหมด onedir (โฟลเดอร์แทนไฟล์เดียว) |

---

## ผลตรวจตรงกับ golden ไหม?
ตรงครับ — แดชบอร์ดเรียก **pipeline ตรวจตัวเดิม** (agents.orchestrator.run_pipeline) และตั้ง
`PYTHONHASHSEED=0` อัตโนมัติตอนเปิด → ผลตรวจเหมือนรันผ่านเทอร์มินัล. แดชบอร์ดเป็นแค่ "หน้าควบคุม"
(advisory UI) ไม่แตะ engine → audit golden `35b2f7c8` ไม่ขยับ.
