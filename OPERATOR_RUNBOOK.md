# 🛠️ OPERATOR RUNBOOK — คู่มือดูแลระบบ ปุ้มปุ้ย (ปิด bus-factor)

> รวมคำสั่งสำคัญไว้ที่เดียว — เปิดไฟล์นี้ไฟล์เดียวก็ดูแลระบบต่อได้ (เผื่อเปลี่ยนคนดูแล / ลืม).
> รายละเอียดเชิงลึกอยู่ใน `GOLDEN.md`, `MAINTENANCE.md`, `INVARIANTS/DECISIONS.md` (ADR ledger).

## 0) ENV บังคับ (ทุกคำสั่งที่แตะ golden)

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1
```

## 1) เช็คสุขภาพระบบ (ทำก่อนเสมอ)

```bash
python3 doctor.py            # quick: python/deps/env/hooks/fixture/drift/master/PII
python3 doctor.py --full     # + invariant tripwire (golden fixture + pin)
```

## 2) ตรวจว่า golden ยังถูก (2 ชั้น)

```bash
# ชั้น fixture (ถาวร ไม่ผูก corpus) — ตัวพิสูจน์ code จริง:
python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json   # ต้อง ad0c9dad

# ชั้น corpus จริง (ผูก /mnt/project):
python3 verify_corpus_manifest.py /mnt/project    # MATCH = code ต้องถูก / DRIFT = data เปลี่ยน
bash run_ci.sh /mnt/project                        # regression เต็ม (ต้อง f05358aa)
```

## 3) เมื่อ golden ข้อมูลจริงไม่ตรง — data drift หรือ code bug?

```bash
python3 verify_corpus_manifest.py /mnt/project
```
- **MATCH** → corpus เดิม แต่ golden เพี้ยน = **CODE BUG** (มีคนแก้ logic) → สืบด้วย `git diff` / ADR
- **DRIFT** → corpus เปลี่ยน = ปกติ → ถ้าตั้งใจ ไป (4) rebaseline ; ถ้าไม่ → restore ไฟล์

## 4) Rebaseline (หลังเพิ่มบิลใหม่ / แก้ที่กระทบ golden — ต้องตั้งใจเท่านั้น)

```bash
python3 golden_master.py . baseline.json /mnt/project        # คำนวณ golden ใหม่
python3 verify_corpus_manifest.py /mnt/project --write        # อัป manifest
python3 test_golden_single_source.py                          # บอกพื้นผิว doc ที่ต้อง sync (แก้ตามที่มันบอก)
# บันทึก ADR ใหม่ (append-only) ใน INVARIANTS/DECISIONS.md + อัป GOLDEN.md table
bash run_ci.sh /mnt/project                                   # ยืนยันเขียวก่อนถือว่าเสร็จ
```

## 5) เพิ่มคำผิด (typo) ใหม่

```
1. ยืนยันว่าผิดจริง (ค้นเน็ตคำผิดตรงๆ ต้อง 0 ร้านใช้ + ไม่อยู่ CONSTRUCTION_DICT)
2. เพิ่ม literal pattern ใน config_base.THAI_TYPO_PATTERNS (ระวังไม่ทับรูปที่ถูก → FP=0)
3. rebaseline ตาม (4) + ADR ใหม่
4. test_typo_decisions_lock.py + test_adr123_borderline_clear.py ต้องเขียว
```

## 6) แจกจ่ายแพ็กให้คนนอก (ต้องปลอด PII)

```bash
python3 sanitize_for_sharing.py <release.zip>    # → *_SHAREABLE.zip (ดู PRIVACY_NOTICE.md)
```

## 7) สร้าง release ใหม่ (ทางเดียวที่อนุญาต)

```bash
python3 make_release.py . /mnt/project <out.zip>   # build+extract+verify (PII self-check + golden)
```

## 8) งานค้าง (ปลดล็อกความสามารถเต็ม)

- **เติม `master_companies.json`** จากทะเบียน ภ.พ.20 (4 ฟิลด์: ชื่อ/tax_id/สาขา/ที่อยู่) →
  ปลดล็อก ~24 กฎตัวตน (ชื่อบริษัทผิด/เลขภาษีผิด/สาขาผิด/ไม่มีในทะเบียน) ที่ตอนนี้ "หลับ" อยู่
- curate typo dict เมื่อมีคำการค้าใหม่ (ปกติ ทำเรื่อยๆ)

## 9) สำรอง & ซ้อมกู้คืน (ทำทันที + ปีละครั้ง) [ADR-163]

```bash
# สร้าง bundle สำรอง "ไฟล์เดียวมีทุกอย่างที่ต้องรอด" (release+corpus+master+ledger+คู่มือกู้):
python3 backup_kit.py build puopuy_v9_3_4_OFFLINE_COMPLETE_f05358aa_5year.zip /mnt/project
# → puopuy_PRIVATE_BACKUP_<วันที่>.zip  ⚠ PRIVATE (มีบิลจริง) — copy ไป ≥2 ที่ (นอกเครื่อง 1)

python3 backup_kit.py verify puopuy_PRIVATE_BACKUP_<วันที่>.zip   # ตรวจ sha256 ครบทุกชิ้น
```

**ซ้อมกู้คืน/เช็คเครื่องใหม่ (30 วินาที ก่อน commit เครื่อง):**
```bash
python3 machine_check.py    # Python3.12? linux x86_64? pip? wheels? ดิสก์? → PASS/วิธีแก้
```
ขั้นกู้เต็ม: เปิด `RESTORE_TH.md` ใน bundle (7 ขั้น พร้อม hash ที่ต้องได้: fixture `ad0c9dad…` → real `f05358aa…`)

## ⛔ ห้ามเด็ดขาด

- `pythainlp`: ไม่บังคับ — **ถ้ามีต้อง 5.0.5 เป๊ะเท่านั้น** (พิสูจน์ 2026-07-02: มี 5.0.5 → golden f05358aa เป๊ะเดิม, ADR-164) · เวอร์ชันอื่นห้ามจนกว่าจะพิสูจน์ (gate จะ FAIL ให้เองที่ major)
- ห้ามใช้ `unzip` กับไฟล์ไทย (ใช้ Python `zipfile`) — Linux unzip ทำชื่อไฟล์ไทยเพี้ยน
- ห้ามแก้ ADR เก่าใน `DECISIONS.md` (append-only — เพิ่มล่างสุดเท่านั้น)
- ห้ามแก้ parse-core โดยไม่ได้รับอนุญาต + rebaseline (FREEZE)
- ต้อง `-c constraints.txt` ทุก pip install (กัน numpy drift)

*[ADR-159]*
