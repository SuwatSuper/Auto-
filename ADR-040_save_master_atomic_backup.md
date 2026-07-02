# ADR-040 — `save_master` เขียนแบบ atomic + `.bak` ห้ามถูก save ที่ "หด" ทับ

สถานะ : ACCEPTED — 17.06.2026
บริบท : รอบ bug-hunt v9.3.1 (hardening). `master.save_master()` เป็นทางบันทึก master จริงของ
        ผู้ใช้ (เรียกจาก `input_master_data` โหมดโต้ตอบ + `เพิ่ม_master.py`). พบ 2 ความเสี่ยง
        data-integrity บนไฟล์ทะเบียนบริษัทจริง

> ระดับ: 🟡 กลาง × 2 (M1 = เขียนไม่ atomic, M2 = .bak generation เดียวถูกทับ), golden-safe

---

## Root cause (สืบจาก source จริง)

```python
with open(CFG['MASTER_FILE'], 'w') as f:   # ← truncate ทันที แล้วค่อย write
    f.write(payload)
```

- **M1 (non-atomic):** `open('w')` truncate ไฟล์เป็น 0 ก่อน แล้ว `write`. kill/ไฟดับ/disk-full
  ระหว่างนั้น → master เหลือ 0 ไบต์/JSON ครึ่ง ๆ. จากนั้น `load_master` เข้า
  `except Exception: return None` → **ระบบตรวจต่อโดย "ไม่มี master" เงียบ ๆ** (กฎที่พึ่ง master ตกหมด)
- **M2 (.bak generation เดียว):** `.bak` ชื่อคงที่ ถูกทับทุก save ที่เนื้อหาต่าง. save ที่ "หด"
  (บริษัทน้อยลง) จะทับ `.bak` ที่สมบูรณ์กว่าทิ้ง → บริษัทที่หลุดหายจากทั้งไฟล์และ backup
  (reproduce: `[ก,ข]` → save `[ก]` → `.bak=[ก,ข]` ; → save `{}` → `.bak=[ก]` เดิมหาย ข)

## Decision (การแก้ — surgical, golden-safe)

1. **Atomic write:** temp + `flush` + `os.fsync` + `os.replace` → kill กลาง write ไม่ทำ
   master ครึ่ง/ว่าง (ของเดิมอยู่ครบจนกว่า replace สำเร็จ)
2. **`.bak` ครบที่สุดเสมอ:** สำรอง live → `.bak` เฉพาะเมื่อ live "ครบ ≥" `.bak` ที่มีอยู่
   (`_json_dict_len(current) >= _json_dict_len(bak)`) → save ที่หด **ไม่ทำ backup เสียข้อมูล**
   แต่ save ที่ครบขึ้นยัง refresh `.bak` ได้ (รักษาเจตนาเดิมของ `test_fix_round2`)
3. ตรึงด้วย `test_bughunt_hardening.py` (Master-M1/M2) + `test_fix_round2` ผ่านครบ

## Golden impact — **ไม่ขยับ (golden-safe)**
`save_master` เป็นทางโต้ตอบ (off-audit-path) ; golden ใช้ `MASTER` dict ไม่ผ่านไฟล์นี้.
fixture oracle = `269ddaed…` ก่อน/หลังแก้ ; `test_fix_round2` (double-save + wipe) ผ่าน

## Migration risk — ต่ำ
ผลลัพธ์ไฟล์เนื้อหาเดิมเป๊ะ (atomic แค่เปลี่ยน "วิธีเขียน") ; กติกา `.bak` ใหม่เป็น superset
ของพฤติกรรมเดิม (ยอม refresh เมื่อครบขึ้น, กันเฉพาะตอนหด)
