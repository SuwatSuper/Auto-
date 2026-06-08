# HANDOFF — ปุ้มปุ้ย/Pukpui v9.2 hardening (ส่งต่อแชทเสริม)

> เริ่มแชทใหม่: วางไฟล์นี้เป็น context + unzip `pukpui_v9_2_HARDENED_v2.zip` แล้วบอก "ทำต่อตาม roadmap §4"
> งานทั้งหมด = **เสริมความแข็งแรง ไม่เพิ่มฟีเจอร์** · ทุกการแก้ต้อง **golden-gated** · สื่อสารภาษาไทย

---

## 0) กฎเหล็ก (อย่าลืม — พิสูจน์ด้วยเลือดแล้ว)
- **Golden ปัจจุบัน = `35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba`** (= `baseline.json._sha256`)
- **Corpus ทางการ = 106 ไฟล์ `/mnt/project` (834 บิล)** · เลข "81 ไฟล์/ec61907f" = ปลดระวาง (ADR-019)
- ลำดับ hash: `7b60b01f → ec61907f(81) → f1ac8421(106 เก่า) → 73f5bf87(106, ก่อน F2-cont) → 35b2f7c8(106 ปัจจุบัน, ADR-021)`
- **rebaseline = อนุมัติล่วงหน้า** แต่ "ดีขึ้นเท่านั้น" → เปลี่ยน output ได้เมื่อ**พิสูจน์ว่าถูกต้องขึ้น/false-positive ลด** เท่านั้น แล้ว regen + ADR
- **agents = advisory อยู่นอก golden snapshot** (เปลี่ยนแล้ว hash มักไม่ขยับ)
- **golden คือ oracle เดียว ไม่ใช่ F821** — re-export hub ทำให้ F821/F405 under-report ได้ (ดู §3)

## 1) Environment (ตั้งทุกครั้ง)
```bash
python3 -m venv /home/claude/.venv_puopuy && . /home/claude/.venv_puopuy/bin/activate
pip install pandas==2.2.2 numpy==2.2.6 xlrd==2.0.1 openpyxl==3.1.5 rapidfuzz==3.10.1 ruff
# งาน: /home/claude/puopuy_work/pukpui_v9_2 (unzip จาก pukpui_v9_2_HARDENED_v2.zip) · corpus: /mnt/project
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02   # ต้องตั้งทุก run
```
**Verify หลัก (รันหลังทุกการแก้):**
```bash
python3 golden_master.py . /tmp/snap.json /mnt/project     # ต้อง 35b2f7c8
python3 regression_full.py . /mnt/project                  # engine==agent==baseline
python3 test_agents.py . /mnt/project                      # 38/38
ruff check . --select F821                                 # ต้อง 0 (undefined)
python3 test_golden_single_source.py                       # tripwire: doc↔baseline sync
python3 test_file_size_ceiling.py                          # tripwire: ≤600 LOC/ไฟล์
python3 test_run_addon_pack_guard.py                       # tripwire: shoulder feature
bash run_ci.sh /mnt/project                                # CI เต็ม (รวม tripwires + regression จริง)
```

## 2) ทำเสร็จแล้ว (verified · golden เคลื่อนครั้งเดียวที่ ADR-021)
| งาน | ผล |
|---|---|
| **F1** single source of truth | doc/operational sync + `test_golden_single_source.py` + ADR-019 |
| **F4a** split verification_lenses | 894 → base/ext/main ≤600 byte-identical |
| **F2** Decimal money (rules_c) | r_vat006/007/r_itm → Decimal+HALF_UP · hash-neutral |
| **🐞 run_addon_pack** undefined | guard เป็น optional shoulder feature + tripwire · golden ไม่ขยับ |
| **F4b** split vendor_report | 708 → base 358/ext 309/main 127 · byte-identical |
| **F2-cont** float→Decimal money 4 จุด | parser VAT + rules_a · **rebaseline 73f5bf87→35b2f7c8** (2 บิล/834 ปัดเศษถูกขึ้น) · ADR-021 |
| **F4** split parser_p0 | 660 → `parser_p0a` 402 + `parser_p0` 271 · cascade · golden ไม่ขยับ |
| **F4** split config.py | 739 → `config_base` 460 + `config` 293 · `__all__` 60 ชื่อครบ · golden ไม่ขยับ |
| **F3** config-star: 6 leaf | core_utils/diagnostics/validators/master/thai_text/webverify → explicit |
| **F3** config-star: 3 chains | rules/parser/reporting chains → top-down explicit · golden ไม่ขยับ |
| **tripwire ใหม่** | `test_file_size_ceiling.py` (≤600 LOC) + wire 3 tripwires เข้า `run_ci.sh` |

**Metrics ปัจจุบัน:** golden `35b2f7c8` · ไฟล์ >600 LOC: **1** (monolith) · **F403 21→12** · **F405 1746→1361** · F821=0 · determinism 10/10=1 · ทุก test ผ่าน (broad sweep 19 ชุด, agents 38/38)

## 3) บทเรียน/harness ที่ reuse ได้
- **F4 split (byte-identical):** ตัด body ด้วย line-slice → ไฟล์ base + ไฟล์หลัก `from base import *` + auto-export `__all__`. ชื่อ `_underscore` infra ต้องอยู่ใน `__all__` (auto-export ครอบ single-underscore แล้ว). verify: golden + F821 + dedicated test.
- **F2 Decimal money:** คง type-gate/threshold/การแสดงผล (`:.2f`) เดิมเป๊ะ เปลี่ยนแค่ arithmetic→`(_D(x)*Decimal('0.07')).quantize(Decimal('0.01'),ROUND_HALF_UP)`; ที่จุดเก็บ **cast กลับ float**. วัด hash; neutral=ฟรี, ขยับ=forensic diff ทีละบิล (`all_bills[].{vat,subtotal,issues}`) ก่อน rebaseline.
- **F3 de-star (config):** **golden เป็น oracle ไม่ใช่ F821** (F821 under-report re-export hub). chain base ทำ **top-down**: หาเซ็ต config ที่ทั้ง chain ใช้ด้วย **bareword grep `config.__all__`** (superset-safe) → ให้สมาชิก chain import config **ตรง** ก่อน → narrow/ลบ base. anchor `^from config import *$` (ระวัง match คอมเมนต์). golden ทุกขั้น — ขยับ=revert.

## 4) ROADMAP ที่เหลือ (เรียงตามลำดับแนะนำ)

### 🔴 P1 — monolith: de-star (11 import*) + split >600  ★ ก้อนใหญ่สุด ทำคู่กัน
`ปุ้มปุ้ย_ultimate_v9_modular.py` (1324 LOC) — ตัวเดียวที่เหลือ >600 และถือ F403 จริง 11 ตัว
(`from config/rules_engine/diagnostics/thai_text/parser/core_utils/webverify/master/validators/analytics/reporting import *`)
- **ข้อจำกัดห้ามพลาด:** `agents/core_access.py` เข้า monolith ผ่าน `importlib`+`getattr` ดึง **`_REQUIRED` 22 ชื่อ** (parse_all_files, run_all_rules, RULES, match_company, run_audit_core, compute_bill_confidence, check_*, clean_tax_id, _taxid_checksum_ok, _D, _vat_tolerance, build_clean_report, export_excel, reset_run_state ฯลฯ). monolith **ไม่มี `__all__`** → ปัจจุบันชื่อพวกนี้เป็น attribute เพราะ re-export จาก import*.
- **harness แนะนำ:** (1) เพิ่ม `__all__` ใน monolith ที่ครอบ 22 ชื่อ + ชื่อที่ monolith re-export จริง → ยืนยัน `test_agents` + core_access ผ่าน (2) ทำ explicit **ทีละ import*** (เริ่มจากที่ leaf ปลายน้ำ เช่น analytics/reporting) + golden ทุกครั้ง (3) split เมื่อ de-star เสร็จ (โครงใหญ่: io/parse · audit-core · reporting glue) ตาม pattern F4
- monolith มี `from config import *` ที่บรรทัด 173 → config ตรงพร้อม (leaf ที่ narrow ไปแล้วไม่กระทบ)

### 🟡 P2 — chain-internal cascade star (ถ้าต้องการ explicit เต็ม)
cascade `from <prev> import *` ใน rules(a/b/c←base, engine), parser(p0←p0a, p1←p0, p2←p1, parser←p2), reporting, agents — มี `# noqa: F403` อยู่แล้ว (re-export architecture ตั้งใจ). de-star = ให้แต่ละชั้น import **ฟังก์ชัน**ที่ใช้ตรงจาก base (เยอะ) — คุ้มน้อยกว่า P1 ทำทีหลัง

### 🟡 P3 — Agent meta-conformance test (Agent 7→9)
เพิ่ม test ตรวจว่าทุก agent ยึด mesh contract ตาม 9-point bar (advisory/read-only, structured failure). ไม่กระทบ golden

### 🟢 P4 — deferred (ดู `P3_FOLLOWUP_TH.md`)
global mutable state → parallel-safe · config JSON extraction · large-file ที่เหลือ

## 5) DoD (เป้า ≥9 ทุกมิติ)
| มิติ | สถานะ |
|---|---|
| Traceability | ✅ 9 (F1 + tripwire) |
| Financial | ✅ 9 (F2 + F2-cont/ADR-021) |
| Stability | ✅ ~9 (run_addon_pack + 10-round gate + 3 tripwires ใน CI) |
| Maintainability | ✅ ดีขึ้นมาก (ไฟล์ >600: 4→1) — เหลือ split monolith |
| Architecture | ✅ ดีขึ้นมาก (monolith de-star 11→0 + `__all__` 28; **agents/ de-star 5→0**; `bash run_ci.sh` เขียวครบรวม ruff) — เหลือ split monolith + cascade rules/parser/reporting (low-value) |
| Agent | 🔶 7→9 (P3 meta-conformance test) |
| Memory | 🔶 7→9 (P4 parallel state) |

**ปลายทาง:** `bash run_ci.sh /mnt/project` คำสั่งเดียว = 10-round determinism + whole-tree lint + ทุก test + regression จริง ผ่านหมด

---

## ✅ P1 DE-STAR — ปิดงานแล้ว (เซสชันนี้)

**ผล:** `import *` ใน monolith **11→0** · golden = `35b2f7c8…` นิ่งทุกขั้น · F403/F405/F821 บน monolith = 0 · whole-tree F403 12→1 (เหลือ 1 ตัวนอก monolith)

**วิธี:** แต่ละ star → explicit import จากโมดูลที่ "ผูกชื่อล่าสุด" (last-wins) เป็น object เดียวกัน → golden-safe โดยโครงสร้าง; verify golden+F821+surface ทุก edit
- reporting(11)·analytics(8)·validators(10)·webverify(4)·master(2)·parser(6)·diagnostics(3)·rules_engine(2)·config(4)
- core_utils, thai_text → ลบ star (ไม่มี bareword; ชื่อที่ต้องใช้ผูกจาก import ตัวอื่น)
- ชื่อที่ "ตัดออกจากแต่ละ leaf" (RULES/CFG/log_system_issue/ANALYTICS_CFG/APP_VERSION/CONSTRUCTION_DICT/VERIFY_CFG) = ผูกจาก explicit import ตัวที่ execute ทีหลัง → กัน F811 ซ้ำ (พิสูจน์แล้ว)
- เพิ่ม `__all__` = 28 ชื่อ contract (เอกสาร public surface + ดับ F401 ของ re-export; golden-neutral เพราะ consumer ใช้ getattr ไม่ใช่ `import *`)

**🔴 บทเรียนสำคัญ (จับได้จาก CI เต็ม ไม่ใช่ golden):**
สัญญาภายนอกของ monolith มี **3 ประเภท** ไม่ใช่ 2:
  (A) `app.<name>` (getattr ตรง) · (B) `core_access._REQUIRED` · **(C) `core.get("…")` dynamic ใน verification lenses**
de-star รอบแรกพลาด (C) → ตัด `audit_today` (config) + `detect_iv_period_mismatch` (validators) ออกจาก namespace → lens คืน None เงียบ ๆ → **golden/regression/test_agents(38) ผ่านหมด** (เพราะ agent อยู่นอก golden snapshot) แต่ **`test_verification_lenses_unit.py` ([3d3]) ล้ม 3 เคส** — ยืนยันโดยสลับ ORIG↔de-star (ORIG 72/0 vs de-star 69/3)
→ คืน 2 ชื่อเข้า explicit import + `__all__` แล้ว lens unit กลับ 72/0
→ **เสริม `test_monolith_surface.py`**: เพิ่มแหล่ง (D) สแกน `core.get("…")` ใน agents/ อัตโนมัติ + แยก REQUIRED (audit_today/detect_iv_period_mismatch) จาก OPTIONAL (run_addon_pack — degrade ได้, baseline ไม่เคยมี); contract 26→28; wire เข้า run_ci.sh `[3z2]`
**หลักการใหม่:** "agent อยู่นอก golden snapshot → golden ไม่จับ regression ชั้น agent. ต้องรัน CI เต็ม (lens unit) เป็น gate คู่กับ golden เสมอ"

**สถานะ CI:** ทุกขั้นเขียว **ยกเว้น `[11] ruff (lint, scope)`** = 132×F405 ทั้งหมดใน `agents/verification_lenses.py` (cascade star `_base`/`_ext` — ไฟล์ที่ P1 ไม่แตะ, [11] ไม่โหลด monolith)
→ **pre-existing P2 debt** เพิ่งโผล่เพราะเซสชันนี้ติดตั้ง ruff (baseline ไม่มี ruff → [11] ถูกข้าม graceful → CI เขียว). **P1 ไม่ได้ก่อ และไม่แก้** (= งาน P2: de-star cascade ของ verification_lenses)

**residual (ไม่ใช่ CI gate, ไม่ใช่ regression):** F401 บน monolith = 42 = dead import เก่าที่ star เคยบัง (pd/re/json/openpyxl/Decimal/re-export ตายจาก puopuy_core·dates·units/alias `_X` ที่ไม่ใช้). CI ruff scope ไม่รวม monolith → ไม่ทำ CI แดง. แนะนำตัดใน hygiene pass แยก (ระวัง import ใน try/except: fuzz/xlrd)

**ถัดไป:** (1) P2 — de-star cascade `verification_lenses_base/_ext` (gate = [3d3]+agents) เพื่อปิด 132 F405 + ทำ [11] เขียว · (2) prune dead import บน monolith (golden-gate) · (3) SPLIT monolith (ยัง >600, whitelist อยู่) — F4 byte-identical, golden-gate ทุก slice, คง 28 contract เป็น attribute

---

## ✅ P2 — DE-STAR AGENT CASCADES + `bash run_ci.sh` เขียวครบ (เซสชันนี้ ต่อจาก P1)

**ผล:** `import *` ใน `agents/` **5→0** (ทั้ง tree เหลือ cascade ของ rules/parser/reporting เท่านั้น) · **`bash run_ci.sh /mnt/project` = ✅ CI ผ่านทั้งหมด (exit 0)** — รวม `[11] ruff` (132 F405→0) · golden = `35b2f7c8…` นิ่ง · agents 38/38

**ทำอะไร (gate = [3d3]/[3d2]/[4b]/[4c]/agents — agent อยู่นอก golden):**
1. `verification_lenses` cascade — แทน `from ._base import *` + `from ._ext import *` ด้วย explicit import (= `__all__` ของ _base[24]/_ext[26] เป๊ะ, no overlap → behavior-identical) + เพิ่ม `__all__` ให้ hub (re-export surface base∪ext∪own). `_ext` แทน base-star ด้วย 10 ชื่อที่ใช้จริง → **132 F405 = 0, [11] เขียว**
2. `vendor_report` cascade — แทน 3 star ด้วย explicit (main: 13 base + 9 ext; ext: 23 base). `vendor_report.py.__all__` มีแค่ `['DIVIDER','build_vendor_reports']` อยู่แล้ว (ไม่ใช่ re-export hub แบบ lens)

**🔴 บทเรียนซ้ำ (ตอกย้ำหลักการ P1):** consumer ดึง re-export ที่ hub *ไม่ได้ใช้ภายใน* ได้
- `test_vendor_report.py:359` ทำ `from agents.vendor_report import _pre_vat` — `_pre_vat` (ext) re-export ผ่าน star เดิม. de-star รอบแรกผม import แค่ 8 ext ที่ใช้ภายใน → **[4b] ล้ม** (ImportError). golden/agents/[4c] ผ่านหมด (agent นอก snapshot) — **[4b] จับ**
- วิธีหาให้ครบ: AST สแกนทั้ง tree หา `from (agents.)?vendor_report import <names>` → union → ตรวจว่าเป็น attribute ครบ → เติม `_pre_vat`
- **ย้ำ:** de-star re-export hub ต้อง import = (ใช้ภายใน) ∪ (ทุกชื่อที่ consumer import) — ไม่ใช่แค่ภายใน. รัน CI เต็ม (ไม่ใช่แค่ golden) เป็น gate เสมอ

**ของที่ทำเสร็จในเซสชันนี้:** P1 (monolith 11→0 + `__all__` 28 + surface guard (D)) · P2 (agents 5→0, [11]+CI เต็มเขียว)

---

## ✅ #2 — PRUNE DEAD IMPORTS บน monolith (เซสชันนี้)

**ผล:** monolith F401 **42→0** (และ F403/F405/F811/F821/F822 = 0 ครบ → lint-clean) · golden = `35b2f7c8…` นิ่ง · `bash run_ci.sh` เขียวครบ · agents 38/38

**วิธีคัดก่อนลบ (กันพลาดแบบ audit_today/_pre_vat):** สร้าง external surface ครบทุกช่องทาง —
ยืนยัน **ไม่มีใคร `from <monolith> import X` ตรง** (เข้าผ่าน importlib+getattr เท่านั้น) → surface = app.X(17) ∪ core.get(4) ∪ _REQUIRED(22) = 28 · จัดประเภท F401 ทั้ง 42:
- KEEP (in surface): 0 · KEEP (guarded try/except): `fuzz` · REMOVABLE: 41
- ลบจริง: stdlib ที่ logic ย้ายออกแล้ว (pandas/re/glob/json/unicodedata/statistics/sqlite3/time/urllib/timedelta/timezone/openpyxl/decimal/math) + dead re-export จาก puopuy_core·dates·units (to_conf01/normalize_text/parse_date_any/extract_unit_hint ฯลฯ) + module-alias `_rules_engine/_diagnostics/_parser/_thai_text/_core_utils/_webverify/_master` (debug handle ที่ไม่ถูกใช้) + tail duplicate block
- **เก็บ contract เสมอ:** `clean_tax_id/_taxid_checksum_ok` (puopuy_core), `_D/_vat_tolerance` (puopuy_units), `os/traceback/gc/datetime/warnings/Counter` (ใช้จริง)
- **`fuzz` = import-as-dependency-gate** (import ล้ม→SystemExit ข้อความชัด) → `# noqa: F401` ไม่ลบ (import เป็น side-effect ไม่ใช่ dead)

**ค่าที่ได้:** monolith เป็น lint-clean เต็มตัว → พร้อม split (#3) โดยไม่ลาก dead weight ตามไป

---

## ✅ #4 — P3 AGENT META-CONFORMANCE TEST (เซสชันนี้)

**ผล:** เพิ่ม `test_agent_conformance.py` (auto-discover 14 Agent subclass, 101 เช็ก) + wire เป็น `[5b]` ใน run_ci.sh · `bash run_ci.sh` เขียวครบ · golden ไม่กระทบ (โครงสร้างล้วน ไม่แตะ golden path)

**ทำไม (ตรงบทเรียน de-star):** สัญญาชั้น agent อยู่ "นอก golden snapshot" → golden ไม่จับการละเมิด. เทสนี้เป็น gate โครงสร้างคู่กับ golden — เพิ่ม agent ใหม่ = ถูกตรวจทันที (self-maintaining, ไม่ hardcode รายชื่อ)

**ตรวจอะไร (ต่อ agent ทุกตัว, 7 ข้อ):** subclass+instantiate ได้ (implement _run) · **ไม่ override run()** (กล่อง error-boundary/timing สม่ำเสมอ) · override _run จริง · name=str ไม่ว่าง/ไม่ซ้ำทั้งระบบ · description=str · critical=bool · ลายเซ็น _run(self,ctx). + guard ระดับชุด: ทุกโมดูล import ผ่าน (discovery ไม่ถูกข้ามเงียบ) + จำนวน ≥14 (กันผ่านแบบว่างเปล่า)

**พิสูจน์ว่าจับ violation จริง (negative test):** ฉีด agent ปลอม (override run + ชื่อซ้ำ 'vat') → เทสจับทั้ง 2 → exit 1 (ไม่ใช่ผ่านลอย ๆ)

**ความแตกต่างจาก `test_agents.py`:** ตัวนั้น = behavioral (A–I: isolation/degrade/mesh/determinism) เจาะ agent เฉพาะตัว; ตัวนี้ = structural meta วนทุกตัว → ครอบคลุมเสริมกัน

**สรุปเซสชันนี้:** P1 (monolith de-star 11→0 +`__all__`28 +surface guard) · P2 (agents de-star 5→0, [11]+CI เต็มเขียว) · #2 prune (monolith F401 42→0 lint-clean) · #4 P3 meta-conformance ([5b])
**เหลือ:** #3 split monolith (1365 LOC, เซสชันเฉพาะ) · #5 P4 (parallel state/config JSON, ดู P3_FOLLOWUP_TH.md)
