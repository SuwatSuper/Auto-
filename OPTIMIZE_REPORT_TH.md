# 🚀 OPTIMIZE REPORT — ปุ้มปุ้ย v9.2 (รอบ OPTIMIZE)

> รายงานผลรอบ OPTIMIZE ตาม `HANDOFF_OPTIMIZE_TH.md`. ลำดับความสำคัญคงเดิม:
> **1.Stability 2.Reliability 3.Maintainability 4.Consistency 5.Predictability 6.Scalability 7.Performance.**
> Performance อยู่ท้ายโดยเจตนา — *เร็วขึ้นแต่ผลตรวจเพี้ยน = ล้มเหลว*. ทุกชิ้นติด **Hash expectation** + **Cert status**.

---

## 0. สรุปผู้บริหาร (TL;DR)

| OPT | งาน | สถานะ | Hash | Cert |
|---|---|---|---|---|
| **OPT-1** | parser hot path (`_dic_int_run`/`_dic_find_seq` อ่าน M) | ✅ **ทำแล้ว** (sandbox) | ไม่ขยับ (พิสูจน์ differential) | ⚠ NEEDS_REAL_DATA_CERT |
| OPT-2 | re-export chain เปราะ | ⏸ **DECIDE GATE** (รออนุมัติ — เสี่ยงสูง) | ไม่ขยับ (คาด) | — |
| OPT-3 | report styling รายเซลล์ | ⏸ defer (ปริมาณยังต่ำ) | report อาจขยับ | — |
| OPT-4 | รวม 3 taxonomy | ⏸ defer (guard พอแล้ว) | report อาจขยับ | — |
| OPT-5 | CI/infra bootstrap | ✅ **พอแล้วเดิม** (doctor advise + README มี) | ไม่ขยับ | — |

**ผลรวม:** OPT-1 (priority สูงสุด, parser = 88% ของเวลา) ทำเสร็จในเชิงโค้ด+พิสูจน์ byte-identical แล้ว
รอเพียง **เจ้าของรัน cert บน 106 ไฟล์จริง (py3.12)** เพื่อปิดวงจร R3/R4. OPT-2/3/4 เป็นงานเสี่ยง/แตะ
report hash → เสนอเป็น **DECIDE GATE** (ตามกฎ handoff: ขออนุมัติก่อนแตะ core parser/report).

---

## 1. Baseline ที่ยืนยันแล้ว (before — เชื่อตัวเลข ไม่เชื่อความจำ)

รันบน sandbox (**Python 3.11.15** + libs ตรึงตาม `constraints.txt`: numpy 2.2.6 / pandas 2.2.2 /
openpyxl 3.1.5 / rapidfuzz 3.10.1 / xlrd 2.0.1) + `PUOPUY_ALLOW_VERSION_MISMATCH=1`:

- **fixture golden** = `d8bcde8555034a203f80d2a596c42ea57b2f1a39ce67003f5629cea03185b07c` (3 บิล/1 ไฟล์) ✅
- **reachability** = ไม่มี floating module (90 reachable) ✅
- **run_ci.sh** = 53 ด่านเขียวครบ (package integrity ผ่านเมื่อไฟล์ถูก track) ✅
- **pytest** (subprocess collector) = **49 passed** (48 เดิม + 1 ใหม่ OPT-1) ✅
- **coverage แกน** = line 95.1% / branch 86.6% (เกต line ≥90% ผ่านทุกกลุ่ม) ✅

### ⚠ ข้อจำกัด sandbox (เปิดเผยตรง ๆ — สำคัญสุด)
สภาพแวดล้อมนี้ **ไม่มี `/mnt/project` (106 ไฟล์จริง/834 บิล)** และเป็น **Python 3.11 ไม่ใช่ 3.12**.
→ hash-gate ที่รันได้จริง = **fixture `d8bcde85`** เท่านั้น. golden ทางการ `35b2f7c8` (= `baseline.json._sha256`)
**วัดที่นี่ไม่ได้**. ดังนั้นทุกงานที่อาจกระทบ golden ปิดท้ายด้วย **⚠ NEEDS_REAL_DATA_CERT** + คำสั่งให้เจ้าของรัน (§6).

---

## 2. OPT-1 — PERFORMANCE: parser hot path ✅ ทำแล้ว (byte-identical)

> **Priority: สูง** (parser = ~88% ของเวลา ; `_dic_int_run` = hot loop อันดับ 1) · **Hash expectation: ไม่ขยับ**

### Current risk
`parse_all_files` ครอง ~88% ของเวลา (PERF_BASELINE). ในนั้น `_dic_int_run` ถูกเรียก **16,553 ครั้ง/106 ไฟล์
(~3.9s)** — สแกนรันตัวเลขต่อคอลัมน์เพื่อหา "คอลัมน์ลำดับสินค้า". เป็น hot loop ที่กินเวลาจริง แต่
"แตะไม่ได้ง่าย" เพราะอยู่ในเส้น golden (byte-sensitive).

### Root cause (file:line)
- `parser_p0.py:35` — `detect_item_columns` เรียก `seq_col = _dic_find_seq(df, ncols)` **ก่อน** materialize M
- `parser_p0a.py:274` — `_dic_find_seq(df, ncols)` วน `for c in range(ncols): _dic_int_run(df, c)`
- `parser_p0a.py:209` — `_dic_int_run` ทำ `for v in df.iloc[:, c].dropna():` → สร้าง Series + dropna **ต่อคอลัมน์**
  (≈ ncols ครั้ง/บล็อก × ~799 บล็อก = 16,553 ครั้ง). pandas indexing overhead ทบกันเป็นก้อนใหญ่.
- `parser_p0.py:38` (เดิม) — `M = df.to_numpy(dtype=object)` materialize **หลัง** seq-detect แล้ว (ของ `_dic_*` ที่เหลือ)

### Long-term impact (ถ้าไม่แก้)
parse ครองเวลาเสมอ → ประสบการณ์ผู้ใช้ช้าลงตามจำนวนไฟล์/บิล. งานนี้เป็น hotspot อันดับ 1 ของ single-core path
(ซึ่งเป็น path ที่ golden/regression ใช้). ปล่อยไว้ = perf ค้างที่ ~7.5 ตามเป้า handoff.

### Solution (เชิงกลไก ไม่ใช่เชิงตรรกะ)
ย้าย `M = df.to_numpy(dtype=object)` ขึ้น **บนสุด** ของ `detect_item_columns` แล้วใช้ M ร่วมกันทั้ง seq-detect
และ `_dic_*` ที่เหลือ:
- `parser_p0.py:detect_item_columns` — materialize M ก่อน `_dic_find_seq(M, ncols)`
- `parser_p0a.py:_dic_find_seq(M, ncols)` / `_dic_int_run(M, c)` — อ่าน `M[:, c]` + ข้าม `pd.isna(v)`
  แทน `df.iloc[:, c].dropna()`. **per-value `int(float(str(v)))` + ช่วง 1..50 ไม่แตะแม้แต่ตัวอักษรเดียว.**

**ทำไม byte-identical:**
1. ทีมพิสูจน์แล้วว่า `M[r,c] ≡ df.iat[r,c]` เชิงพฤติกรรม (isna/str/เป็นตัวเลข/float) = **0 ต่าง บน 836 ชีต/555,176 cell**
   (DECISIONS §OBJ-PERF step4, บรรทัด 250-252) — M คือตัวเดียวกับที่ `_dic_*` ใช้อยู่แล้ว.
2. `for v in M[:,c] if not pd.isna(v)` ให้ค่าและลำดับเท่ากับ `df.iloc[:,c].dropna()` (ข้าม null ตามแถวเหมือนกัน).
3. **`test_dic_int_run_equiv.py`** (ใหม่) — เก็บโค้ดเดิมไว้เป็น oracle อิสระแล้วเทียบกับของจริง บนคลังอินพุตทรหด
   (วันที่/บูลีน/วิทยาศาสตร์/เลขไทย/comma/None/NaT/ทศนิยมยาว/ค่าใกล้จำนวนเต็ม/inf):
   **9,703 คอลัมน์ + 1,528 เฟรม = 0 ต่าง** รวม "เส้น exception" (เช่น `'inf'` → `OverflowError` ที่
   `except (ValueError,TypeError)` เดิม **ไม่จับ** → โค้ดเดิม crash เหมือนกัน → optimize โปร่งใสแม้ตอน error).

### หลักฐาน perf (synthetic — sandbox py3.11, ไม่ใช่ 106 ไฟล์)
จำลอง 800 บล็อกบิล (85% มี seq / 15% ไม่มี seq), เทียบ `detect_item_columns` เดิม vs ใหม่:
- **6.09× (−83.6%)** ต่อ pass (1181ms → 194ms)
- เคส **no-seq อย่างเดียว = 8.64× เร็วขึ้น** — สวนข้อกังวล ADR-017(b) ที่ว่า "ชีตไม่มี seq จะจ่าย to_numpy เพิ่ม":
  ในความจริง `to_numpy` ครั้งเดียว ถูกกว่าการ `df.iloc[:,c].dropna()` ~15 ครั้ง/บล็อกมาก → **ไม่มี tradeoff ติดลบ**.

> ⚠️ ตัวเลขสัมบูรณ์ขึ้นกับเครื่อง/ข้อมูล — บน 106 ไฟล์จริง (py3.12) อาจต่างในเชิงขนาด แต่กลไก
> ("แทน N pandas-slice ด้วย 1 vectorized materialize") เป็นการลด overhead ที่คงทน. **ตัวเลขจริงต้อง cert (§6).**

### Migration risk
**ต่ำ–กลาง.** การเปลี่ยนถูกจำกัดวง: `_dic_find_seq`/`_dic_int_run` เป็น private helper ที่มี caller เดียว
(`detect_item_columns`) และ **ไม่มีเทสเรียกตรง** (เทสเรียก `detect_item_columns`/`detect_item_columns_safe`/
`_dic_pick_qty_price(M,...)` ซึ่งคง contract เดิม). re-export chain ไม่เปลี่ยน (ชื่อเดิม) → ไม่มี ImportError.
ย้อนกลับง่าย (diff เล็ก, contained) + `test_dic_int_run_equiv.py` เป็น additive.

### Hash expectation & Cert status
- fixture golden `d8bcde85…` → **ยืนยันแล้วว่าไม่ขยับ** (รันซ้ำหลังแก้)
- audit golden `35b2f7c8…` (106 ไฟล์) → **คาดว่าไม่ขยับ** (เพราะ M≡iat + differential 0 ต่าง) → **⚠ NEEDS_REAL_DATA_CERT**
- บันทึกการตัดสินใจ: **ADR-022** (supersedes ADR-017(b) defer — ดู `INVARIANTS/DECISIONS.md`)

### ของพ่วง (future, ยังไม่ทำ — note ไว้)
`parser_p2._parse_block` (บรรทัด 203-205) เรียก `detect_item_columns(block_df)` (materialize M) แล้วเรียก
`_pb_extract_items(result, block_df, cols)` ต่อ ซึ่งน่าจะ materialize M ของ block_df ซ้ำ → มี **double-materialize**.
การ thread M ออกจาก `detect_item_columns` จะลดซ้ำได้อีก แต่ **เปลี่ยน return signature (6-tuple)** = test-facing +
ใกล้ golden → **เสี่ยงสูงกว่า ROI** ตอนนี้ → defer จนหลัง cert OPT-1.

---

## 3. OPT-2 — MAINTAINABILITY: re-export chain เปราะ ⏸ DECIDE GATE (รออนุมัติ)

> **Priority: กลาง** · **Hash: ไม่ขยับ (คาด)** · handoff สั่งชัด: *"ต้องเสนอ options+tradeoffs ขออนุมัติก่อนแตะ"*

### Current risk / Root cause (file:line)
chain `parser_p0a → parser_p0 → parser_p1 → parser_p2 → parser.py(__all__)` ทำ **explicit re-export**
โยงสัญลักษณ์ข้ามชั้น (เช่น `parser_p0.py:12-28` import 40+ ชื่อจาก parser_p0a เพื่อส่งต่อ).
**ความเปราะ (B2 พิสูจน์):** ลบ/ย้าย 1 ฟังก์ชันใน parser_p0 → ImportError ทันทีจาก parser_p1/p2
(ต้องแก้ 6+ จุดประสานกัน). blast radius สูง = บั๊กง่ายเวลาเพิ่ม/ลบ/ย้ายฟังก์ชัน parser.

### Options + tradeoffs (ต้องเลือกก่อนแตะ)
| ออปชัน | วิธี | ข้อดี | ความเสี่ยง |
|---|---|---|---|
| **(ก)** `__all__`-driven re-export | derive รายการ re-export อัตโนมัติจาก `__all__` (เหมือน parser_p0a:403 ที่ auto-export อยู่แล้ว) | ลด explicit list ที่ต้อง sync มือ | ต้องคุม import order ; เสี่ยง shadow ชื่อ |
| **(ข)** ยุบ parser_p0a/p0/p1/p2 เป็นโมดูลเดียว | รวมกลับ | ตัด chain ทิ้งทั้งหมด | **ชน file-size gate ≤600 LOC** (`test_file_size_ceiling.py`) ; coverage map เปลี่ยน ; เสี่ยงสุด |
| **(ค)** คง chain + เพิ่ม guard | เพิ่ม test ที่ assert chain integrity (ทุกชื่อใน `__all__` import ได้ครบ) | เสี่ยงต่ำสุด, ไม่แตะ logic | ไม่ลดความเปราะจริง แค่จับเร็วขึ้น |

**ข้อเสนอแนะ (ของผม):** ทำ **(ค) ก่อน** (guard ราคาถูก จับ regression chain ได้ทันที, hash ไม่ขยับแน่นอน) →
ค่อยพิจารณา (ก) ภายหลัง. **(ข) ไม่แนะนำ** (ชน gate + เสี่ยงสุด, ROI ต่ำ). **รออนุมัติก่อนลงมือ.**
- **พ่วง B2:** เมื่อ chain จัดระเบียบแล้ว ค่อย retire `detect_item_columns_safe`/`_compute_col_confidence`
  (`parser_p0.py:83,54` — dead additive, ไม่มี call site production) ได้ปลอดภัย.

---

## 4. OPT-3 — SCALABILITY: report styling รายเซลล์ ⏸ defer

> **Priority: ต่ำ** · **Hash: report `fff69fc6` อาจขยับ** (audit `35b2f7c8` ไม่ขยับ — คนละชั้น)

- **Current:** `reporting_p2.build_clean_report` ใส่ style ต่อเซลล์ (พอสำหรับหลักพัน-หมื่นบิล ; หลายแสนจะช้า/แรมโต).
- **Approach (ตามโน้ตเดิม):** (1) แบ่งไฟล์ตามงวด/บริษัท (ไม่แตะ builder, ปลอดสุด) → (2) xlsxwriter constant_memory
  → (3) batch styling. ทุกออปชันต้องผ่าน `verify_report_det.py` (report hash) + **ดูหน้าตารายงานด้วยตา** (style ไม่อยู่ใน hash).
- **Decision ปัจจุบัน: defer** — ปริมาณจริง ~3,000 บิล/วัน สบาย. ทำเมื่อแตะหลายแสนบิล + ยอม re-verify report hash. → **DECIDE GATE เมื่อถึงเวลา**

---

## 5. OPT-4 — CONSISTENCY: รวม 3 taxonomy ⏸ defer

> **Priority: ต่ำ** · **Hash: report อาจขยับ**

- **Current:** `code_labels.MAP` / `config.FIELD_CODES` / `vendor_report_base.FIELD_LAYOUT` ใช้กลุ่มต่างกัน
  (มี guard `test_code_tables_consistency` กัน drift แล้ว).
- **ปัญหา:** taxonomy ต่างกัน *จริง* (DOC002/VAT008 จัดกลุ่มไม่ตรงข้ามตาราง) → derive จาก `code_registry.py`
  ตัวเดียวจะ **เปลี่ยน layout = report hash ขยับ**.
- **Decision ปัจจุบัน: defer** — guard พอแล้ว (drift จับได้). ทำเมื่อมีเวลา + ยอม re-verify report hash. → **DECIDE GATE**

---

## 6. OPT-5 — CI/INFRA ✅ พอแล้วเดิม (ไม่ต้องแก้)

- **pre-commit bootstrap:** `doctor.py:117-127` ตรวจ hook + แนะนำ `bash INVARIANTS/install_hooks.sh` อยู่แล้ว
  (advisory). **ไม่แนะนำให้ doctor auto-เขียน `.git/hooks` เอง** — การ mutate git config ของผู้ใช้โดยไม่ขออนุญาต
  เป็นพฤติกรรมที่ก้าวก่าย ; แบบ advisory ปัจจุบันปลอดภัยกว่าและถูกต้องแล้ว.
- **real cert นอก CI:** `README.md` (บรรทัด 32/41/51/73) ระบุชัดแล้วว่า real cert = `regression_full.py . <106 ไฟล์>`
  ต้องได้ `35b2f7c8`. → **ไม่ต้องเพิ่มอะไร** (OPT-5 ถือว่าครบโดยสถานะเดิม).

---

## 7. ⚠ NEEDS_REAL_DATA_CERT — คำสั่งให้เจ้าของรัน (ปิดวงจร R3/R4 ของ OPT-1)

รันบนเครื่องจริง **Python 3.12 + 106 ไฟล์ `/mnt/project`** (libs ตาม `constraints.txt`). ทุกบรรทัดต้องได้ค่าตามนี้:

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02

# 1) audit golden ก่อน==หลัง OPT-1 — ต้องได้ 35b2f7c8 ทั้ง engine==agent==baseline
python3 regression_full.py . /mnt/project
#    → 35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba

# 2) serial == parallel (OPT-1 อยู่ใน parse core ที่ทั้งสอง path ใช้ร่วม)
python3 verify_parallel.py /mnt/project 8

# 3) report determinism — ต้องได้ fff69fc6 (OPT-1 ไม่แตะ builder → ควรไม่ขยับ)
python3 verify_report_det.py /mnt/project

# 4) (ทางเลือก) วัด perf จริง ก่อน/หลัง เพื่อบันทึกตัวเลขลง PERF_BASELINE.md
python3 profile_baseline.py /mnt/project
```

- **ถ้า hash ตรงทุกบรรทัด** → OPT-1 ผ่าน cert สมบูรณ์ (Stability ไม่ถอย) → ปิด ADR-022 เป็น CERTIFIED.
- **ถ้า hash ต่างแม้บรรทัดเดียว** → OPT-1 เปลี่ยนพฤติกรรม (ไม่คาดหมาย) → **revert ทันที** (diff เล็ก, contained)
  แล้วแจ้งเคสที่ต่างเพื่อสอบสวน (differential 9,703+1,528 บอกว่าไม่ควรเกิด — ถ้าเกิดคือสัญญาณ env/version drift).

---

## 8. กฎที่รักษาไว้ครบ (PRESERVE — ไม่ถอดของดี)
ยืนยันว่ารอบนี้ **ไม่แตะ**: `version_gate.enforce` · `hashseed_guard` · numpy ใน version_gate · `golden_master` isolate ·
guards ทั้งหมด (reachability/report-det/reset/package/merged-cell/code-table/field-codes/golden-single-source) ·
advisory layer (ultra_agent/lenses/vendor_report) = READ-ONLY. OPT-1 แตะเฉพาะกลไกอ่านข้อมูลใน `detect_item_columns`.

## 9. Next steps (สำหรับเจ้าของ)
1. **รัน §7 บน 106 ไฟล์ (py3.12)** → ยืนยัน `35b2f7c8`/`fff69fc6` ก่อน==หลัง → ปิด cert OPT-1.
2. ตัดสิน **OPT-2 DECIDE GATE** (แนะนำออปชัน (ค) guard ก่อน) — แล้วผมลงมือต่อได้.
3. OPT-3/4 ทำเมื่อถึง trigger (ปริมาณบิลโต / ยอมขยับ report hash).
