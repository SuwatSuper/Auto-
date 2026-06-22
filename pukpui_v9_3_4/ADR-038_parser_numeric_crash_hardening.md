# ADR-038 — กัน parser ครัชจาก "เซลล์ตัวเลขพยาธิสภาพ" (inf / ยอดมหึมา) ทำบิลทั้งชีต/ไฟล์หาย

สถานะ : ACCEPTED — 17.06.2026
บริบท : รอบ bug-hunt v9.3.1 (hardening) พบ 3 จุดบนเส้น parse ที่ "เซลล์ตัวเลขวิปริต" ทำให้
        ตัวแปลงเลขครัช แล้วถูก catch-all guard ของ parser กลืน → **บิลทั้งชีต/ไฟล์หายเงียบ**
        (SYS001) โดยผู้ตรวจไม่รู้ว่าใบกำกับของผู้เสียภาษีหายไป

> ระดับ: Parse-S1 = 🔴 ร้ายแรง (โดยผลกระทบ — ข้อมูลผู้เสียภาษีหายเงียบ),
>        Parse-M1 = 🟡 กลาง, Parse-M3 = 🟡 กลาง (latent)

---

## อาการ + Root cause (สืบจาก source จริง ไม่เดา)

### Parse-S1 — `OverflowError` ใน `_dic_int_run` (parser_p0a.py)
`int(float(str(v)))` สำหรับเซลล์ข้อความ `'inf'`/`'-inf'`/`'Infinity'`/`'1e400'` :
`float('inf')` สำเร็จ แต่ `int(float('inf'))` โยน **`OverflowError`** ซึ่ง
`except (ValueError, TypeError)` เดิม **ไม่ครอบ**. `_dic_int_run` ถูกเรียกต่อทุกคอลัมน์ใน
`detect_item_columns`/`_dic_find_seq` → ครัชก่อนสร้างบิล → `parse_file` ดักที่ระดับชีต
(parser_p2.py:~568, `except Exception` → log SYS001) → **บิลทุกใบในชีตนั้นถูกทิ้ง**
(`'nan'` ไม่โดน เพราะ `int(float('nan'))` โยน `ValueError` ที่ครอบอยู่แล้ว)

### Parse-M1 — `decimal.InvalidOperation` ใน derive-VAT
`subtotal` (หรือ qty×price รวม) ที่ใหญ่ระดับ ≥ ~1e28 ทำ
`(_D(sub) * Decimal('0.07')).quantize(Decimal('0.01'))` โยน **`InvalidOperation`**
(ผลลัพธ์เกินความละเอียด context 28 หลัก). 3 จุด:
`parser_p2._pb_finalize_amounts` PATCH-5 (ไม่ห่อ try เลย), PATCH-6 (`except` ครอบแค่
`(ValueError, TypeError)`), และเส้น merge `parser_p0a.merge_continuation_bills`.
ครัชหลุดถึง `parse_file`/`parse_all_files` → บิลทั้งชีต/ทั้งไฟล์หาย

### Parse-M3 — `_cell_to_num` ปล่อย `±inf` หลุด (latent)
`return None if f != f else f` กันแค่ `NaN` (`nan != nan`) แต่ `inf == inf` → `inf` ผ่าน
→ `_D(inf) * Decimal('0.07')` โยน `InvalidOperation` ปลายน้ำ (ตระกูลเดียวกับ M1).
ปัจจุบัน **ไม่ reachable จากไฟล์ Excel ที่ save** (openpyxl เขียน `inf` เป็น `None`,
สตริง `'inf'` ผ่าน regex ไม่ได้) — เป็น defensive guard กันผู้เรียกในอนาคต/DataFrame in-memory

---

## Decision (การแก้ — surgical, golden-safe)

1. `parser_p0a._dic_int_run` : เพิ่ม `OverflowError` ใน except (ค่า inf/1e400 ไม่ใช่ลำดับ
   สินค้า 1..50 อยู่แล้ว → ข้ามถูกต้อง)
2. derive-VAT 3 จุด : ครอบ/เพิ่ม `InvalidOperation` (+`ValueError,TypeError`) → degrade
   เป็น `vat=None` แทนครัช
3. `parser_p0a._cell_to_num` : ใช้ `math.isfinite(f)` (กัน NaN + ±inf จุดเดียว)
4. ตรึงด้วย `test_bughunt_hardening.py` (unit + end-to-end ผ่าน fixture) + อัปเดต reference ใน
   `test_dic_int_run_equiv.py` ให้กัน OverflowError เหมือนกัน (differential ยัง byte-identical)

## Golden impact — **ไม่ขยับ (golden-safe)**
ข้อมูลจริงในชุด golden เก็บตัวเลขเป็น number/datetime จริง (ไม่ใช่ข้อความ `'inf'`) และยอดจริง
เล็กกว่า 1e28 มาก → เส้นปกติเดินทางเดิมเป๊ะ. พิสูจน์: fixture oracle = `269ddaed…`
(engine==agent==baseline) ก่อน/หลังแก้ ; ยอดปกติ 2500 → vat 175.0 / total 2675.0 เท่าเดิม

## Migration risk — ต่ำมาก
แก้เฉพาะเส้น exception/edge ; ไม่แตะ business logic. `parser_p2.py` คุมไว้ที่เพดาน 600 LOC
(test_file_size_ceiling). ทั้งสุดท้ายไฟล์นี้เข้าใกล้เพดาน → ผู้ดูแลควรพิจารณาซอยในอนาคต
(บันทึกเป็น Low finding)
