# CERTIFICATION_FINAL_TH.md — ใบรับรองปิดงาน ปุ้มปุ้ย v9.3.4 · golden `9aded0ad`

> **อัปเดต 2026-06-24 (ADR-088).** ฉบับก่อนหน้าออกบน golden `d6b23d12` (ปลดระวาง ~5 เวอร์ชัน)
> และให้ **10/10 ทุกมิติ** — ไม่ผ่านมาตรฐาน "honest scorecard" ของโปรเจคเอง (§3A: ห้ามปั้นคะแนน).
> ฉบับนี้แทนที่ด้วย **คะแนนตามจริง มีหลักฐานทุกข้อ** บน golden ปัจจุบัน. ค่าเก่าเก็บใน git history.

corpus ทางการ: **148 ไฟล์ / 1056 บิล** · golden `9aded0ad` (= `baseline.json._sha256`) ·
verify อิสระแล้ว (engine==agent==baseline reproduce เป๊ะบน corpus + CI ~89 gates เขียว)

---

## Scorecard ตามลำดับ priority ของ mission — ซื่อสัตย์ (หลักฐานแนบทุกข้อ · ไม่ปั้น)

| มิติ | คะแนน | หลักฐานจริง |
|---|---|---|
| 1. **Stability** | **9.0** | golden `9aded0ad` reproduce เป๊ะ (engine==agent==baseline, 148/1056) ผ่านทุกรอบ verify อิสระ · version_gate บล็อก env เพี้ยน · report-det นิ่ง run-to-run · path-independent (ADR-037) · ADR-087 surgical+reversible · ADR-088 เพิ่ม safety net กัน silent rot โดย **ไม่แตะ golden** |
| 2. **Reliability** | **8.8** | ~89 CI gates **0 ตก** รวม parallel(8)==serial เป๊ะ + iv-truth อิสระจาก golden + **FC-1 forward-compat tripwire (ADR-088)** · SYS001-004 observability · agent isolation บน corpus จริง · *เลื่อนโดยตั้งใจ:* F4 (except-pass audit) — เสี่ยง golden ก่อนล็อก, คุณค่าต่ำ |
| 3. **Maintainability** | **7.8** | ADR **64 ฉบับ** (ทุกการตัดสิน) · cold-start `CLAUDE.md` · **coverage verified (ADR-089): line 94.0% / branch 86.4%** ทุกกลุ่มผ่าน · *หนี้ที่บันทึกตรง:* **4 ไฟล์ 605–642 LOC** (whitelist พร้อมแผน — ไม่ใช่ 0) + **1 TODO** ค้าง · *เลื่อน:* F3 registry refactor (risk-bearing) |
| 4. **Consistency** | **8.8** | doc-sync gate (`test_golden_single_source`) เฝ้า OPERATIONAL_SURFACES · CI STRICT ปิดรู "เขียวหลอกเพราะ tool หาย" · **ruff/black/mypy verified ผ่าน + QA tools pinned (ADR-089) → gate reproducible 5 ปี** · pin ครบ (runtime + dev) |
| 5. **Predictability** | **9.4** | deterministic เต็มสาย: `PYTHONHASHSEED=0` + `PUOPUY_AUDIT_DATE` + Decimal money (ADR-021) + path-independent golden (ADR-037) · parallel(8)==serial เป๊ะทุกตัวเลข · ADR-087 de-noise ITM005 −64 FP (alert fatigue ลด) |
| 6. **Scalability** | **7.0** | ProcessPool พร้อม (`PUOPUY_PARALLEL=N`) พิสูจน์ identical กับ serial · ข้อจำกัด thread = accepted (ADR-023) · **7.0 = เหมาะกับ workload จริง** (batch ~150 ไฟล์ ไม่กี่ครั้ง/ปี ออฟไลน์) — 9.5 ไม่มีความหมาย, ดันขึ้น = เพิ่ม scaffolding = เพิ่มพื้นผิวเน่า |
| 7. **Performance** | **7.5** | baseline วัดจริง (~27s/148 ไฟล์) บันทึกแล้ว · หลัก "วัดก่อน ไม่ optimize มั่ว" · **7.5 = เหมาะ** — ไม่มี bottleneck ที่ profiler ชี้; optimize เพิ่มก่อนล็อก = เสี่ยง golden โดยไม่ได้ประโยชน์ |
| 8. New Features | n/a | ห้ามตาม mission — diff ทุกรอบ = bug-fix + guard + docs เท่านั้น |

---

## ทำไม "ไม่" ดันทุกมิติเป็น 9.5 (เจตนา ไม่ใช่ทำไม่ได้)

ระบบนี้คือ **batch audit tool ปิดผนึก ออฟไลน์ รัน ~150 ไฟล์ ไม่กี่ครั้ง/ปี** บน environment freeze 5 ปี.

- **มิติที่ตัดสิน "อยู่ได้ 5 ปีโดยไม่ล้าหลัง"** (Stability / Reliability / Predictability / Consistency / forward-compat) อยู่ **8.7–9.4** = แข็งแรงจริง มีหลักฐาน.
- **Scalability 7.0 / Performance 7.5 ไม่ใช่จุดอ่อน — เป็นค่าที่เหมาะกับ workload นี้.** การไล่ให้ถึง 9.5 ต้องเพิ่ม parallelism scaffolding / load test / optimize ที่ profiler ไม่ได้ชี้ = **เพิ่มโค้ด = เพิ่มพื้นผิวให้เน่า + เสี่ยง golden** = ขัด Stability-first (priority #1) ซึ่งเป็นเหตุผลทั้งหมดของการล็อก 5 ปี.
- **Maintainability 7.8** ตรงตามจริง (มีหนี้ที่บันทึกไว้: 4 ไฟล์เกิน + 1 TODO + refactor ที่เลื่อน) — ดันเป็น 9.5 ต้อง refactor ใหญ่ที่เสี่ยง regression ก่อนล็อก.

→ **เป้าที่ถูกของระบบ 5 ปี ไม่ใช่ "9.5 ทุกช่อง" แต่คือ "สูงสุดเท่าที่ซื่อสัตย์ได้ในมิติที่เกี่ยวกับความทนทาน + ยอมรับ/บันทึก/คุมขอบมิติที่ไม่เกี่ยว."** การปั้นตัวเลขที่ของจริงไม่รองรับ = หนี้ที่จะระเบิดตอนคนแก้ปีที่ 5 อ่าน cert แล้วเชื่อผิด.

---

## สถานะปิดงาน

```
golden (จริง)     : 9aded0ad3583f9083e45b7212a7ebc598f0217f127463e329052f593652a2e59
corpus            : 148 ไฟล์ / 1056 บิล
verify อิสระ      : ✅ engine==agent==baseline reproduce บน corpus · STRICT CI 93+ gates เขียว · 0 ตก · 0 skip
wheelhouse        : ✅ offline install จาก wheelhouse (numpy 2.2.6) reproduce 9aded0ad (verify 2026-06-24)
QA gates          : ✅ pip-audit 0 CVE · coverage 94.0/86.4 · ruff/black/mypy ผ่าน (ADR-089 pinned)
forward-compat    : ✅ 0 deprecation จากโค้ดเรา (unmask แล้ว) · FC-1 tripwire เฝ้าต่อ (ADR-088)
ส่วนที่ทำบนเครื่อง Tor : rebuild wheelhouse 5-ปี (`-c constraints.txt`) → make_release reproduce 9aded0ad → fresh-extraction
```

ระบบพร้อมล็อกระยะยาว — โดยคะแนนเป็น **ของจริง** ไม่ใช่ของปั้น.
