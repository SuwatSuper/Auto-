# เซสชันยืนยันฐาน + นำเข้าโปรเจกต์เข้า repo — pukpui v9.3.4 (2026-06-22)

> วันที่: 2026-06-22 · โหมด: **LOCKED** (อ่าน/สืบ/ยืนยัน — ไม่แก้ golden) · ผู้ทำ: Claude Code (remote/cloud)
> ขอบเขต: ตั้งระบบลง repo ว่าง (`Auto-`, branch `claude/wizardly-dirac-74wtga`) + รัน session-start checklist ตาม `CLAUDE.md`

---

## 0) สรุปผู้บริหาร

- นำแพ็ก `pukpui_v9_3_4` (จาก zip ที่เจ้าของอัปโหลด) เข้า repo โดย **แตกด้วย Python `zipfile` เท่านั้น**
  (กฎ landmine — `unzip` ทำชื่อไฟล์ไทยเพี้ยน). zip ที่ได้มา **ไม่ตั้ง UTF-8 flag** → กู้ชื่อไทยด้วย `cp437→utf-8`
  ครบ 8 ไฟล์ (เช่น `ปุ้มปุ้ย_ultimate_v9_modular.py`, `_ส่งมอบ_ระบบสมบูรณ์_v9_3_4_TH.md`).
- เพิ่ม `CLAUDE.md` (สัญญากำกับที่เจ้าของให้มา — เดิมแพ็กไม่มีไฟล์นี้).
- **ไม่แตะโค้ด engine/parser/rules/validators/baseline ใด ๆ** — golden-neutral โดยสมบูรณ์ (เพิ่มเฉพาะ "ไฟล์โปรเจกต์ที่พิสูจน์แล้ว + เอกสาร 2 ฉบับ").
- ยืนยันฐานเท่าที่สภาพแวดล้อม cloud ทำได้ → **ผ่านทุก oracle ที่ reproduce ได้ในที่นี้** (ดู §2). ค่า hash ทุกตัวตรงกับที่รอบ 2026-06-21 ยืนยันไว้เป๊ะ.

---

## 1) สภาพแวดล้อมที่รัน (สำคัญ — ต่างจาก runtime ทางการ)

| ของ | ที่ล็อก (ทางการ) | ในเซสชันนี้ | หมายเหตุ |
|---|---|---|---|
| Python | **3.12.x** | **3.11.15** | minor ต่าง → `version_gate` FAIL ถูกต้อง ; ผ่อนด้วย `PUOPUY_ALLOW_VERSION_MISMATCH=1` |
| pandas | 2.2.2 | **2.2.2** ✅ | ติดตั้งตรง pin |
| numpy | 2.2.6 | **2.2.6** ✅ | ติดตั้งตรง pin |
| openpyxl | 3.1.5 | **3.1.5** ✅ | ติดตั้งตรง pin |
| rapidfuzz | 3.10.1 | **3.10.1** ✅ | ติดตั้งตรง pin |
| xlrd | 2.0.1 | **2.0.1** ✅ | ติดตั้งตรง pin |
| pythainlp | (ไม่ติดตั้ง) | **ไม่ติดตั้ง** ✅ | ตรง landmine #6 — ห้ามติดตั้ง (golden 51 typo มาจาก `CONSTRUCTION_DICT`) |
| corpus `/mnt/project` | 148 ไฟล์ / 1056 บิล | **ไม่มีในคอนเทนเนอร์** | → golden ทางการ `ae84d3f0` **reproduce ที่นี่ไม่ได้** (ดู §3) |

> env determinism ที่ตั้งทุกครั้ง: `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1`.

---

## 2) Oracle ที่ reproduce ได้ในเซสชันนี้ — ผ่านทั้งหมด ✅

| oracle | ค่าที่ได้ | คาดหวัง | ผล |
|---|---|---|---|
| **fixture golden** (engine==agent==baseline, 3 บิล) | `b5c415bb…` | `b5c415bb…` | ✅ ตรงเป๊ะ |
| **real_cases digest** (engine snapshot, 3 ไฟล์ / 15 บิล) | `95852c68…` | `95852c68…` | ✅ ตรงเป๊ะ |
| **check_invariants.py** (fixture + PIN LOGIC + PIN LENSES + VAT002) | 4/4 | 4/4 | ✅ |
| **run_ci.sh** (ไม่ใส่ data dir) | **79 PASS / 0 FAIL / 6 SKIP** (exit 0) | — | ✅ |
| pin behavioral 2026-06-21 `[3x14d]` (P-MED2 / V-F3) | ผ่าน | ผ่าน | ✅ |

- 6 SKIP = ตามคาดในสภาพแวดล้อมนี้: เครื่องมือ QA ไม่ได้ติดตั้ง (`pip-audit`/`coverage`/`ruff`/`black`/`mypy`)
  + regression เต็มข้าม (ไม่มี data dir). ทั้งหมดเป็น graceful-skip (ไม่ใช่ความล้มเหลว).
- ค่า `b5c415bb` + `95852c68` ตรงกับที่รายงาน `BUGHUNT_RERECHECK_20260621_TH.md` ใช้เป็น oracle → ยืนยันว่า
  เครื่องยนต์ + parser + rules + ชั้น agent **นิ่งและ deterministic** แม้ Python คนละ minor.

---

## 3) สิ่งที่ยืนยัน "ไม่ได้" ในที่นี้ (เจ้าของต้องรันเอง)

golden ทางการ **`ae84d3f0`** ทำบน **148 ไฟล์ `/mnt/project`** ภายใต้ **Python 3.12 + numpy 2.2.6** ซึ่งคอนเทนเนอร์นี้
เข้าไม่ถึง (ไม่มี corpus + Python เป็น 3.11). ตามกฎ §5/§8 ของ `CLAUDE.md`: เปิด session แล้วยังไม่ได้ `ae84d3f0`
= **ห้ามแตะอะไรที่ขยับ golden** จนกว่าเจ้าของจะรันยืนยันบน runtime ทางการ:

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1
pip install -r requirements.txt -c constraints.txt        # Python 3.12 + numpy 2.2.6 เป๊ะ
python3 regression_full.py . /mnt/project baseline.json   # ต้องได้ engine==agent==baseline = ae84d3f0…
bash run_ci.sh /mnt/project                               # ด่านเต็ม + ขั้น [7]/[8]/[8c]/[8d] บนข้อมูลจริง
```

> หมายเหตุ: รายงานรอบ 2026-06-21 (§2) ระบุว่าการแก้ M-1/L-1/L-2 ออกแบบให้ยิงเฉพาะ edge ที่ข้อมูลสะอาดไม่มี
> จึง "คาดว่า" `ae84d3f0` ยังตรง — แต่ **ยังต้องรันจริงเพื่อปิดจบ** (gate ไม่เชื่อค่าที่จำ).

---

## 4) เรื่อง `[3x7] package integrity` (อย่าตกใจ — ไม่ใช่บั๊ก)

ตอนยังไม่ commit ไฟล์เข้า repo → `package.sh` เรียก `git ls-files` ได้ค่าว่าง (ไฟล์ยัง untracked) → เทส `[3x7]` แดง.
**หลัง `git add` (ไฟล์เข้า index) เทสผ่านทันที** (296 entry · ไฟล์ไทย 8 · UTF-8 flag ครบ · ไม่มี cache/secret หลุด).
นี่คือผลของ "รันเทสก่อน commit" ล้วน ๆ ไม่ใช่ regression ของระบบ.

---

## 5) สิ่งที่ทำ / ไม่ทำ ในเซสชันนี้

**ทำ (golden-neutral):**
- แตก zip (Python `zipfile` + กู้ชื่อไทย + zip-slip guard) → นำไฟล์เข้า `pukpui_v9_3_4/`
- เพิ่ม `CLAUDE.md` (สัญญากำกับ) + `_SESSION_VERIFY_20260622_TH.md` (รายงานฉบับนี้)
- ติดตั้ง deps ตาม pin (เพื่อรัน oracle) ; รัน fixture/real_cases/invariants/CI เพื่อ "ยืนยัน" ไม่ใช่ "แก้"
- commit + push เข้า branch `claude/wizardly-dirac-74wtga`

**ไม่ทำ (เคารพ LOCKED + STOP-AND-ASK):**
- ❌ ไม่แตะ engine / parser / rules / validators / `baseline.json` / fixture
- ❌ ไม่ rebaseline, ไม่แพ็ก release, ไม่ติดตั้ง `pythainlp`, ไม่ bump deps
- ❌ ไม่แตะรายการ "เสี่ยง/รอเจ้าของตัดสิน" จากรอบ 2026-06-21

---

## 6) งานค้าง (ยกมาจาก `BUGHUNT_RERECHECK_20260621_TH.md` — รอเจ้าของสั่งเท่านั้น)

- **ยืนยัน corpus จริง (§3 ข้างบน):** รัน `regression_full.py . /mnt/project` ให้ได้ `ae84d3f0` บน Python 3.12 → ปิดจบ.
- **M-3 / CMP004** (advisory display policy): ตัวเลือก A (คงเดิม) vs B ("ก้ำกึ่ง (ดูตรวจตาเพิ่ม)") — **เจ้าของเลือก**.
- **L-5 (V-F2)** `validators.py:343` DT004 false-positive เลขรันล้วน ≥5 หลัก — เป็น live rule, **ต้อง regression 148 ไฟล์ก่อน** → STOP-AND-ASK.
- **L-7 (P-LOW3)** `parser_p1/p0` ANTI_PREFIX `PRODUCT/SUBTOTAL` dead code — กระทบ IV selection (golden-sensitive) → STOP-AND-ASK.
- **M-2 (0.07 split)** — กระทบการมีอยู่ของบิล, **ต้องมากับ regression 148 ไฟล์เสมอ**.
- L-3/L-4/L-6/L-8..11 — รายงานแล้ว จงใจคงไว้ (false-neg > false-pos / unreachable).

---

### สรุป 1 บรรทัด
**โปรเจกต์เข้า repo เรียบร้อย · oracle ที่ reproduce ได้ในนี้ผ่านหมด (`b5c415bb`/`95852c68`/CI 79-0-6) · golden ทางการ `ae84d3f0` รอเจ้าของรันบน Python 3.12 + corpus · ไม่มีการแก้ที่ขยับ golden.**
