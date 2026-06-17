# ADR-039 — กัน `write_master_file` ทำลาย master จริงของผู้ใช้ + backup ถาวร

สถานะ : ACCEPTED — 17.06.2026
บริบท : รอบ bug-hunt v9.3.1 (hardening). `golden_snapshot.write_master_file()` ถูกเรียก
        "ในโฟลเดอร์โปรเจกต์" โดยเครื่องมือ golden/verify จำนวนมาก (golden_master, verify_golden,
        verify_parallel, verify_report_det, build_consolidated_report, e2e_test, profile_baseline)
        ซึ่งเขียน stub ทดสอบทับ `master_companies.json`. เดิมมี atexit คืนค่า แต่ยังมีรู data-loss

> ระดับ: 🔴 ร้ายแรง (ทำข้อมูลผู้เสียภาษี/ทะเบียนบริษัทจริงหายถาวร), golden-safe ในการแก้

---

## Root cause (สืบจาก source จริง)

```python
if os.path.exists(path):
    backup = path + ".user.bak"
    shutil.copy2(path, backup)          # ← ทับ backup แบบไม่มีเงื่อนไข
    atexit.register(_restore_master_file, path, backup)
...
with open(path, "w") ...: json.dump(stub)   # ← เขียนไม่ atomic
```

2 ทางพัง:
1. **atexit ไม่ทำงานบน SIGKILL / OOM / ไฟดับ / `os._exit`** → หลังรันที่ถูก kill:
   live = stub, `.user.bak` = master จริง (ยังกู้ได้)
2. **`copy2` ทับ backup ไม่มีเงื่อนไข** → รัน "รอบที่สอง" ที่ถูก kill อีก: `copy2(stub → .user.bak)`
   → `.user.bak` กลายเป็น stub → **master จริงหายจากทั้ง live และ backup = กู้ไม่ได้ถาวร**

(reproduce ยืนยันแล้ว: หลัง 2 รอบที่ถูก kill ทั้ง 2 ไฟล์เป็น stub)

> บรรเทาบางส่วนที่มีอยู่เดิม: stub มี `_golden_stub:true` → `_is_real_master` ไม่ใช้ stub เป็น
> master จริง (ไม่ทำผลตรวจผิดเงียบ) — แต่ "ความพร้อมใช้ของข้อมูล" ยังหายอยู่

## Decision (การแก้ — จุดเดียว, golden-safe)

1. **ห้าม copy2 ทับ `.user.bak` ที่มีอยู่แล้ว** และ **ห้ามสำรองเมื่อ live เป็น stub อยู่แล้ว**
   (เพิ่ม `_file_has_stub_marker(path)`) → master จริงใน `.user.bak` รอดข้ามรอบ kill ซ้ำ ๆ
2. เขียน stub แบบ **atomic** (`_atomic_write_json`: temp + `fsync` + `os.replace`) →
   kill กลาง write ไม่ทำ master ครึ่ง/ว่าง
3. `_restore_master_file` คืน **เฉพาะเมื่อ live เป็น stub หรือหายไป** → ไม่เผลอทับ master จริง
   ด้วย backup เก่า
4. `.gitignore` : เพิ่ม `master_companies.json.user.bak` / `.tmp`
5. ตรึงด้วย `test_bughunt_hardening.py` (4 สถานการณ์: kill-replay, ไม่ทับ backup, วงจรปกติ, atomic)

## Golden impact — **ไม่ขยับ (golden-safe)**
ระหว่างรัน ไฟล์ยังเป็น golden stub เนื้อหาเดิมเป๊ะ ; และ golden hash คำนวณจาก `MASTER` dict
(ส่งตรงเข้า `run_audit_core`) ไม่ใช่จากไฟล์. พิสูจน์: fixture oracle = `269ddaed…` ก่อน/หลังแก้,
`test_stub_marker` + `test_reset_completeness` ผ่าน

## Migration risk — ต่ำ
เปลี่ยนเฉพาะ I/O ของไฟล์ master (off-audit-path). พฤติกรรม sandbox เดิม (เขียน stub → คืนเมื่อจบ)
คงไว้ ; เพิ่มเฉพาะความปลอดภัยตอน kill/รอบซ้ำ
