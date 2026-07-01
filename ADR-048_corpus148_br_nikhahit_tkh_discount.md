# ADR-048 — Re-baseline golden 106/834 → 148/1056 + แก้ 2 บั๊ก (BR สํา nikhahit, TKH คอลัมน์ส่วนลด)

วันที่: 2026-06-19
สถานะ: ✅ ตัดสินใจแล้ว — golden ใหม่ `ddd06191…` (เดิม `df91493f…` ปลดระวาง)

---

## บริบท (Context)

เจ้าของระบบสั่งให้ forensic review ไฟล์ใหม่ทั้งหมดในคอร์ปัสด้วยระบบเอง แก้ทุกปัญหาที่พบ
เทสครบ แล้วส่งระบบสมบูรณ์ ระหว่างทำงานพบว่า **คอร์ปัสจริง `/mnt/project` เปลี่ยนไปมาก**
จากตอน baseline `df91493f`:

- **เพิ่ม 42 ไฟล์ใหม่** (270 บิล): SSN, TNT_69_01, TOR_69_05, และงวดใหม่ของ EKS/KNT/SHS/TSH/TKH/CHM ฯลฯ
- **แก้ไข 16 ไฟล์เดิม** จาก 106 ไฟล์ (จำนวนบิลรวมของ 106 ไฟล์เดิม: 834 → 786)
- รวมสถานะปัจจุบัน: **148 ไฟล์ / 1056 บิล** (786 จาก 106-เดิมที่แก้ + 270 จาก 42-ใหม่)

(การเปลี่ยนไฟล์เป็นของเจ้าของระบบ — ไม่ใช่ผลจากโค้ด: รัน "โค้ดเดิม" บนไฟล์ปัจจุบันก็ได้ 786 บิล)

## Forensic review (พิสูจน์ก่อน rebaseline)

**ความซื่อตรงของการอ่าน (independent cell-level) — ทั้งคอร์ปัส 1056 บิล:**
- IV faithful: 1056/1056 · tax_id faithful: 1056/1056 · ocr-subtotal ตรงเซลล์: 654/654
- (2 เคสที่ verifier รายงานว่า "ไม่เจอ" = ชีตต่อเนื่อง "4 + 4 (2)" / "2 + 2 (2)" — ข้อมูลอยู่ในชีตจริง "4"/"2" ครบ → artifact ของ verifier ไม่ใช่ misread)
- item_sum / derived subtotal: ถูกต้องทุกบิล · วันที่ invalid (day>31/month>12): 0

**การจัดประเภท issue ของ 42 ไฟล์ใหม่ (350 issue):**
- DT002 (future), DOC001 (วันที่≠ชีต), DT001 ("012"→เดือน12 แบบเดียวกับ KRR_69_012 ที่อยู่ใน golden เดิมแล้ว),
  CMP006 (stub ภ.พ.20 1 บริษัท), ITM004/005/010/011/015/018/019 (typo/หน่วย advisory) = **ระบบจับถูก ไม่ใช่บั๊ก**
- **2 บั๊กจริง (ระบบอ่านผิด → ฟ้องผิด) → แก้ใน ADR นี้:**

---

## บั๊ก A — BR สาขาฟ้องผิด: สระอำแบบ nikhahit "สํา" (16 บิล, TSH_69_056)

**อาการ:** บิล TSH_69_056 ทุกใบมีหัวบิล "บริษัท … จำกัด (สํานักงานใหญ่)" — ระบุสำนักงานใหญ่ครบ
แต่ระบบฟ้อง BR001 "ไม่พบรหัสสาขา" + BR002 "ไม่ระบุ สนญ./สาขา" รวม 16 บิล

**ต้นเหตุ (forensic):** เซลล์ใช้ "สํา" = NIKHAHIT (U+0E4D) + SARA AA า (U+0E32) แทน "สำ" = SARA AM ำ (U+0E33).
เรนเดอร์เหมือนกันแต่เป็นคนละ code point — `unicodedata.normalize('NFC')` **ไม่ fold ให้**.
ตัวจับสาขา (parser_p1 `_scan_branch_block` ฯลฯ) ค้น literal `'สำนักงานใหญ่'` (sara am) → พลาดรูป nikhahit.

**ความชุก:** golden เดิม 106 ไฟล์มี "ํา" 2 ไฟล์ (KRR_69_057, EKS_69_0516) · ใหม่ 2 ไฟล์ (TSH_69_056, SHS_69_05_เพิ่ม)

**การแก้:** เพิ่ม fold ใน `normalize_text` (puopuy_core.py) — จุดเดียวกลางของการ normalize ข้อความ:
```python
s = unicodedata.normalize('NFC', s)
s = s.replace('\u0e4d\u0e32', '\u0e33')   # ◌ํ + า  →  ำ
```
ทุกการ match (สาขา/ชื่อบริษัท/typo) จึงเห็นรูป canonical พร้อมกัน.

**ผลตรวจ:** `normalize_text('สํานักงานใหญ่')` → `'สำนักงานใหญ่'` · TSH_69_056 BR001/BR002 16 → 0 (branch '00000') ·
ไฟล์ golden ที่มี "ํา" fold ถูกต้องตามหลักภาษา ("ดํา"→"ดำ", "ตําบล"→"ตำบล", "อําเภอ"→"อำเภอ")

---

## บั๊ก B — ITM001 ฟ้องผิด: คอลัมน์ส่วนลด 25% (18 บรรทัด/6 บิล, TKH_69_05)

**อาการ:** TKH_69_05 ฟ้อง ITM001 "0.25×2970=742.50 แต่=33412.50" รวม 18 บรรทัด — ทั้งที่ยอด/VAT ถูกต้อง

**ต้นเหตุ (forensic — อ่านเซลล์จริง):** เทมเพลต TKH มีคอลัมน์ส่วนลดต่อบรรทัด:
col[12]=qty(15), col[13]=price(2970), **col[14]=ส่วนลด(0.25=25%)**, col[17]=ยอดสุทธิ(33412.5).
สมการ: `15 × 2970 × (1−0.25) = 33412.5` ✓ — เป็นบรรทัดมีส่วนลดถูกต้อง.
TKH เก่า (ใน golden) col[14]=0.0 (ไม่มีส่วนลด) → `qty×price = amount` → detect ปกติอ่าน qty=col12 ถูก.
TKH_69_05 มีส่วนลด → `qty×price ≠ amount` → `_dic_pick_qty_price` หา combo ไม่ผ่าน → ตก fallback "min=qty"
→ เลือกคอลัมน์ค่าน้อยสุด (col14=0.25 = ส่วนลด) เป็น qty ผิด → ITM001 ฟ้อง (0.25×2970≠33412.5).
(ยอด/subtotal/VAT อ่านจาก col17 ตรง → ถูกต้องเสมอ; ผิดเฉพาะ field qty + ธง ITM001)

**การแก้:** เพิ่ม discount-aware detection ใน parser_p0a `_dic_pick_qty_price` (ก่อนตก fallback) —
ลอง `qty×price×(1−d) ≈ amount` โดย d มาจากคอลัมน์ที่ค่าอยู่ใน [0,1):
```python
def _dic_score_combo_discount(M, item_rows, amt_col, qc, pc, nums_c): ...  # ให้คะแนน combo แบบหักส่วนลด
# ใน _dic_pick_qty_price: ถ้า combo ปกติไม่ผ่าน 50% → ลอง discount combo → คืน qty/price ที่ถูก
```
**ไม่แตะกฎ ITM001** — เพราะ r_itm001 มี logic ส่วนลดอยู่แล้ว (skip ถ้า discount% ∈ [1,50]).
เดิมไม่ทำงานเพราะ qty อ่านผิด (0.25) ทำให้ e=742.5 < amount → เงื่อนไข "amount<e" ไม่เข้า.
พอ qty=15 ถูก → e=44550 > amount=33412.5 → discount 25% ∈ [1,50] → skip อัตโนมัติ.

**ผลตรวจ:** TKH_69_05 qty 0.25 → 15 (ถูก) · ITM001 18 → 0 · ยอด/subtotal/VAT ไม่เปลี่ยน

---

## ความเป็นการแก้แบบ surgical (พิสูจน์ด้วย per-bill diff บนคอร์ปัสปัจจุบัน)

diff "โค้ดเดิม vs โค้ดแก้แล้ว" บนไฟล์ปัจจุบันชุดเดียวกัน (กันสับสนกับการเปลี่ยนไฟล์):
- discount fix: เปลี่ยน **เฉพาะ TKH_69_05** (6 บิล) — ไฟล์อื่นรวม TKH เก่า (ส่วนลด=0) ไม่ขยับ
- normalize fold: เปลี่ยน **เฉพาะไฟล์ที่มี "ํา"** (TSH_69_056 BR + EKS_69_0516 + product name ใน KRR_69_057/SHS_69_05_เพิ่ม) — ไฟล์ที่ไม่มี "ํา" เอาต์พุต normalize เท่าเดิม

## หมายเหตุ — agent notepad (advisory, ไม่กระทบ golden)
ในงานชุดนี้ยังแก้บั๊กเก่าจากการซอย monolith: `_emit_agent_notepad` ตั้ง `PUKPUI_MAIN_MODULE=__name__`
ซึ่งหลังซอย = 'pukpui_modular_funcs' (ผิดโมดูล ไม่มี io symbol) → import gate ล้ม → `agent_report.txt`
ถูกข้ามเงียบทุกครั้ง. แก้ให้ชี้โมดูล orchestrator จริง (มี `run_audit_core`). เป็น advisory ล้วน — golden ไม่ขยับ.

## ผลกระทบ / การตัดสินใจ (Decision)

1. **คอร์ปัสทางการใหม่ = 148 ไฟล์ `/mnt/project` (1056 บิล)** — golden `ddd06191…` (= `baseline.json._sha256`)
2. `df91493f` (106/834) **ปลดระวาง** → เพิ่มใน RETIRED_PREFIXES (test_golden_single_source.py)
3. backup: `baseline.df91493f.pre-corpus148.json`
4. ไฟล์แก้: `puopuy_core.py` (fold) · `parser_p0a.py` (discount detect) · `pukpui_modular_funcs.py` (agent notepad)
5. operational surfaces sync `ddd06191…` (doc-sync gate ผ่าน) · ledger DECISIONS.md เก็บประวัติ df91493f

## ความเสี่ยง (Migration risk)

ต่ำ–ปานกลาง:
- fold "ํา"→"ำ" เป็น Unicode equivalence จริง — ปลอดภัยทุกที่ที่ใช้ normalize_text
- discount detect ทำงานเฉพาะตอน detect ปกติไม่ผ่าน (qty×price≠amount) → ไม่แตะไฟล์ไม่มีส่วนลด
- ทั้งคู่พิสูจน์ surgical ด้วย per-bill diff + ทั้งคอร์ปัส faithful 1056/1056

ถ้า hash drift จาก `ddd06191` โดยไม่ตั้งใจ → revert ทันที + ลง ADR (กฎเดิม)
