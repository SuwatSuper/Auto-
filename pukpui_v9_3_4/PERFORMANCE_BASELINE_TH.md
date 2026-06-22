# PERFORMANCE_BASELINE_TH.md — บันทึกฐานประสิทธิภาพ (ปิด roadmap-3 ตาม ADR-023)

วัดจริง 11.06.2026 บน corpus production เต็ม (sandbox อ้างอิง — เครื่องอื่นตัวเลขต่างได้
แต่ "สัดส่วน hotspot" คือสาระที่ใช้เทียบในอนาคต)

## ตัวเลขรวม

| ตัวชี้วัด | ค่า |
|---|---|
| ไฟล์ / บิล | 106 / 834 |
| เวลารวม parse + audit-core (serial) | **27.54 วินาที** (~0.26 s/ไฟล์, ~33 ms/บิล) |
| เครื่องมือวัด | `profile_baseline.py <DATA_DIR> 12` (cProfile cumulative) |
| Environment | `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02` + version gate ผ่าน |

## Hotspot (cumulative, เฉพาะฟังก์ชันในระบบ)

| อันดับ | ฟังก์ชัน | calls | cum (s) | หมายเหตุ |
|---|---|---|---|---|
| 1 | `parser_p2.parse_file` | 106 | 16.87 | เพดานรวมฝั่ง parse |
| 2 | `parser_p2.parse_sheet` | 836 | 11.88 | |
| 3 | `rules_engine.run_rules` | 834 | 10.19 | เพดานรวมฝั่งกฎ |
| 4 | `parser_p2._parse_block` | 786 | 9.11 | |
| 5 | `rules_engine_rules_c.r_tax008` | 834 | 7.47 | กฎเดี่ยวแพงสุด |
| 6 | `puopuy_core.clean_tax_id` | **716,095** | 6.04 | ถูกเรียกถี่สุด (ผ่าน r_tax008 เป็นหลัก) |

## คำตัดสิน (อ้าง ADR-023 ข้อ 1)

**ไม่ optimize** — 27.5 วินาที/รอบเดือน อยู่ในเกณฑ์ผู้ใช้รับได้สบาย ; การแตะ rules layer
เพื่อรีดวินาทีแลกความเสี่ยง golden ขยับ = ไม่คุ้ม

**เงื่อนไขเปิดงานใหม่ในอนาคต :** corpus โต ~10 เท่า (≥1,000 ไฟล์) หรือ wall เกิน ~5 นาที
→ เป้าแรกที่คุ้มสุดคือ memoize `clean_tax_id` ภายใน `r_tax008` (716K calls บน input ซ้ำสูง)
— ต้องเปิด ADR ใหม่ + golden gate ก่อนเสมอ
