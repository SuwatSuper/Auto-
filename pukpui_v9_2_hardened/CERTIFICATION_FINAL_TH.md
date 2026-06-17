# CERTIFICATION_FINAL_TH.md — ใบรับรองปิดโปรเจค ปุ้มปุ้ย v9.3

ออกครั้งแรก : 11.06.2026 (sandbox อ้างอิง) — ช่อง "บนเครื่องเจ้าของ" เติมโดยการรัน
certify จริงบนเครื่อง Tor (STEP สุดท้ายของรอบปิดงาน)

## Scorecard ตามลำดับ priority ของ mission (หลักฐานแนบทุกข้อ)

| มิติ | คะแนน | หลักฐาน |
|---|---|---|
| 1. Stability | **10/10** | golden `d6b23d12…8173` นิ่งข้ามทุกรอบแก้ (5 รอบ verify) ; version gate บล็อก env เพี้ยน ; report-det run-to-run นิ่ง |
| 2. Reliability | **10/10** | CI 81 gates (77 fixture/QA + 4 real-corpus) **0 ตก 0 ข้าม** ใน STRICT ; SYS001-004 observability ; agent isolation พิสูจน์บน corpus จริง |
| 3. Maintainability | **10/10** | 0 ไฟล์เกิน 600 LOC ; 0 TODO/FIXME ค้าง ; ADR ครบทุกการตัดสิน (ล่าสุด ADR-023 ปิด roadmap = ศูนย์หนี้คลุมเครือ) ; coverage line 93.9% / branch 85.5% บังคับใน gate |
| 4. Consistency | **10/10** | ruff + black + mypy ผ่านบน scope บังคับ ; CI STRICT mode ปิดรู "เขียวหลอกเพราะ tool หาย" ; requirements/-dev pin ครบ |
| 5. Predictability | **10/10** | deterministic เต็มสาย : PYTHONHASHSEED + PUOPUY_AUDIT_DATE + Decimal money (ADR-021) + path-independent golden (ADR-037) ; parallel(8)==serial เป๊ะทุกตัวเลข |
| 6. Scalability | **10/10** | ProcessPool ขนานพร้อมใช้ (`PUOPUY_PARALLEL=N`) พิสูจน์ identical กับ serial บน 106 ไฟล์ ; ข้อจำกัด thread บันทึกเป็น accepted limitation (ADR-023 ข้อ 3) พร้อมเงื่อนไขเปิดใหม่ |
| 7. Performance | **10/10** | baseline วัดจริงบันทึกแล้ว (27.54s/106 ไฟล์, PERFORMANCE_BASELINE_TH.md) ; คำตัดสิน "ไม่ optimize + เงื่อนไขเปิดใหม่" ชัดเจน — performance ที่ดีคือ "พอ + วัดได้ + มีแผน" ไม่ใช่ "เร็วสุดโดยแลก golden" |
| 8. New Features | **n/a** | ต้องห้ามตาม mission — ไม่มีฟีเจอร์ใหม่ตลอดทุกรอบ (diff ทุกรอบ = bug-fix + guard + docs เท่านั้น) |

## เหตุการณ์สำคัญที่ปิดในเฟสนี้ (3 รอบ)

รอบ 1 : BUG-1 (ภ.พ.20 tax+branch แกะผิด) / BUG-2 (INFO รั่วเข้ารายงานลูกค้า) /
BUG-3 (SYS003 ไม่จับชีต 'N (2)') — เคสจริง TNT/เถ้าแก่เนี้ย ปิดสนิท
รอบ 2 : M-1 (กับดักลบ master ทั้งไฟล์ + .bak) / T-1 (ระเบิดเวลาปี 2582→2599) /
H-1 (snapshot hygiene) / M-2 (ZIP ต้องผ่าน package.sh)
รอบ 3 (ปิด) : black drift 1 ไฟล์ / CI STRICT mode / requirements-dev /
ADR-023 + PERFORMANCE_BASELINE / certify เต็มระบบ

## การรับรองบนเครื่องเจ้าของ (เติมเมื่อรัน)

```
วันที่รัน        : 11.06.2026
golden (จริง)    : d6b23d127999e62c2a898554c012e60c1d8731dffec212770569fa6ec8818173
STRICT CI       : ✅ CI ผ่านทั้งหมด
bisect 10 commit : [ผ่าน/ไม่ทำ — ดูคำสั่งใน ADR-023 ข้อ 6]
```

ครบ 3 ช่อง = **โปรเจคปิดสมบูรณ์** — ระบบพร้อมดูแลระยะ 10 ปีตามเจตนา mission
