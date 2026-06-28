# สรุปการแก้บั๊ก "กฎที่เปิดใช้งาน" + 5-year hardening — ปุ้มปุ้ย v9.3.4 (2026-06-22)

> เจ้าของอนุมัติ: **"แก้เลยครับผม แก้ทั้งหมด และส่งระบบที่สมบูรณ์"**
> โหมด: แก้ surgical → reproduce ก่อน-หลังทุกจุด → พิสูจน์ golden ที่ run ได้ → 1 ADR ต่อจุด → เทสกันถอย
> ผู้ทำ: Claude Code (remote/cloud) · Python 3.11 (ทางการ 3.12)

---

## 0) สรุปผู้บริหาร

แก้ครบ **2 รอบ** ตามที่ตรวจเจอ:
- **รอบ infra (M-2/M-3/M-4)** — ADR-061/062/063 (golden-neutral แท้, แก้+ส่งไปแล้วก่อนหน้า)
- **รอบกฎที่เปิดใช้งาน (15 จุด)** — ADR-064..076 (รอบนี้)

**พิสูจน์เท่าที่ cloud env ทำได้ — ผ่านหมด:**
- fixture golden `b5c415bb` **ไม่ขยับ** (engine==agent==baseline)
- `check_invariants.py` 4/4 · `test_golden_single_source.py` (doc-sync) PASS
- `run_ci.sh` (ไม่มี data) **exit 0** + เทสใหม่ `[3x14e]` + `[3x14f]` ผ่าน
- ทุกการแก้ reproduce ก่อน-หลัง + ของจริงไม่ถอย (เช่น CP All ยังจับ, สนญ.จริงยังฟ้อง, ซ้ำจริงยังฟ้อง)

**⚠️ เหลือขั้นเดียว (เครื่องเจ้าของเท่านั้น):** 2 ใน 15 การแก้ (**ITM004 + ITM016**) ลบ false-positive จริงใน corpus 148 ไฟล์ → golden `ae84d3f0` **จะเปลี่ยน (ตั้งใจ — ผลตรวจถูกขึ้น)** → ต้อง **rebaseline** บน Python 3.12 + `/mnt/project` (cloud นี้ไม่มี corpus + เป็น 3.11 จึงทำให้ไม่ได้). อีก 13 จุด golden-neutral (0 occurrence ใน baseline.json).

---

## 1) รายการแก้ทั้งหมด (ADR-064..076)

| ADR | รหัส | ระดับ | แก้อะไร | ผล corpus 148 |
|---|---|---|---|---|
| 064 | **DT003 (M-1)** | ⏰ 5-ปี | `yr>2030` → `yr>audit_today().year+1` — กันบิลปกติทุกใบโดนฟ้อง "digit-swap ตัวเอง" ตั้งแต่ ค.ศ.2031 | neutral |
| 065 | **CMP003** | 🟡 | brand blacklist → match ขอบคำละติน (CP ไม่ match CPF, Tops ไม่ match Laptops) | neutral |
| 066 | **BR001/004** | 🟡 | "สำนัก" → "สำนักงานใหญ่"/"สนญ" เต็มคำ (สาขาที่มีคำ "สำนัก" ไม่ถูกตีเป็นสนญ.) | neutral |
| 067 | **DOC001** | 🟡 | +guard วัน 1–31 (ชีตเลข "32"/"2026" ไม่ถูกตีเป็น "วัน") | neutral |
| 068 | **ADDR002** | 🟡 | ต่างแค่เว้นวรรค (พระราม4 vs พระราม 4) ไม่ฟ้องสะกดผิด | neutral |
| 069 | **VAT006/007 (C-1)** | 🔴 | กัน `_D()=None` (เงิน inf/NaN) ก่อนคำนวณ + `math.isfinite` ใน `_tor_scan_*` — เดิม TypeError หลุด → ข้ามกฎ VAT (CRITICAL) เงียบ | neutral |
| 070 | **ITM016** | 🟡 | dedup key +qty +amount — รายการแยกจริง (qty ต่าง) ไม่ฟ้อง "รายการซ้ำ" | **เปลี่ยน → rebaseline** |
| 071 | **ADDR005** | ⚪ | ตัด "โทร/แฟกซ์" ก่อนหาไปรษณีย์ (เบอร์โทรท้ายไม่ถูกตีเป็น zip) | neutral |
| 072 | **DOC003** | ⚪ | บิลไม่มีวันที่ (None==None) ไม่ฟ้องซ้ำ | neutral |
| 073 | **DT004** | 🟡 | YYMM ต้อง ≥5 หลัก (PO2501 = counter ไม่ใช่ ปี25/ด.01) | neutral |
| 074 | **เลขภาษีไทย (C-2)** | 🔴 | `clean_tax_id` แปลงเลขไทย ๐-๙ → อารบิก (TAX003 ไม่ฟ้อง "อันตราย" ผิด + TAX005/008 anti-fraud ไม่พลาด) | neutral |
| 075 | **ITM004** | ⚪ | ตัด 0-9 จาก lookaround ("5นิ้ว" ไม่ใช่ "อังกฤษ+ไทยติดกัน") | **เปลี่ยน → rebaseline** |
| 076 | **ITM010** | ⚪ | "วาว"/ประกายวาว ไม่ถูกเดาเป็น "วาล์ว" (ยังจับ บอลวาว/เกจวาว) | neutral |

**ITM009 (กฎ dormant):** เปิดอยู่แต่ `product_master.json` ไม่มีในแพ็ก → คืน `[]` เสมอ. **ไม่ใช่บั๊กโค้ด** (กฎทำงานเมื่อมีไฟล์ data) → ไม่แตะ. เจ้าของเลือก: เติม `product_master.json` ให้ทำงาน หรือคงไว้ dormant.

ไฟล์ที่แก้: `rules_engine_rules_a.py` · `rules_engine_rules_c.py` · `validators.py` · `parser_p2.py` · `config_base.py` · `puopuy_core.py` (+ เทส 2 ไฟล์, ADR, run_ci.sh).

---

## 2) ขั้นตอน rebaseline (เครื่องเจ้าของ — Python 3.12 + /mnt/project)

เพราะ **ITM004 (ADR-075)** + **ITM016 (ADR-070)** ลบ false-positive จริง → `ae84d3f0` จะเปลี่ยนโดยตั้งใจ:

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1
pip install -r requirements.txt -c constraints.txt          # Python 3.12

# 1) ดูว่าเปลี่ยนเพราะ ITM004/ITM016 เท่านั้น (ไม่ใช่ regression อื่น)
python3 regression_full.py . /mnt/project                   # คาด: MISMATCH ae84d3f0 (ปกติ)
#    → ตรวจ diff: flag ที่หายต้องเป็น ITM004 (เลขติดไทย) + ITM016 (รายการแยก qty ต่าง) เท่านั้น

# 2) เขียน golden ใหม่ (ตั้งใจ rebaseline)
python3 golden_master.py . /mnt/project baseline.json --write   # (ดู MAINTENANCE.md / REBUILD_STATUS_TH.md ข้อ 7)

# 3) อัปพื้นผิว operational ให้ตรง hash ใหม่ — เครื่องมือบอกเอง
python3 test_golden_single_source.py                        # แดง = บอก surface ที่ต้องแก้ (README/Makefile/ci.yml/GOLDEN.md/DECISIONS banner ฯลฯ)

# 4) ด่านเต็มบน golden ใหม่
bash run_ci.sh /mnt/project                                 # ต้อง exit 0
```

> 13 จุดที่เหลือ golden-neutral — ยืนยันได้ว่าไม่กระทบ `ae84d3f0` เพราะรหัสเหล่านั้น **0 occurrence** ใน `baseline.json` (สแกนแล้ว: CMP003/BR001/DT004/ADDR002/ADDR005/ADDR006/TAX003/VAT006/VAT007/DOC003/DT003 = 0 ; DOC001 มีแต่ชีต "6"=วันจริง).

---

## 3) สิ่งที่พิสูจน์แล้ว (cloud env นี้)

- ✅ fixture `b5c415bb` (engine==agent==baseline) — ไม่ขยับ
- ✅ `check_invariants.py` 4/4 · doc-sync PASS · `run_ci.sh` exit 0 (รวม `[3x14e]`+`[3x14f]`)
- ✅ ทุกการแก้ reproduce: บั๊กหาย + ของจริงไม่หลุด (CP All/สนญ.จริง/ซ้ำจริง/VAT-included จริง/บอลวาว ยังจับ)
- ✅ DT002 + กฎวันที่อื่น สะอาด (ตรวจรอบ audit) → DT003 (064) เป็นระเบิดเวลาวันที่ตัวเดียวในกรอบ 5 ปี และปิดแล้ว
- ✅ ทุกไฟล์อยู่ในเพดาน LOC (ไฟล์ >600 = ตัวที่ whitelist เดิม)

### สรุป 1 บรรทัด
**แก้ครบ 15 จุด (กฎที่เปิด) + 3 จุด infra · golden fixture ไม่ขยับ · CI เขียว · เหลือ rebaseline corpus (ITM004/ITM016) บน Python 3.12 ของเจ้าของ = ขั้นตอนปกติหลังแก้บั๊กที่ปรับผลตรวจให้ถูกขึ้น.**
