# ADR-044 — Rebaseline golden 106 ไฟล์: `d6b23d12` → `bb042554` (TNT_69_03 float-tail IV)

สถานะ : ACCEPTED — 18.06.2026
บริบท : ตรวจสุขภาพระบบเต็ม (Principal-Architect audit) พบว่ารัน `regression_full.py` /
`verify_golden.py` / CI gate [7]+[8] บน corpus จริง 106 ไฟล์ **แดง** ทั้งที่โค้ด v9.3.4 ถูกต้อง
สาเหตุ = `baseline.json._sha256` ค้างเป็นพฤติกรรม **ก่อน ADR-041** (float decimal-tail IV misread)
ส่วนโค้ดแก้แล้ว → baseline ไม่ถูก regenerate → drift เงียบ.

---

## รากของปัญหา (สืบจาก source จริง ไม่เดา)

ADR-041 (iv float decimal-tail) + ADR-024 (iv money misread) ระบุตัวเองว่า **"golden-neutral"**
แต่พิสูจน์ความ neutral เฉพาะบน:
- `tests/real_cases` = KRR / STC / TKH (hash `95852c68`) — **ไม่มีไฟล์ TNT**
- `tests/fixtures` (hash `269ddaed`)

corpus จริง 106 ไฟล์ที่ `/mnt/project` มี `TNT_69_03.xls` ซึ่ง **เป็นไฟล์เดียวที่ trigger บั๊ก float-tail**
จึงไม่เคยถูกตรวจ neutrality → คำว่า "golden-neutral" จริง ๆ แล้ว **ผิดบน corpus เต็ม** (ผลเปลี่ยนถูกต้องขึ้น
แต่ค่า hash ขยับ). ตรงกับ pattern ที่บันทึกไว้: certify บน fixture เล็ก ไม่ใช่ corpus จริง.

### หลักฐานระดับ cell (TNT_69_03.xls ชีต "6", vendor 0105568190762, วันที่ 06/03/2026)

| ชั้น | ค่า | ที่มา |
|---|---|---|
| raw cell `[5,20]` (xlrd, TEXT) | `"03210"` | เลขใบกำกับจริง |
| money cell `[19,22]` (pandas float) | `87282.04000000001` | ยอดรวม (float noise) |
| money cell `[18,22]` (pandas float) | `5710.040000000001` | VAT (float noise) |
| **โค้ดเก่า (d6b23d12)** อ่าน iv = | `04000000001` | คว้า "หางทศนิยม" ของ `87282.04000000001` มาเป็นเลขเอกสาร |
| **โค้ด v9.3.4 (ADR-041)** อ่าน iv = | `03210` | ✅ ถูกต้อง — ปฏิเสธ candidate หางทศนิยม |

---

## Before/After forensic diff (corpus เต็ม 106 ไฟล์ / 834 บิล)

โครงสร้าง snapshot ทุก key เทียบ baseline เดิม — **เปลี่ยนเฉพาะที่เกี่ยวกับ iv ของ TNT_69_03 เท่านั้น**:

```
all_bills        : 834 == 834  · ต่าง 2 แถว (เฉพาะ iv_number/issues — ยอดเงินไม่ขยับ)
  row(TNT ชีต6)  : iv_number 04000000001 → 03210 · iv_number_raw เช่นกัน · IV002 false-flag หาย
  row(TNT 11/03) : issues list อัปเดตตาม crosscheck ที่ถูกต้อง
iv_seq           : 28 → 29  (+ "09/03 เลข 3320 → 11/03 เลข 3072 ลดลง" — ของจริง ถูกต้อง)
iv_date          : 3 → 2    (− "03179 ↔ 04000000001 ถอยหลัง" — false positive จาก misparse หาย)
summary          : 2 == 2   · bill issue-list ของ TNT สะท้อนผลถูกต้อง
dup_items 1·file_names 106·filename_issues 9·typos 42·n_bills 834·n_files 106 : ✅ ตรงเป๊ะ
```

> **ยอดเงิน subtotal/VAT/total ของทั้ง 834 บิล: ไม่มีค่าใดเปลี่ยนแม้แต่บาทเดียว.** blast radius = การ
> parse เลขใบกำกับ 1 ใบ + ผลลัพธ์ปลายน้ำ (crosscheck/issue list) เท่านั้น.

---

## Decision

Re-baseline golden corpus จริง: `d6b23d12…` → **`bb042554…`** (เต็ม:
`bb04255422d64b21e3c00db235912054a62999b3ed1ebc2d4644888b9f3633a4`).

เหตุผล: ค่าใหม่ = ผลตรวจที่ **ถูกต้องกว่า** (ตรง raw cell). การ revert ADR-041 = นำบั๊กกลับ → ไม่ทำ.
นี่คือ "documented rebaseline ตามวินัย golden": มี before/after forensic diff + ADR + อัปเดตทุกพื้นผิว.

ทางเลือกที่ปฏิเสธ:
- **คง baseline เดิม (d6b23d12)** → gate แดงค้างถาวร, ระบบฟ้องเลขขยะ `04000000001` เป็นเลขเอกสาร → ตัดทิ้ง
- **revert float-tail guard** → นำ false positive กลับมาทั้ง corpus → ตัดทิ้ง

---

## วิธีสร้างซ้ำ (reproducible)

```bash
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 golden_master.py . baseline.json /mnt/project
# → bb04255422d64b21e3c00db235912054a62999b3ed1ebc2d4644888b9f3633a4  (golden_master ×2 ตรงกัน — deterministic)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . /mnt/project
# → engine == agent == baseline ✅
```

## Migration risk : ต่ำมาก
- ไม่แตะ source/logic ใด ๆ (เปลี่ยนเฉพาะ `baseline.json` + พื้นผิวเอกสารที่ประกาศค่า hash)
- ค่าใหม่ deterministic (รัน golden_master 2 ครั้งได้ค่าเดียวกัน) และ engine==agent
- พื้นผิว operational sync แล้ว (`test_golden_single_source.py` ✅) ; `d6b23d12` ขึ้นทะเบียนเป็น retired

## พื้นผิวที่อัปเดต (จาก `d6b23d12` → `bb042554`)
`baseline.json` · `GOLDEN.md` (current + retired table) · `INVARIANTS/DECISIONS.md` (banner + ledger)
· `MAINTENANCE.md` · `.github/workflows/ci.yml` · `QUICKSTART_VSCODE_TH.md` · `_SESSION_HANDOFF.md`
· `Makefile` · `run_ci.sh` · `.vscode/tasks.json` · `.vscode/launch.json`
· `test_golden_single_source.py` (RETIRED_PREFIXES += d6b23d12)

> เอกสารประวัติ (ADR-018/019/021/023/024, CHANGELOG, HANDOFF, GOLDEN_EVIDENCE, parser_p0a docstring)
> ที่อ้าง `d6b23d12` **คงไว้** — ถูกต้องตามเวลาที่เขียน (หลักฐานอดีต ห้ามเขียนทับ).

## Backup
`baseline.d6b23d12.pre-rebaseline.json` = snapshot golden เดิม (เก็บเป็นหลักฐานก่อน rebaseline).
