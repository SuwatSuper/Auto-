# PERF_BASELINE — ฐานประสิทธิภาพที่วัดจริง (ปุ้มปุ้ย v9.2)

> ผลิต/ทำซ้ำได้ด้วย: `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 profile_baseline.py /mnt/project`
> ตัวเลขสัมบูรณ์ขึ้นกับเครื่อง (CPU/IO) — สิ่งที่สำคัญคือ **สัดส่วน hotspot** และใช้เทียบก่อน/หลัง.

## สรุป (ชุด sandbox 106 ไฟล์ / 836 บิล)

| ช่วง | เวลา (ตัวอย่างเครื่อง audit) | สัดส่วน |
|---|---|---|
| `parse_all_files` (parse) | ~17.6s | **~88%** |
| `run_audit_core` (56 rules + cross-check + summary) | ~2.0s | ~10% |
| รวม parse+audit-core | ~19.8s | 100% |

> หมายเหตุ: เอกสารเดิมระบุ parse ~9s (single-core หลัง OBJ-PERF) — ต่างจากตัวเลขข้างบนเพราะ
> เครื่อง/เวอร์ชัน numpy/ไม่มี pythainlp ต่างกัน. **สัดส่วน** (parse ครองเวลา) คือสิ่งที่คงที่และใช้เทียบ.

## Hotspot จริง (top cumulative — ฟังก์ชันในระบบ)

| ฟังก์ชัน | จำนวนเรียก | cumtime | หมายเหตุ |
|---|---|---|---|
| `parser_p2.parse_file` | 106 | ~17.6s | ต่อไฟล์ |
| `parser_p2.parse_sheet` | 836 | ~13.5s | ต่อชีต |
| `parser_p2._parse_block` | 799 | ~11.7s | ต่อบล็อกบิล |
| `parser_p0.detect_item_columns` | 799 | ~4.3s | ตรวจคอลัมน์รายการ |
| `parser_p0._dic_int_run` | **16,553** | ~3.9s | สแกนรันตัวเลขต่อเซลล์ (hot loop) |
| `parser_p1._row_label_match` | **35,661** | ~2.5s | จับ label ต่อแถว (hot loop) |
| `rules_engine.run_rules` | 836 | ~1.9s | 56 กฎต่อบิล |

## บทสรุปเชิงสถาปัตยกรรม

1. **bottleneck = parse ต่อเซลล์/แถว** (ไม่ใช่ typo อย่างที่อาจเดา). typo O(n²) จะกัดเฉพาะตอน
   unique names เยอะใกล้เพดาน `CFG['MAX_TYPO_NAMES']`=3000.
2. งาน parse **embarrassingly parallel ข้ามไฟล์** → `parallel_audit.parse_all_files_parallel`
   โจมตีตรงจุด และพิสูจน์แล้วว่า **byte-identical** (ดู DECISIONS § proof).
3. การไปไกลกว่านี้ (ลด `_dic_int_run`/`_row_label_match`) = แตะ parser (golden-gated) →
   ต้องผ่าน `regression_full` ยืนยัน `f1ac8421`/`f1ac8421` ไม่ขยับ ก่อนถือว่าเสร็จ.

## ตัวกันถดถอย (regression guards)

- `test_perf_budget.py` — canary จับ regression ระดับ catastrophic ของเส้น typo (ปรับ
  `PUOPUY_PERF_N` / `PUOPUY_PERF_BUDGET_S`).
- `verify_parallel.py <data> <workers>` + `test_parallel_merge_nonempty.py` — พิสูจน์ parallel==serial
  (รวม merge ของ system_issues ที่ไม่ว่าง).
