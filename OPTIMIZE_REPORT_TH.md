# 🚀 OPTIMIZE REPORT — ปุ้มปุ้ย v9.2 (รอบ OPTIMIZE)

> รายงานผลรอบ OPTIMIZE ตาม `HANDOFF_OPTIMIZE_TH.md`. ลำดับความสำคัญคงเดิม:
> **1.Stability 2.Reliability 3.Maintainability 4.Consistency 5.Predictability 6.Scalability 7.Performance.**
> Performance อยู่ท้ายโดยเจตนา — *เร็วขึ้นแต่ผลตรวจเพี้ยน = ล้มเหลว*. ทุกชิ้นติด **Hash expectation** + **Cert status**.

---

## 0. สรุปผู้บริหาร (TL;DR)

| OPT | งาน | สถานะ | Hash | Cert |
|---|---|---|---|---|
| **OPT-1** | parser hot path #1 — `_dic_int_run`/`_dic_find_seq` อ่าน M | ✅ **ทำ + CERTIFIED** | ไม่ขยับ | ✅ **35b2f7c8 ยืนยันบน 106 ไฟล์จริง** |
| **OPT-1b** | parser hot path #2 — `_label_based_amounts` normalize แถวเดียว | ✅ **ทำแล้ว** (byte-identical) | ไม่ขยับ | ⚠ NEEDS_REAL_DATA_CERT |
| **OPT-2(ก)** | re-export chain เปราะ → auto re-export | ✅ **ทำแล้ว** (surface byte-identical) | ไม่ขยับ | ⚠ NEEDS_REAL_DATA_CERT |
| OPT-3 | report styling รายเซลล์ | ⏸ defer (ปริมาณยังต่ำ) | report อาจขยับ | — |
| OPT-4 | รวม 3 taxonomy | ⏸ defer (guard พอแล้ว) | report อาจขยับ | — |
| OPT-5 | CI/infra bootstrap | ✅ พอแล้วเดิม | ไม่ขยับ | — |

**ผลรวม:** **OPT-1 ผ่าน cert จริงแล้ว** (`35b2f7c8` engine==agent==baseline บน 106 ไฟล์ py3.12) → พิสูจน์ว่า
optimize เร็วขึ้นโดยผลตรวจ **byte-identical บนข้อมูลจริง**. OPT-1b + OPT-2(ก) ทำเสร็จเชิงโค้ด + พิสูจน์
byte-identical ใน sandbox (differential/surface) แล้ว — รอ cert รอบถัดไป (วัดทีละ commit, bisectable).

---

## 1. Baseline + สถานะ cert (เชื่อตัวเลข ไม่เชื่อความจำ)

**Sandbox** (Python 3.11.15 + libs ตรึงตาม `constraints.txt`: numpy 2.2.6 / pandas 2.2.2 / openpyxl 3.1.5 /
rapidfuzz 3.10.1 / xlrd 2.0.1) + `PUOPUY_ALLOW_VERSION_MISMATCH=1`:

- **fixture golden** = `d8bcde85…` (3 บิล/1 ไฟล์) — **ไม่ขยับ** ทุก commit ✅
- **reachability** = ไม่มี floating module (parser_reexport reachable) ✅
- **run_ci.sh** = เขียวครบ (รวม guard ใหม่ OPT-1/OPT-1b/chain integrity) ✅
- **pytest** (subprocess collector) = **51 passed** (48 เดิม + 3 ใหม่) ✅
- **coverage แกน** = line ≥90% ทุกกลุ่ม (parser family รวม `parser_reexport`) ✅

**Real-data cert** (เจ้าของรันบน Python 3.12 + 106 ไฟล์ `/mnt/project`):

- **OPT-1** → `35b2f7c8c288…` **engine == agent == baseline ✅ CERTIFIED** (golden ไม่ขยับบนข้อมูลจริง)
- **report determinism** → `eeec47c6` (นิ่ง 3 รอบ) — **ผ่านเกณฑ์** (ดู §1.1)

### 1.1 บันทึก report-det: `eeec47c6` ≠ `fff69fc6` แต่ **ไม่ใช่บั๊ก**
absolute report hash ผูกกับ **เวอร์ชัน Python/openpyxl** → เปราะข้ามเครื่อง (3.11↔3.12) **โดยธรรมชาติ**:
- `test_report_det.py:10` — gate เช็คแค่ **ความนิ่งระหว่างรอบ (h1==h2)** ไม่เทียบค่าตายตัว (ออกแบบมารับเรื่องนี้)
- `P3_FOLLOWUP_TH.md:228` — ค่า absolute `fff69fc6` บน 106 ไฟล์ = "หน้าที่ผู้ใช้รันบนเครื่องตัวเอง"
- **audit golden `35b2f7c8`** (ผูกผลตรวจจริง คนละชั้นกับ report styling) = นิ่งสนิท → ผลตรวจไม่เพี้ยน ✅

---

## 2. OPT-1 — PERFORMANCE: parser hot path #1 ✅ CERTIFIED

> **Priority: สูง** (parser ≈ 88% ของเวลา ; `_dic_int_run` = hot loop อันดับ 1, 16,553 ครั้ง/~3.9s) · **Hash: ไม่ขยับ**

### Root cause (file:line)
- `parser_p0.py:35` (เดิม) — `detect_item_columns` เรียก `_dic_find_seq(df, ncols)` **ก่อน** materialize M
- `parser_p0a.py:209` (เดิม) — `_dic_int_run` ทำ `for v in df.iloc[:, c].dropna()` → สร้าง Series + dropna **ต่อคอลัมน์**
  (≈ ncols × ~799 บล็อก = 16,553 ครั้ง) — pandas indexing overhead ทบเป็นก้อนใหญ่

### Solution (เชิงกลไก ไม่ใช่เชิงตรรกะ)
ย้าย `M = df.to_numpy(dtype=object)` ขึ้นบนสุดของ `detect_item_columns` แล้วใช้ M ร่วมกับ seq-detect:
`_dic_find_seq(M, ncols)` / `_dic_int_run(M, c)` อ่าน `M[:, c]` + ข้าม `pd.isna(v)` แทน `df.iloc[:,c].dropna()`.
**per-value `int(float(str(v)))` + ช่วง 1..50 ไม่แตะแม้ตัวอักษรเดียว.**

**ทำไม byte-identical:** (1) ทีมพิสูจน์ `M[r,c] ≡ df.iat[r,c]` = 0 ต่าง บน 836 ชีต/555,176 cell (DECISIONS §OBJ-PERF);
(2) `for v in M[:,c] if not pd.isna(v)` ≡ `.dropna()` ; (3) **`test_dic_int_run_equiv.py`** เทียบกับโค้ดเดิม
(oracle อิสระ) บนคลังทรหด (วันที่/บูลีน/วิทยาศาสตร์/เลขไทย/comma/None/NaT/`inf`→OverflowError) =
**9,703 คอลัมน์ + 1,528 เฟรม, 0 ต่าง** (รวมเส้น exception).

### หลักฐาน perf + cert
- synthetic (sandbox): `detect_item_columns` **6.09× (−83.6%)**; เคส no-seq = **8.64× เร็วขึ้น** (สวนข้อกังวล
  ADR-017(b) ว่าจะ "จ่าย to_numpy เพิ่ม" — จริง ๆ to_numpy ครั้งเดียว ถูกกว่า df.iloc 15 ครั้ง/บล็อกมาก)
- **real-data cert:** `regression_full.py . /mnt/project` → `35b2f7c8` **engine==agent==baseline ✅**
- บันทึก: **ADR-022** (supersedes ADR-017(b) defer)

### Migration risk: **ต่ำ** — private helper, caller เดียว, ไม่มีเทสเรียกตรง, re-export ชื่อเดิม, ย้อนง่าย

---

## 3. OPT-1b — PERFORMANCE: parser hot path #2 ✅ ทำแล้ว

> **Priority: สูง** (`_row_label_match` = hot loop อันดับ 2, 35,661 ครั้ง/~2.5s) · **Hash: ไม่ขยับ**

### Root cause (file:line)
`parser_p1.py:_label_based_amounts` เรียก `_row_label_match(M, r, ncols, ...)` **3 ครั้ง/แถว** (TOTAL/VAT/SUBTOTAL)
ด้วย `continue` short-circuit → แต่ละครั้งสแกนทุกคอลัมน์แล้ว recompute `normalize_text(M[r,c]).lower()` ซ้ำ
≤3× ต่อเซลล์ (สำหรับแถวที่ไม่ match — ซึ่งเป็นส่วนใหญ่).

### Solution
normalize ทั้งแถว **ครั้งเดียว** เก็บเป็น `row_norm` (เซลล์ไม่ว่าง ตามลำดับคอลัมน์) แล้วเช็ก 3 label set
ด้วย `any(_label_in_text(s, L) for s in row_norm)`. `_row_label_match` เดิม **ไม่ถูกแตะ** (ยัง public/re-export).

**ทำไม byte-identical:** `normalize_text` เป็น **total** (None/NaN→`''` ; อื่น `str()` — ไม่ throw) → precompute
เต็มแถวให้ผลเท่า short-circuit เดิมทุก path (ไม่มีเส้น exception ใหม่). `any(...)` ตามลำดับคอลัมน์ ≡
`_row_label_match` (คืน True ที่ match แรก). **`test_label_amounts_equiv.py`** เทียบกับโค้ดเดิม
(ใช้ `_row_label_match` ที่ไม่ถูกแตะเป็น oracle) = **2,503 บล็อก, 0 ต่าง** (label/ยอด/อัตรา/เลข 7 vs 7.00/OCR สระหาย).

### หลักฐาน perf: synthetic ~**1.11× (−10%)** บน `_label_based_amounts` (ส่วนที่เหลือคือ `_rightmost_num` ที่ยังสแกน)
### Hash & Cert: fixture `d8bcde85` ไม่ขยับ · **⚠ NEEDS_REAL_DATA_CERT** (`35b2f7c8` ก่อน==หลัง)
### Migration risk: **ต่ำ** — แตะ caller ตัวเดียว, helper เดิมคงไว้, ย้อนง่าย

---

## 4. OPT-2(ก) — MAINTAINABILITY: auto re-export chain ✅ ทำแล้ว

> **Priority: กลาง** · **Hash: ไม่ขยับ (surface byte-identical)** · เจ้าของเลือก **(ก) แบบกระโดด** (2026-06)

### Current risk / Root cause (file:line)
chain `parser_p0a → parser_p0 → parser_p1 → parser_p2` ทำ **explicit re-export ด้วยมือ ~57–95 ชื่อ/ชั้น**
(`parser_p0.py:12-28` ฯลฯ). **B2:** ลบ/ย้าย 1 ฟังก์ชันต้นน้ำ → ImportError ทั้ง chain (ต้องแก้ 6+ จุด) =
blast radius สูง = รากงอกบั๊ก.

### Options + เหตุผลที่เลือก (ก)
| ออปชัน | ผล | ตัดสิน |
|---|---|---|
| **(ก)** auto re-export จาก `__all__` | blast radius → ~0 | ✅ **เลือก** (เจ้าของสั่ง "กระโดดถึง 9") |
| (ข) ยุบ 4 โมดูลเป็นหนึ่ง | ตัด chain | ❌ **ชน file-size gate ≤600 LOC** (รวม ~2,500 LOC) — ทำไม่ได้โดยไม่ถอดเกต |
| (ค) คง chain + guard | จับเร็วขึ้น | ทำไปก่อนแล้ว (e77d306) — เจ้าของบอก "ขยับนิดเดียว ไม่เอา" |

### Solution
เพิ่ม `parser_reexport.py` → `reexport(upstream, globals(), exclude=...)` ดึง `upstream.__all__`
เข้าสู่ namespace ปลายน้ำ โดย **bind object เดิม (`getattr`)** — **zero-star (ไม่ใช่ `import *`)** เพื่อกัน
รากปัญหา surface-leak เดิม (เช่น `annotations` รั่ว, DECISIONS:120):
- `parser_p0 ← parser_p0a` (57) / `parser_p1 ← parser_p0` (64) = **full pass-through** (EXACT_EQUAL edge)
- `parser_p2 ← parser_p1` (95) = exclude 5 ชื่อที่ p2 จัดการเอง: `Decimal`/`ROUND_HALF_UP` (import ตรงจาก
  stdlib `decimal` = object เดียวกัน) + `_RATE_MARKERS`/`_rightmost_num_has_decimal`/`_row_has_rate_marker`
  (helper ภายใน p1 ที่ไม่เคย re-export ขึ้น — คง minimal interface)
- `parser.py` (public API) **คง explicit `__all__` โดยเจตนา** — เป็น contract ที่ต้อง curate มือ ไม่ใช่ debt

**ทำไม byte-identical:** re-export bind **object เดิม** → โค้ดที่รันคือ object เดียวกันทุกตัว → golden ไม่ขยับ.
พิสูจน์ surface: re-export count 57/64/95 + `__all__` 64/100/118 **เท่าเดิมเป๊ะ** ; identity
`downstream.X is upstream.X` ครบทุกชื่อ ; `parser.__all__` เข้าถึงครบ ; fixture `d8bcde85` ไม่ขยับ.
**`test_parser_chain_integrity.py`** อัปเป็น: C1 auto-edge (216 ลิงก์ completeness + identity) +
C1b explicit-edge (parser public 70 ชื่อ) + C2 public-contract (68 ชื่อ).

### หมายเหตุ B2 (ไม่ retire):
`detect_item_columns_safe`/`_compute_col_confidence` **ไม่ retire** — **ADR-015** จงใจชุบชีวิตคืน + มีเทสตรึง
(`test_parser_extra.py`). โน้ต handoff ที่ว่า "dead → retire" ถูก ADR-015 superse แล้ว.

### Hash & Cert: fixture ไม่ขยับ · **⚠ NEEDS_REAL_DATA_CERT** (`35b2f7c8` ก่อน==หลัง) · บันทึก **ADR-023**
### Migration risk: **กลาง** — แตะ import mechanics ของ core chain ; ลดด้วย surface-snapshot + identity guard + cert แยก commit

---

## 5. OPT-3 / OPT-4 — ⏸ defer (DECIDE GATE เมื่อถึง trigger)

- **OPT-3 (report styling รายเซลล์):** `reporting_p2.build_clean_report` style ต่อเซลล์ (พอสำหรับหลักพัน-หมื่น).
  ปริมาณจริง ~3,000 บิล/วัน สบาย → **defer** จนแตะหลายแสนบิล. แตะแล้ว report hash อาจขยับ → re-verify + ดูตา.
- **OPT-4 (รวม 3 taxonomy):** taxonomy ต่างกันจริง (DOC002/VAT008) → derive จะเปลี่ยน layout = report hash ขยับ.
  มี `test_code_tables_consistency` กัน drift แล้ว → **defer** (guard พอ).

---

## 6. OPT-5 — CI/INFRA ✅ พอแล้วเดิม
- `doctor.py` ตรวจ + แนะนำ `install_hooks.sh` (advisory) — ไม่ให้ auto-mutate `.git/hooks` (ก้าวก่าย git ผู้ใช้)
- `README.md` ระบุ real cert = `regression_full.py . <106 ไฟล์>` → `35b2f7c8` ครบแล้ว

---

## 7. ⚠ NEEDS_REAL_DATA_CERT — คำสั่งให้เจ้าของรัน (OPT-1b + OPT-2(ก))

> OPT-1 cert ผ่านแล้ว ✅. รอบถัดไป cert **OPT-1b → OPT-2** แยกทีละ commit (bisectable) บน py3.12 + 106 ไฟล์:

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02

# ขั้น 1 — หลัง OPT-1b (commit 19efdf9): ต้องได้ 35b2f7c8 (engine==agent==baseline)
git checkout 19efdf9 && python3 regression_full.py . /mnt/project

# ขั้น 2 — หลัง OPT-2(ก) (commit 812a9ab): ต้องได้ 35b2f7c8 เท่าเดิม
git checkout 812a9ab && python3 regression_full.py . /mnt/project
python3 verify_parallel.py /mnt/project 8        # serial==parallel
python3 verify_report_det.py /mnt/project        # นิ่งระหว่างรอบ (ค่า absolute = env-bound, ดู §1.1)
```
- **ตรงทุกบรรทัด** → ปิด ADR-022/023 เป็น CERTIFIED → Performance + Maintainability แตะ 9 จริง
- **ต่างแม้บรรทัดเดียว** → revert เฉพาะ commit นั้น (diff เล็ก, contained) แล้วแจ้งเคสที่ต่าง
  (differential ใน sandbox บอกว่าไม่ควรเกิด — ถ้าเกิด = สัญญาณ env/version drift)

---

## 8. คะแนน (ตรงไปตรงมา — sandbox-verified vs หลัง cert)

| มิติ | ฐาน | ตอนนี้ (verified) | หลัง cert OPT-1b/OPT-2 |
|---|---|---|---|
| Stability / Reliability / Security | 9.0 | **9.0** (golden ไม่ถอย) | 9.0 |
| Test/Safety | 9.5 | **9.6** (+3 guard ถาวร) | 9.6 |
| Maintainability | 7.0 | 7.5 → **~9.0** (auto re-export, รอ cert ยืนยัน) | **~9.0** |
| Performance | 7.5 | **~8.5** (OPT-1 certified + OPT-1b) | **~9.0** |
| **รวม** | ~8.5 | **~8.8** | **~9.0 (ทุกตัว 9+)** |

## 9. PRESERVE (ไม่ถอดของดี)
ไม่แตะ: `version_gate.enforce` · `hashseed_guard` · numpy ใน version_gate · `golden_master` isolate ·
guards ทั้งหมด · advisory layer (READ-ONLY). OPT-1/1b แตะเฉพาะกลไกอ่านข้อมูล ; OPT-2 แตะเฉพาะกลไก re-export.
