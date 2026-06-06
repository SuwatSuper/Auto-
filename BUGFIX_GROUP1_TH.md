# รายงานแก้บั๊ก — ปุ้มปุ้ย v9.2 (สถานะล่าสุด)

> รีเช็คโครงสร้างโค้ด → จัดบั๊กเป็น 3 กลุ่มตาม "ความเสี่ยงต่อ golden hash" แล้วทยอยแก้
> **กติกาเหล็ก:** ผลตรวจต้อง reproduce ได้ → ทุกการแก้พิสูจน์ golden ไม่ขยับ

## วิธีพิสูจน์ "ไม่กระทบระบบ" (ใช้ทุกการแก้)
- **golden hash ทางการ (106 ไฟล์):** `35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba`
  *(ต้องมี `/mnt/project` — แซนด์บ็อกซ์นี้ไม่มี จึงพิสูจน์ทางอ้อมด้านล่าง)*
- **fixture (3 บิล):** `d8bcde8555034a203f80d2a596c42ea57b2f1a39ce67003f5629cea03185b07c` — เท่าเดิมทุกการแก้
- **real-case (3 ไฟล์ .xls จริง / 15 บิล):** `87a46aaa669bf6ab938c5fce1b58be86728f06b963f940209de20ccc63e01ef1` — เท่าเดิมทุกการแก้
- `bash run_ci.sh` เขียวครบ (44 ขั้น) · sandbox เป็น Python 3.11 ใช้ `PUOPUY_ALLOW_VERSION_MISMATCH=1`

---

## ✅ เสร็จแล้ว

### กลุ่ม 1 — ชุดปลอดภัย (golden ไม่ขยับ)
**commit `e682962`** (C1 + M1–M7 + L8/L9/L14):
- C1 sort ไฟล์ production · M1/M2/M3 กัน dashboard crash + figure leak · M4 setdefault คีย์บิล
- M5 เทียบปี พ.ศ.→ค.ศ. · M6 REVIEW_ONLY ครบ · M7 guard hash_randomization · L8/L9/L14 observability

**commit `20c8f48` + แก้ตาม CI:** Low batch:
- L3 subtotal==0 ใน viewer · L4 `.removesuffix('.0')` · L5 dedup `is not None`
- L11 contracts summary=List · L12 ลบ seen_fname ตาย
- ~~L2 ลบ dead code (mo/day)~~ **ถอนคืน** — CI จับได้ว่า "ไม่ตาย": มี date-like
  duck-typed (month=0/day=40) ที่ test_rules_extra ตรึงไว้ → คงโค้ดเดิม

### กลุ่ม 2 — แก้แล้วผลอาจเปลี่ยน (พิสูจน์แล้วว่า golden ไม่ขยับบนคอร์ปัส)
**commit `60e146f` (M8) + แก้ตาม CI:** VAT 7.00 บาทพอดี — ทิ้ง 0.07 เสมอ ;
ทิ้งเลข 7 เมื่อ "ไม่ใช่ยอดทศนิยม" (แถวมี %/อัตรา **หรือ** เขียน '7' ล้วนไม่มีจุด) ;
คงไว้เมื่อเป็น '7.00' (ยอดจริง). วิธีนี้รักษา test เดิม (bare 7→rate) + แก้บั๊กยอด 7.00
→ unit test ผ่าน (bare 7→None / 7.00→7.0 / 7%→None / 0.07→None) · fixture+real-case ไม่ขยับ

**commit `533fc05` (M9):** Excel-serial เมื่อไม่มี xlrd — fallback pandas (origin 1899-12-30)
→ พิสูจน์ fallback ตรง xlrd เป๊ะ (serial 30001/45000/45292/69999) · กิ่งนี้ไม่ทำงานบนเครื่อง golden

---

## ⏳ ยังเหลือ — กลุ่ม 1 (Low) ที่เลื่อน (golden-neutral แต่อ่อนไหว/วงกว้าง → แยก PR)

| รหัส | ไฟล์ | ปัญหา | วิธีแก้ | เหตุที่เลื่อน |
|---|---|---|---|---|
| L1 | `rules_*` ~15 จุด | `except Exception: return []` กลืน error ไม่ log | route ผ่าน `log_system_issue` หรือแคบ except | แตะหลายกฎ |
| L6 | `file_guard.py:74,91` | zip-bomb fail-open กลืน error โครงสร้าง zip | แยก IO error vs zip error | แตะ security guard + `test_input_hardening` |
| L7 | `pukpui_modular_funcs.py:351` | `setdefault('PUKPUI_MAIN_MODULE',__name__)` ชี้ slice | ใส่ชื่อ orchestrator | core resolution ซับซ้อน |
| L10 | `agents/super_agent.py:46` | `_EXPECTED` ขาด `verification` | เพิ่ม `"verification"` | `test_agents`/`test_agent_conformance` อ้างถึง |
| L13 | `agents/ai_review_agent.py:97` | sort ไม่มี tiebreaker เสถียร | เพิ่มคีย์ file/sheet/iv/code | ปิดโดย default (enable_ai=False) |
| L15 | `parallel_audit.py:103` | default `workers=cpu_count()` chunk ขึ้นกับเครื่อง | clamp/บังคับส่ง workers | merge order-preserving อยู่แล้ว |

> วิธีทำต่อ: แก้ทีละตัว → `golden_master.py . /tmp/x.json tests/fixtures` (= d8bcde85) + `... tests/real_cases` (= 87a46aaa) + `bash run_ci.sh` เขียว → commit

---

## 🚫 กลุ่ม 3 — "อย่าแตะ" (golden เข้ารหัสพฤติกรรมไว้โดยตั้งใจ)
| จุด | เหตุผล |
|---|---|
| `rules_engine_rules_b.py:250` `r_itm008` | ปิดอยู่ (`enabled:False`) — เปิดต้อง port Decimal + regen golden |
| `rules_engine_rules_b.py:380` `r_vat004` | dead แต่ golden เข้ารหัส "ไม่เคยฟ้อง" |
| `rules_engine_rules_c.py:122` `r_addr005` | แก้ = ขยับ ADDR005 บนข้อมูลจริง |

---

## ⚠️ ที่ยังต้องให้เจ้าของยืนยันเอง
M8/M9 พิสูจน์บน fixture + 3 real-case แล้วว่า golden ไม่ขยับ — แต่ **ยังไม่ได้รัน 106 ไฟล์จริง**
(แซนด์บ็อกซ์ไม่มี `/mnt/project`). ก่อน merge production ควรรันบนเครื่องที่มีข้อมูลจริง:
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02
python3 regression_full.py . /mnt/project       # ต้องได้ 35b2f7c8...
python3 verify_parallel.py /mnt/project 8        # serial == parallel
```
ถ้า hash ขยับแม้จุดเดียว → rollback + รายงาน (ไม่สร้าง baseline ใหม่เองตามกติกา)
