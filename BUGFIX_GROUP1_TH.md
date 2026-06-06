# รายงานแก้บั๊ก — กลุ่ม 1 (ชุดปลอดภัย: ไม่กระทบผลตรวจ/golden)

> วันที่: 2026-06 · ขอบเขต: รีเช็คโครงสร้างโค้ด ปุ้มปุ้ย v9.2 → แก้เฉพาะ "กลุ่ม 1"
> (robustness / observability / determinism-alignment) ที่ **ไม่ขยับ golden hash และผลตรวจ**

## พิสูจน์ว่า "ไม่กระทบระบบ"
- golden fixture hash **เท่าเดิมเป๊ะ** ก่อน/หลังแก้: `d8bcde8555034a203f80d2a596c42ea57b2f1a39ce67003f5629cea03185b07c`
- `bash run_ci.sh` ผ่านครบทุกขั้น (เทส + invariants + pin lenses + consolidator + parallel) — เขียวทั้งก่อนและหลัง
- หมายเหตุสภาพแวดล้อม: sandbox นี้เป็น Python 3.11 (lock = 3.12) จึงรันด้วย `PUOPUY_ALLOW_VERSION_MISMATCH=1`
  ซึ่งพิสูจน์แล้วว่า fixture hash ตรง 3.12 ทุกประการ (ต่าง python minor ไม่ขยับ hash ชุดนี้)

---

## รายการที่แก้ (11 จุด)

| รหัส | ไฟล์ | สิ่งที่แก้ | ทำไมปลอดภัย |
|---|---|---|---|
| **C1** 🔴 | `parser_p2.py` `get_files_via_drive` | `return clean` → `return sorted(clean)` | caller golden/regression sort อยู่แล้ว → production ไปตรง hash ที่รับรองไว้ ; fixture hash ไม่ขยับ |
| **M1** 🟡 | `reporting_p1.py:174` | กันคอลัมน์ `หน่วย` หาย (`''.fillna()` crash) | normal path เหมือนเดิม ; report ไม่อยู่ใน golden |
| **M2** 🟡 | `reporting_p1.py:199` | กัน `df[False]` KeyError ตอน flag column หาย | normal path เหมือนเดิม |
| **M3** 🟡 | `reporting_p0.py` | `finally: plt.close('all')` กัน figure รั่ว | ปิดหลัง savefig อยู่แล้ว ; idempotent |
| **M4** 🟡 | `rules_engine.py` `run_rules` | `setdefault` items/subtotal/vat/total | parser ใส่คีย์เสมอ → no-op กับบิลจริง ; golden ไม่ขยับ |
| **M5** 🟡 | `agents/verification_lenses_ext.py` | เทียบปี normalize พ.ศ.→ค.ศ. (`yr-543 if yr>2400`) | advisory layer ; เทสเดิม (ปี ≤2400) ยังผ่าน |
| **M6** 🟡 | `issue_consolidator.py:47` | `REVIEW_ONLY` ครบทุกรหัสเลน review | advisory ; เทส consolidator ยังผ่าน (item ผสม FIX) |
| **M7** 🟡 | `parallel_audit.py` | guard `sys.flags.hash_randomization` | CI ตั้ง seed ก่อน start → ผ่าน ; serial ไม่แตะ |
| **L8** 🟢 | `ปุ้มปุ้ย_..._modular.py` | เตือนเมื่อ `PUOPUY_PARALLEL` ค่าผิด | เพิ่ม print อย่างเดียว |
| **L9** 🟢 | `agents/report_agent.py` | log ก่อน fallback ไป cwd | เพิ่ม print อย่างเดียว |
| **L14** 🟢 | `parser_p2.py:466` | print โชว์ `type(e).__name__` | เปลี่ยน stdout เท่านั้น ไม่มีเทส assert |

---

## ยังเหลือ — กลุ่ม 1 (Low) ที่ "เลื่อนไว้" (ปลอดภัยแต่คุณค่าต่ำ/แตะของอ่อนไหว)

แก้ได้ทีหลังทีละตัว (ไม่กระทบ golden) — เลื่อนเพราะอยากให้ชุดแรกรีวิวง่าย:

| รหัส | ไฟล์ | ปัญหา | วิธีแก้ | ทำไมเลื่อน |
|---|---|---|---|---|
| L1 | `rules_*` หลายจุด | `except Exception: return []` กลืน error ไม่ log | log ผ่าน `log_system_issue` หรือแคบ except | แตะ ~15 จุดในกฎ — แยก PR ดีกว่า |
| L2 | `rules_engine_rules_c.py:258-263` | เช็ค `mo==0/day==0/day>31` ยิงไม่ได้ (dead) | ลบทิ้ง | churn ในไฟล์กฎ |
| L3 | `super_ultra_viewer.py:122` | `subtotal or (...)` ทำ subtotal=0 เพี้ยน | เช็ค `is not None` | viewer มีเทส — ตรวจ fixture zero ก่อน |
| L4 | `parser_p0a.py:290`,`parser_p2.py:66` | `.replace('.0','')` แทนทั้งสตริง | `re.sub(r'\.0+$','',...)` 2 ที่ | แตะ predicate parser 2 จุด |
| L5 | `parser_p2.py:380` | dedup TOR truthiness (0.0) | `is not None` | edge เล็ก |
| L6 | `file_guard.py:74,91` | zip-bomb fail-open กลืน error โครงสร้าง | แยก IO error vs zip error | แตะ security guard — เช็ค test_input_hardening |
| L7 | `pukpui_modular_funcs.py:351` | `setdefault('PUKPUI_MAIN_MODULE',__name__)` ชี้ slice | ใส่ชื่อ orchestrator | core resolution มีนัยซับซ้อน |
| L10 | `agents/super_agent.py:46` | `_EXPECTED` ขาด `verification` | เพิ่ม `"verification"` | กระทบ QA count — เช็ค pin |
| L11 | `agents/contracts.py:99` | `summary: Dict` แต่จริงเป็น `List` | เปลี่ยน annotation เป็น `List` | type-only |
| L12 | `agents/vendor_report.py:124` | `seen_fname` dead | ลบ | cleanup |
| L13 | `agents/ai_review_agent.py:97` | sort ไม่มี tiebreaker | เพิ่มคีย์ | ปิดโดย default (enable_ai=False) |
| L15 | `parallel_audit.py:103` | default `workers=cpu_count()` chunk ขึ้นกับเครื่อง | clamp/บังคับส่ง | merge order-preserving อยู่แล้ว |

---

## กลุ่ม 2 — "แก้แล้วผลตรวจเปลี่ยน" (ต้องตรวจ corpus + สร้าง golden ใหม่)

> ⚠️ **ห้ามเหมารวมกับกลุ่ม 1** — ต้องรัน `regression_full.py . <106 ไฟล์จริง>` ก่อน แล้วยอมสร้าง baseline ใหม่อย่างตั้งใจ

### M8 — VAT ที่เป็น 7.00 บาทพอดี ถูกทิ้ง · `parser_p1.py:354`
```python
if n is not None and not (abs(n-0.07) < 0.001 or n == 7):   # n==7 กิน "ยอด 7.00" ด้วย
```
- **ผล:** บิล subtotal=100 → VAT จริง 7.00 ถูกตัด → ปลายทาง derive 7% + พลิก provenance `ocr→derived` (กระทบเช็คตระกูล VAT010)
- **วิธีแก้:** เทียบ "เซลล์ดิบ" กับ token เรต (`%`/`0.07`) แทนเทียบค่าตัวเลข — หรือเอา `or n == 7` ออกแล้วบังคับให้แถวต้องมี token `%`/`.07` ด้วย
- **ขั้นตอน:** แก้ → `PYTHONHASHSEED=0 python3 regression_full.py . <data>` ดูไฟล์ที่ผลเปลี่ยน → ยืนยันว่า "ถูกขึ้น" ทุกไฟล์ → `golden_master.py` สร้าง baseline ใหม่ + เพิ่มเทสเคส 7.00

### M9 — วันที่ Excel-serial → None เมื่อไม่มี xlrd · `puopuy_dates.py:29`
```python
return safe(lambda: xlrd.xldate_as_datetime(v, 0))   # xlrd is None → AttributeError → safe กลืน → None
```
- **ผล:** เฉพาะเครื่องที่ไม่มี xlrd → `iv_date=None` กระทบกฎวันที่
- **วิธีแก้:** fallback pandas `pd.Timestamp('1899-12-30') + pd.to_timedelta(v, unit='D')` เมื่อ `xlrd is None`
- **หมายเหตุ:** เครื่อง golden มี xlrd → ผลเท่าเดิม ; เปลี่ยนเฉพาะ config ที่เคยพัง

---

## กลุ่ม 3 — "อย่าแตะ" (พฤติกรรมที่ golden เข้ารหัสไว้โดยตั้งใจ)

แก้ = ผลเพี้ยนจากที่รับรองไว้ → **ไม่ควรแตะถ้าไม่ได้ตั้งใจ regen golden**

| จุด | เหตุผลที่ห้ามแตะ |
|---|---|
| `rules_engine_rules_b.py:250` `r_itm008` | **ปิดอยู่** (`enabled:False`) ผลกระทบ=0 ; ถ้าจะเปิดต้อง port Decimal ก่อน + regen golden |
| `rules_engine_rules_b.py:380` `r_vat004` | เช็ค ">2 ตำแหน่ง" ยิงไม่ได้ (dead) แต่ golden เข้ารหัส "ไม่เคยฟ้อง" ไว้ |
| `rules_engine_rules_c.py:122` `r_addr005` กรุงเทพ 10xxx | false-positive ได้ แต่แก้ = ขยับ ADDR005 บนข้อมูลจริง |

---

## คำสั่งยืนยัน (รันก่อน merge ทุกครั้ง)
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02
bash run_ci.sh                                  # ต้องเขียวครบ
python3 INVARIANTS/check_invariants.py          # golden fixture = d8bcde85...
# มีข้อมูลจริง:
python3 regression_full.py . <โฟลเดอร์ 106 ไฟล์>   # ต้องได้ hash baseline เดิม
python3 verify_parallel.py <data> 8             # serial == parallel
```
