# ส่งมอบรอบ 2 — BUGHUNT ทุกระดับทั้งระบบ + แก้ (ADR-171..175) · 2026-07-02

> คำสั่งเจ้าของ: "ไฟล์ที่ส่งมาทางแชทนี้ ถ้ามีบั๊ก ร้าย/กลาง/ต่ำ ครัช ร้าย/กลาง/ต่ำ ทำการแก้ไข
> และส่งระบบที่สมบูรณ์กลับทางแชทนี้เท่านั้น" — ทำต่อจากรอบแรก (ADR-167..170, ดู `_ส่งมอบ_FIX3BUGS_ADR167-170_TH.md`)
> วิธีล่า: ทีมสำรวจอิสระ 4 ทีม (parser / rules engine / ชั้นรายงาน / orchestration) — **ทุกบั๊กต้อง
> reproduce ได้จริงก่อนรายงาน** แล้วคัดกรอง: แก้เฉพาะที่ golden ไม่ขยับ + gate เขียวครบ

## สิ่งที่แก้ (พิสูจน์ครบทุกตัว · fixture `ad0c9dad` คงเดิมทุก commit)

### ระดับร้าย (ครัชฆ่าทั้ง run)
| # | บั๊ก | แก้ที่ | ADR |
|---|---|---|---|
| 1 | **Windows console ไม่ใช่ UTF-8 (redirect/pipe/Task Scheduler) → ตายตั้งแต่ import** — banner version-gate มี emoji พิมพ์ตอน import ก่อนการ์ด ADR-063 ทำงาน; `main.py` (ทางเข้าหลัก) ไม่มีการ์ดเลย | `main.py` (reconfigure ก่อน import + ห่อ KeyboardInterrupt/Exception), `version_gate.py` (print encode-safe) — พิสูจน์: cp874 + redirect รันจบได้รายงานครบ (เดิม exit 1 ตั้งแต่ import) | 171 |
| 2 | **display 2 ตัวใน main ไม่ถูกห่อ** — บิลเพี้ยน (วันที่/เงินเป็น str, issues=None) ครัชหลังตรวจเสร็จ **ก่อนได้รายงานใด ๆ** | ห่อ try/except ใน main (หลัก ADR-166) + เสริมเกราะใน `reporting_p0.py` (or [] ×28 จุด, `_fin0`, `_bill_date_key`, str company) | 173 |
| 3 | **ชื่อชีตเป็น Unicode digit แปลก ('²','①') ชีตเดียว → การตรวจลำดับ/ซ้ำ IV ดับเงียบทั้งรอบ + DOC001 crosscheck หายทั้งรอบ** (`isdigit()` ผ่านแต่ `int()` ครัช → bumper ปิดทั้งคลาส) — false-negative machine | `.isdecimal()` 4 จุด (`validators.py` ×2, `rules_engine_rules_a.py` ×2) — เลขไทย/ASCII เดิมเป๊ะ | 172 |
| 4 | **ReDoS ใน regex คัดเลือก IV** — เซลล์เดียวที่มีเลขติดกันยาวชนตัวอักษร: 28 หลัก ~10 วิ, 40 หลัก >100 วิ, ยาวกว่า = **ค้างข้ามคืนไม่มี error** | `parser_p1.py`/`parser_p0.py`: `{0,10}` + บล็อกเลข ≥20 หลักแทน placeholder ก่อนสแกน — fuzz 200k เคส match ตรงเดิม 100%, 5,000 หลัก = 0.0000s | 174 |

### ระดับกลาง
| # | บั๊ก | แก้ที่ | ADR |
|---|---|---|---|
| 5 | FULL mode (`export_excel`) ไม่มีเกราะแบบ ADR-168 → workbook ทั้งไฟล์หายเงียบกับบิลเพี้ยน 4 คลาส | pre-pass twin + `_get_p`/`bill_company_label`/`sort_bills_by_date` guard | 173 |
| 6 | `super_ultra_viewer` ครัชกับบิลเพี้ยน → company_summary .txt+.xlsx หายทั้งชุด + **NaN โผล่เป็น "ยอด : nan บาท" ในไฟล์ส่งลูกค้า** | ขยาย gate ADR-153 + `_sv_num` ในผลรวมเงิน | 173 |
| 7 | 29 ก.พ. ปี พ.ศ. อธิกสุรทิน (เช่น 2568) ในชีต TOR → ครัช → **บิลทั้งชีตหาย** (twin ของ [M1] ที่ตกหล่น) | `parser_p2.py _tor_try_date`: try/except + เก็บ `_bad_date` ให้ DT006 | 174 |
| 8 | สรุปท้ายรัน "มี N ไฟล์อ่านไม่สำเร็จ" **นับขาด** เคสเปิดไฟล์ไม่ได้ (รวมเคส Excel lock ของ ADR-167!) | `parse_all_files` รวม SYS001 File Open Failure เข้าสรุป | 174 |
| 9 | last-resort IV หยิบ "ปีเปล่า ๆ" (2569) / รหัสไปรษณีย์ เป็นเลขที่เอกสาร | `parser_guards.py`: ตัด token ปี + zip ในแถวที่อยู่ (เคสจริง TNT '01954' ยังทำงาน) | 174 |
| 10 | สำเนาชื่อซ้ำที่ SYS004 ข้าม **ไม่เคยถูกย้าย** → รอบถัดไปถูกตรวจซ้ำเงียบ = ยอดนับซ้ำข้ามรอบ (เคสจริง 11.06.69) | เก็บเข้า `ตรวจแล้ว_*/สำเนาซ้ำ_ข้าม/` — พิสูจน์ AUTO 2 รอบจริง: รอบ 2 พบ 0 ไฟล์ | 174 |
| 11 | master ที่มือแก้ให้ `address_parts` ผิด type → ADDR001/002/003 **ดับเงียบทุกบิลของผู้ขายนั้น** | type-gate ใน `rules_engine_rules_a.py` ×2 | 172 |
| 12 | `iv_date` ชนิดผิด (str/serial/NaT) → กฎวันที่ 3 ตัวข้ามเงียบรายบิล (GAP-A ตกหล่น) | type-gate ใน `rules_engine.py` | 172 |

### ระดับต่ำ
| # | บั๊ก | แก้ที่ | ADR |
|---|---|---|---|
| 13 | ดัชนี cross-bill 2 ตัวไม่ถูกล้างโดย `reset_run_state` (RAM ค้าง + ดัชนีค้างเมื่อแก้ list in-place) | `pukpui_modular_funcs.py` | 172 |
| 14 | vendor report ครัชกับ NaT/company ผิด type | `agents/vendor_report_base.py` | 173 |
| 15 | `summary_stats` ครัชกับ issues=None (พี่น้อง ADR-133 ที่ตกหล่น) | `issue_consolidator.py` | 173 |
| 16 | sidecar `audit_system_issues.jsonl` — record เสีย 1 ตัวทำไฟล์หายทั้งไฟล์ (truncate ค้าง) | `diagnostics.py`: try ต่อ record | 173 |
| 17 | `r_doc001` ครัชรายบิลกับชีต digit แปลก | รวมใน isdecimal (ข้อ 3) | 172 |

## รายงานอย่างเดียว — ไม่แก้ (ต้องการคำตัดสิน Tor / corpus จริง)

1. **merge_continuation_bills คำนวณ subtotal ใหม่จาก qty×price ทิ้งค่า amount จริง** (parser_p0a.py:119-132)
   — เคสส่วนลด/บรรทัดบริการทำยอด "เกินจริง/ต่ำกว่าจริง" ได้ (probe synthetic ยืนยัน) แต่โค้ดส่วนนี้อยู่ใต้
   **FREEZE ตามคำสั่งเจ้าของ** (DECISIONS.md: "รื้อเฉพาะเมื่อมีเคสจริงพัง") + แก้แล้ว golden อาจขยับ
   → ต้อง STOP-AND-ASK พร้อม simulate delta บน corpus จริงก่อน
2. **Formula injection ในรายงาน**: ชื่อสินค้า/ข้อความขึ้นต้น `=` กลายเป็นสูตรจริง (พิสูจน์: `=HYPERLINK(...)`
   เป็น live formula ใน 3 รายงาน) — การแก้เปลี่ยน byte รายงานเฉพาะเซลล์แบบนี้ (fixture ไม่มีเลย แต่ corpus
   ตรวจจากที่นี่ไม่ได้) + มี trade-off การแสดงผล → เสนอตัดสินใจ: สแกน corpus ก่อน (`ขึ้นต้น =`) แล้วเลือกวิธี
3. **ข้อสังเกตสถาปัตยกรรม**: กฎ ~19 ตัวห่อทั้งตัวด้วย `except: return []` (เงียบสนิท ไม่มี SYS-*) —
   fuzz ไม่พบ input จริงที่ครัชในนั้น จึงไม่แตะ แต่ควรรู้ไว้

## หลักฐานความถูกต้อง (ทุก commit)

- fixture oracle `regression_full` = `ad0c9dad…` เป๊ะ (engine==agent==baseline) หลังทุกกลุ่มแก้
- lock tests 8 ตัว + parser suite + report suite เขียวครบ · `REPORT_DET_HASH` ไม่ขยับ · doc-sync ผ่าน
- CI เต็มชุด fixture: exit 0 "✅ CI ผ่านทั้งหมด"
- ADR append-only ครบ: ADR-171..175 (ledger รวม 79 entries) — ไม่มี entry เก่าถูกแก้
- deps pin ไม่ขยับ · ไม่แตะ THAI_TYPO_PATTERNS · fixture ไม่ถูก rebaseline

## สิ่งที่ยังต้องทำบนเครื่องเจ้าของ (เหมือนรอบแรก)

รัน batch จริง → ยืนยัน 3 บั๊กเดิมปิด → sweep §5.4 → **rebaseline corpus** (golden ใหม่จะต่างจาก
f05358aa เพราะมีไฟล์ มิ.ย. เพิ่ม — ตามขั้นตอนใน `_ส่งมอบ_FIX3BUGS_ADR167-170_TH.md`)

## หมายเหตุการส่งมอบ

- ส่งมอบทาง**แชทเท่านั้น**ตามคำสั่ง (zip แพ็กด้วย Python zipfile)
- branch `claude/thai-instruction-35mzcb` ที่เคย push ขึ้น GitHub: **สั่งลบแล้วแต่ระบบปฏิเสธ (HTTP 403 —
  สภาพแวดล้อมนี้ push ได้อย่างเดียว ลบไม่ได้)** → ลบเองได้ที่หน้า GitHub repo → Branches → ถังขยะ
  หรือ `git push origin --delete claude/thai-instruction-35mzcb` จากเครื่องที่มีสิทธิ์
