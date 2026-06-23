# 🏁 ส่งมอบระบบ ปุ้มปุ้ย (Puopuy) v9.3.4 — FINAL CLOSE-OUT (อายุใช้งาน 5 ปี+)

> **เอกสารนี้ = จุดเริ่มต้นเดียวของการส่งมอบ.** เอกสารส่งมอบฉบับก่อน (`_ส่งมอบ_ระบบสมบูรณ์_v9_3_4_TH.md`, `_ส่งมอบ_v9_3_4_ADR060_20260622_TH.md`) ถูกแทนที่แล้ว (เก็บเป็นประวัติ).
> รอบปิดงานนี้ทำตาม `PROMPT_FINAL_CLOSEOUT_5YR` — **ไม่เพิ่มฟีเจอร์** · แก้เฉพาะโซนเขียว (golden ไม่ขยับ) · รวบโซนแดง/ก้ำกึ่งให้ Tor ตัดสิน.

- **วันที่ปิดงาน:** 2026-06-23 · **เวอร์ชัน:** v9.3.4 (`config_base.APP_VERSION = "9.3.4"`)
- **golden ปัจจุบัน (แหล่งจริง = ไฟล์):** corpus `08e6abfd…` (= `baseline.json._sha256`, **148 ไฟล์ / 1056 บิล**) · fixture `b5c415bb…` (3 บิล)
- **Python 3.12** + deps pin: `pandas==2.2.2 numpy==2.2.6 xlrd==2.0.1 openpyxl==3.1.5 rapidfuzz==3.10.1` · **ไม่มี pythainlp** (landmine #6)

---

## 0) สรุปผู้บริหาร (TL;DR)

รอบปิดงานนี้ทำ **forensic audit + adversarial stress + แก้โซนเขียว 4 ADR** โดย **golden ไม่ขยับ**:

| สิ่งที่ทำ | ผล |
|---|---|
| ยืนยัน baseline | corpus `08e6abfd` (จากไฟล์) · fixture `b5c415bb` (รันจริง engine==agent==baseline) ✅ |
| **ADR-080** ปิด doc-drift (`ae84d3f0`/`ba9deda0` ตกค้าง 3 surface) + ปิดช่อง guard | ✅ golden-neutral |
| **ADR-081** แก้เทสขัด golden (`test_rules_typo_branch` "5นิ้ว") + wire 9 orphan tests | ✅ golden-neutral |
| **ADR-082** เติม type annotation leaf 4 ฟังก์ชัน + wire `test_typing_leaf` | ✅ golden-neutral |
| **ADR-083** รวมเอกสารส่งมอบเป็นฉบับ FINAL เดียว | ✅ doc-only |
| Phase 2 adversarial (11 ไฟล์เพี้ยน → parse_all_files) | ✅ ROBUST — 0 crash · 0 fabricate · batch รอด |
| gate ในเครื่อง (run_ci.sh, ไม่มี corpus) | ✅ ผ่านทุก step **ยกเว้น** `[10] coverage gate` (artifact ของ tool-version — ดู §5) |

**ค้างให้ Tor ตัดสิน (โซนแดง/ก้ำกึ่ง — ไม่แตะเอง):** ดู §4.

---

## 1) สถานะ golden + การยืนยัน

```bash
python3 -c "import json;print(json.load(open('baseline.json'))['_sha256'])"
# → 08e6abfddd6cff6d2254e41998c97b5cdacb1d07edc4cbedd8ec722dda0166d9   (148/1056)
python3 -c "import json;print(json.load(open('tests/fixtures/baseline_fixture.json'))['_sha256'])"
# → b5c415bbd7bf58bac4328fec1c868325e0955f423d01e9695ba50015fc2f02eb   (3 บิล)
```

- **fixture golden ยืนยันแบบรันจริง** (`INVARIANTS/check_invariants.py` → engine==agent==baseline `b5c415bb`) ✅
- **corpus golden `08e6abfd` ยืนยันจาก "ไฟล์" (`baseline.json._sha256`)** — รอบนี้ **ไม่ได้ re-run `regression_full.py . /mnt/project`** เพราะสภาพแวดล้อม cloud **ไม่มี corpus 148 ไฟล์** (ดูข้อจำกัด §5). การแก้ทั้งหมดเป็น doc/comment/label/test/annotation → **ไม่แตะ execution path ของ golden โดยโครงสร้าง**.

---

## 2) สิ่งที่แก้ในรอบนี้ (โซนเขียว — golden-neutral · 1 ADR/แก้ · append-only)

### ADR-080 — close-out doc-drift + ปิดช่อง guard
ADR-077 (rebaseline `ae84d3f0`→`08e6abfd`) อัป "ทุก OPERATIONAL_SURFACES" แต่ **3 พื้นผิวที่อ้าง hash แต่ไม่เคยอยู่ใน guard** เลยถูกข้าม:
- `CLAUDE.md` (cold-start contract — สำคัญสุด): `ae84d3f0`→`08e6abfd` (6 จุด)
- `run_ci.sh` (comment + step [7]): `ba9deda0`→`08e6abfd` (2 จุด)
- `test_date_parse_characterization.py` (characterization label): `ae84d3f0`→`08e6abfd` (3 จุด; CASES ตรงอยู่แล้ว เทส 36/36)
- `requirements.txt` (ADR-060 note): ชี้ `08e6abfd` + คงประวัติ
- **เพิ่ม 3 ไฟล์แรกเข้า `OPERATIONAL_SURFACES`** ของ `test_golden_single_source.py` → rebaseline ครั้งหน้าลืมอัป = CI แดงทันที (ปิด root cause ถาวร)

### ADR-081 — แก้เทสขัด golden + ปิดช่อง "orphan test"
`test_rules_typo_branch.py:61` assert "5นิ้ว ต้องฟ้อง" — **ขัด golden** (ADR-075: เลข+หน่วยไทย = เขียนปกติ → ไม่ฟ้อง) และ **ขัด `test_recheck_rules_20260622.py:84`** ที่ผ่าน. ไม่ถูกจับเพราะ `run_ci.sh` ไม่รันเป็น step + `coverage_gate` กลืน exit code.
- แก้ assert → "5นิ้ว ไม่ฟ้อง" + เพิ่มเคส positive `"ABCนิ้ว"` (อังกฤษ+ไทยจริง) เก็บกิ่ง emit
- **wire 9 orphan tests** เข้า `run_ci.sh` ([3za]–[3zi]) → ความจริง run_ci.sh == pytest job ใน ci.yml

### ADR-082 — leaf typing gate
`test_typing_leaf.py` (mypy `--disallow-untyped-defs` บน leaf 4 โมดูล) fail — 4 ฟังก์ชันขาด annotation. เติม: `_df_safe(df:Any)->Any` · `_c(v:Any)->Any` (core_utils) · `_money_q->float|None` (puopuy_units) · `_be_serial->datetime|None` (puopuy_dates) + wire `test_typing_leaf` เป็น [3zj]. **golden-neutral** (`from __future__ import annotations` → ไม่ eval).

### ADR-083 — รวมเอกสารส่งมอบเป็น FINAL เดียว
สร้างเอกสารนี้ + ใส่ banner "SUPERSEDED" บนเอกสารส่งมอบเก่า 2 ฉบับ (คงเนื้อหาเป็นประวัติ ไม่ลบ).

---

## 3) ผล gate (รอบปิดงานนี้)

| gate | คำสั่ง | ผล |
|---|---|---|
| fixture golden + pin | `python3 INVARIANTS/check_invariants.py` | ✅ engine==agent==baseline `b5c415bb` + pins |
| doc-sync (ขยาย guard) | `python3 test_golden_single_source.py` | ✅ PASS (`08e6abfd` + 3 surface ใหม่, no retired) |
| reachability | `python3 test_reachability.py` | ✅ ไม่มี floating module |
| characterization date | `python3 test_date_parse_characterization.py` | ✅ 36/36 |
| full CI (ไม่มี corpus) | `bash run_ci.sh` | ✅ 91 step ผ่าน · ❌ `[10] coverage gate` เท่านั้น (artifact — §5) |
| adversarial probe | (Phase 2) | ✅ ROBUST (0 crash/fabricate, batch รอด) |
| package integrity | `python3 test_package_integrity.py` | ✅ (หลัง commit — git ls-files ครบ) |

> **corpus gate ที่ต้องรันบนเครื่อง Tor (มี /mnt/project + Python 3.12):**
> `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 python3 regression_full.py . /mnt/project baseline.json` → ต้องได้ `08e6abfd`
> `bash run_ci.sh /mnt/project` → ต้อง exit 0 (รวม parallel==serial, canary, [7][8][8c][8d])

---

## 4) 🔴 ค้างให้ Tor ตัดสิน (ไม่แตะเอง)

### 4.1 CMP004 advisory conflict (ความขัดแย้งเชิงดีไซน์ — ต้องเลือกพฤติกรรม)
`test_cmp004_notepad_visibility.py` **fail** (advisory ล้วน, ไม่กระทบ golden). อาการ: บิลที่ชื่อบริษัทเว้นวรรคเกิน → engine ฟ้อง `CMP004` ถูกต้อง **แต่** บล็อกสรุปบริษัท (`super_ultra_viewer`) โชว์ช่อง "ชื่อบจ. : ตรง" (ไม่โชว์ปัญหาเว้นวรรค).
- **root cause:** `apply_identity_honesty` (ฟีเจอร์ A1 "honesty รายผู้ขาย" ที่มาทีหลัง) override ช่องตัวตนเป็น "ตรง" เมื่อชื่อ **normalize แล้วตรง master** → กลบ CMP004 ที่ดูจาก raw (เว้นวรรค).
- **ความขัดแย้ง:** `test_honesty_per_bill.py` (ผ่าน) ต้องการ "ตรง" เมื่อตรง master ; `test_cmp004` (fail) ต้องการโชว์เว้นวรรค. **2 พฤติกรรมขัดกันบนเคสเดียวกัน** — แก้ฝั่งใดเสี่ยงพังอีกฝั่ง.
- **ทำไมไม่แก้เอง:** เป็นการตัดสินใจเชิงนโยบายรายงาน (โชว์ "ตรงตาม master" หรือ "เตือนเว้นวรรค raw" อันไหนสำคัญกว่า) + ต้องพิสูจน์ report-output บน corpus จริง (ไม่มีในรอบนี้). หลักฐาน cell-level: บิล company==master(เป๊ะ), company_raw=ชื่อ+เว้นวรรคคู่ → CMP004 ฟ้อง แต่ render_block ออก "ชื่อบจ. : ตรง".
- **คำถามขออนุมัติ:** ให้ผมแก้ `super_ultra_viewer`/`apply_identity_honesty` ให้ช่องชื่อโชว์ทั้ง "ตรง master + มีจุดเว้นวรรคต้องดู" (advisory, golden-neutral) ไหม? — **เอา / ไม่เอา / พักไว้**

### 4.2 typo whitelist (ค้างรออนุมัติ "รายคำ" จากเดิม — ยังไม่ตัดสิน)
ตัวแปรก้ำกึ่งที่ **ห้าม suppress โดยไม่เซ็นรับรายคำ**: `พุ๊ก · เจียร์ · สวิตซ์ · ปี๊ป` + เคส segmentation.
- หมายเหตุยืนยัน: **`แกลอน` = คำผิดชัดเจน** (ถูก = `แกลลอน`, ขาด ล) → SPELLING_PATTERNS จับถูกแล้ว (ไม่ต้อง whitelist).
- **คำถาม:** จะ suppress คำใดบ้าง? ต้องตอบ "รายคำ" (false negative อันตรายกว่า false positive ในระบบ audit).

### 4.3 ไฟล์ >600 LOC ใน whitelist (split ต้องอนุมัติ)
`parser_p1.py(605) · parser_p2.py(616) · rules_engine_rules_a.py(642) · validators.py(627)` — มีแผน split รอบ F4 แต่ **golden-path + de-star re-export เสี่ยงสูง** → ห้าม split เองโดยไม่อนุมัติ. (สถานะคงเดิม — ไม่ได้แตะ)

---

## 5) ⚠️ ข้อจำกัดสภาพแวดล้อม + caveat ที่ต้องรู้ (โปร่งใส)

1. **ไม่มี corpus 148 ไฟล์ใน cloud นี้** → ยืนยัน corpus golden `08e6abfd` ได้จาก **ไฟล์** เท่านั้น (ไม่ได้ re-run บนข้อมูลจริง). ทุกการแก้เป็น doc/test/annotation = golden-neutral โดยโครงสร้าง + fixture (รันจริง) ยืนยัน engine ไม่ขยับ. **Tor ควรรัน corpus gate (§3) บนเครื่องตนเพื่อปิดงาน 100%.**
2. **`[10] coverage gate` แดงในเครื่องนี้ (rules_engine branch 84.9% < 85%)** — เป็น **artifact ของ tool/Python-patch version** ไม่ใช่ regression: โค้ด engine byte-identical กับที่ ship ; เครื่อง certify ของ Tor วัดได้ 85.1% (DECISIONS.md §6) ผ่าน ; ต่างกัน ~0.2% (1–2 branch จาก 775). branch ที่ขาดเป็น guard/dispatch path (`->exit`/early-return) ไม่ใช่ logic gap. **ไม่ได้ "เติมเทสหลอก" ให้ผ่าน** (จะเป็น coverage theater) — รายงานตามจริง. รันบน env ของ Tor = เขียว.
3. **ไม่ได้รัน `make_release.py`** (ต้องมี corpus เพื่อ build→extract→verify oracle). การแพ็ก release จริง + fresh-extraction reproduce `08e6abfd` ต้องทำบนเครื่อง Tor (คำสั่ง §6).
4. cloud นี้ python3 ดีฟอลต์ = 3.11 ; รอบนี้ใช้ **venv Python 3.12.3** (ตรง pin) สำหรับทุก gate.

---

## 6) วิธีใช้ + วิธี reproduce (5 ปี)

```bash
# 0) ตั้ง env เสมอ (ขาดตัวใด hash เพี้ยน)
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1
find . -name __pycache__ -type d -exec rm -rf {} + ; find . -name '*.pyc' -delete

# 1) ติดตั้ง (offline 5 ปี) — ใช้ wheelhouse + lockfile (ADR-079)
pip install --no-index --find-links vendor/wheels --require-hashes -r requirements.lock
#   หรือ:  pip install -r requirements.txt -c constraints.txt    (ออนไลน์, Python 3.12)
#   หรือ Docker:  docker build -t pukpui .    (ดู BUILD_OFFLINE.md)

# 2) gate เต็ม (บนเครื่องที่มี corpus 148 ไฟล์)
python3 regression_full.py . /mnt/project baseline.json   # ต้องได้ 08e6abfd
python3 INVARIANTS/check_invariants.py                     # fixture b5c415bb + pins
python3 test_golden_single_source.py                      # doc-sync
python3 test_reachability.py                              # ไม่มี floating module
bash run_ci.sh /mnt/project                               # เต็ม → exit 0

# 3) รันจริง (production)
python3 main.py                                           # = ปุ้มปุ้ย_ultimate_v9_modular.py

# 4) แพ็ก release (เฉพาะเมื่อ gate เขียวครบ)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
  python3 make_release.py . /mnt/project pukpui_v9_3_4_FINAL_5YR_08e6abfd_$(date +%Y%m%d).zip
```

**กฎทอง 5 ปี:** ความจริงอยู่ที่ `baseline.json._sha256` + `run_ci.sh` ไม่ใช่ความเห็น AI. **gate เขียว = ปลอดภัย ไม่ว่าใคร/โมเดลไหนแก้.** แก้ที่ทำให้ golden ขยับ = **STOP-AND-ASK Tor** ก่อนเสมอ.

---

## 7) ไฟล์ที่แตะรอบนี้ (diff สรุป)

```
CLAUDE.md                            (ae84d3f0→08e6abfd ×6)            ADR-080
run_ci.sh                            (ba9deda0→08e6abfd ×2 + wire 10 orphan steps)  ADR-080/081/082
test_date_parse_characterization.py  (label ae84d3f0→08e6abfd ×3)      ADR-080
requirements.txt                     (ADR-060 note → ชี้ 08e6abfd)     ADR-080
test_golden_single_source.py         (+3 surface เข้า guard)           ADR-080
test_rules_typo_branch.py            (5นิ้ว assert + เคส ABCนิ้ว)       ADR-081
core_utils.py / puopuy_units.py / puopuy_dates.py  (annotation 4 จุด)  ADR-082
_ส่งมอบ_*.md (เก่า 2 ฉบับ + FINAL ใหม่)                                ADR-083
INVARIANTS/DECISIONS.md              (+ADR-080..083, append-only)
```
**ไม่มีฟีเจอร์ใหม่ · golden ไม่ขยับ · ไม่มี ADR เก่าถูกลบ/แก้.**
