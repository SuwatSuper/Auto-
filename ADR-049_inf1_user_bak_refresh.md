# ADR-049 — `.user.bak` ต้อง refresh จาก master จริงทุกรอบ (แทน ADR-039 #2)

สถานะ : ACCEPTED — 20.06.2026 (supersedes ADR-039 ข้อ #2 เท่านั้น; ข้ออื่นของ ADR-039 คงเดิม)
บริบท : รอบ re-audit 2026-06-20 พบช่องข้อมูลหายที่ ADR-039 #2 สร้างขึ้นเอง (finding INF1).

> ระดับ: 🔴 ร้ายแรง (master จริงของผู้ใช้หายถาวรเงียบ), golden-safe ในการแก้

---

## ปัญหา (INF1) — ADR-039 #2 เป็นต้นเหตุข้อมูลหาย

ADR-039 #2 กำหนด: *"ห้ามทับ `.user.bak` ที่มีอยู่แล้ว (ถือว่าเก็บของจริงครบแล้ว)"* —
`write_master_file` จึงสำรอง **ครั้งเดียว** (`if not os.path.exists(backup)`). ลำดับที่ทำข้อมูลหาย:

1. รอบ golden #1: live = master จริง `v1` → สำรอง `.user.bak = v1`, เขียน stub. **ถูก kill ก่อน atexit**
   → คงเหลือ: live = stub, `.user.bak = v1`.
2. ผู้ใช้เห็นไฟล์เป็น stub จึง **ใส่ master ใหม่ `v2`** (ตั้งใจแทนของเดิม) → live = `v2` (จริง).
3. รอบ golden #2: เดิมเห็น `.user.bak` มีอยู่ → **ไม่สำรอง `v2`** → เขียน stub →
   atexit `_restore_master_file`: live = stub → `os.replace(.user.bak=v1, live)` →
   **live = `v1`. `v2` หายถาวร** (`.user.bak` ถูก consume ทิ้งด้วย).

reproduce จริงด้วย `os.kill(pid, 9)` (และ `os._exit`) — ดู `test_bughunt_hardening.py` case 2b.

## การตัดสินใจ

สัญญาที่ถูกต้องของ `.user.bak` คือ **"สิ่งที่อยู่ใน live ก่อนเครื่องมือ golden แตะ"** — ดังนั้นต้อง
**refresh ทุกรอบเมื่อ live เป็น master จริง** (ไม่ใช่ stub):

```python
if not _file_has_stub_marker(path):          # live = จริง → สำรอง (atomic temp+replace)
    shutil.copy2(path, backup + ".tmp"); os.replace(backup + ".tmp", backup)
```

คงกติกาสำคัญของ ADR-039 เดิมทุกข้อ:
- **live = stub → ไม่สำรอง** (กัน stub กลืน `.user.bak` ที่เก็บ master จริง) — case 1 ยังกู้ได้.
- `_restore_master_file` คืนเฉพาะเมื่อ live = stub/หาย, เขียน atomic.

## trade-off ที่ยอมรับ

| สถานการณ์ | เดิม (ADR-039 #2) | ใหม่ (ADR-049) |
|-----------|-------------------|-----------------|
| kill → ใส่ master **ใหม่** → รัน | ❌ ของใหม่หาย (INF1) | ✅ ของใหม่รอด |
| ผู้ใช้ใส่ master **subset** โดยเผลอ | ของเต็มเดิมถูกคืน | subset (ของที่ผู้ใช้พิมพ์ล่าสุด) ถูกเก็บ |

เลือกใหม่เพราะ: live = เจตนาปัจจุบันของผู้ใช้; backup เป็น "safety net ของรอบนี้" ไม่ใช่ version history.
แนะนำเสริม (อนาคต): เตือนเมื่อ master ใหม่เล็กกว่า backup เดิมมาก (ให้ผู้ใช้ยืนยัน).

## เทส/พิสูจน์

- `test_bughunt_hardening.py` case 2 (refresh) + case 2b (kill→edit→run→restore: `co_NEW` รอด) — **ผ่าน 26/26**.
- golden-safe: แตะเฉพาะ sidecar `.user.bak` (ไม่อยู่ใน golden path) — fixture `269ddaed…` + digest `f271e98b…` ไม่ขยับ.
