# 🔒 PRIVACY NOTICE — แพ็กนี้มีข้อมูลจริงของลูกค้า (PII)

> **สรุปบรรทัดเดียว: แพ็ก release หลักนี้มี tax_id / ที่อยู่ / ชื่อบริษัทจริง — ห้ามแชร์ให้คนนอก. ถ้าต้องแจกจ่าย ให้ทำแพ็ก shareable ก่อน.**

## ไฟล์ที่มี PII

| ไฟล์ | มีอะไร |
|---|---|
| `baseline.json` | สแนปช็อต golden = ผลตรวจ 1,153 บิลจริง (ชื่อบริษัท · เลขผู้เสียภาษี · ที่อยู่ · ชื่อสินค้า) |
| `tests/real_cases/*.xls` | ใบกำกับภาษีจริง 3 ไฟล์ (KRR/STC/TKH_69_05) ใช้เป็น test case |
| `canary_baseline.json` | สแนปช็อต parse ที่ derive จากข้อมูลจริง |

ไฟล์เหล่านี้ **จำเป็น** ต่อการทำงานบนเครื่องเจ้าของ (regression ข้อมูลจริง `run_ci.sh /mnt/project` ต้องใช้ `baseline.json`) — จึงคงไว้ในแพ็กหลัก. เป็นข้อมูลของเจ้าของระบบเอง (คืนสู่เจ้าของ) ไม่ได้รั่วออกนอก.

## กฎการใช้งาน

1. **เก็บแพ็กหลักเป็นส่วนตัว** — อย่าอัปโหลดขึ้นที่สาธารณะ / ส่งให้บุคคลภายนอก
2. ถ้า **ต้องแจกจ่าย** (เดโม/ส่งมอบให้ทีมภายนอก/เก็บเป็น public) → ทำแพ็กปลอด PII ก่อน:

```bash
python3 sanitize_for_sharing.py puopuy_v9_3_4_OFFLINE_COMPLETE_f05358aa_5year.zip
# → *_SHAREABLE.zip : redact PII ใน baseline.json + ตัด real_cases/canary
```

แพ็ก `_SHAREABLE.zip`:
- ✅ ยัง verify ได้ด้วย **fixture golden `ad0c9dad`** (`bash run_ci.sh` — ไม่ต้องมี corpus)
- ⚠  regression ข้อมูลจริง `[7]/[8]` ใช้ไม่ได้ (ไม่มี baseline จริง/corpus) — ปกติ เพราะคนนอกไม่มี corpus อยู่แล้ว

## ตรวจสถานะ PII ได้ทุกเมื่อ

```bash
python3 doctor.py        # ข้อ [9] จะเตือนถ้าแพ็กมีข้อมูลจริง
```

## Bundle สำรอง (backup_kit) — PRIVATE เสมอ

`puopuy_PRIVATE_BACKUP_*.zip` (จาก `backup_kit.py`) **ตั้งใจ**ให้มี corpus จริงครบ เพื่อกู้ระบบได้ 100% —
จึงเป็นไฟล์ส่วนตัวระดับเดียวกับ corpus เอง: เก็บ ≥2 ที่ของเจ้าของเท่านั้น ห้ามอัปโหลด/ส่งต่อ.
การแจกจ่ายระบบให้คนนอกยังใช้เส้นทางเดียวคือ `sanitize_for_sharing.py` กับ release. *[ADR-163]*

*[ADR-159]*
