# รายงานตรวจบั๊ก + ความพร้อมทำงานยาว 5 ปี — ปุ้มปุ้ย (Puopuy) v9.3.4 GOLDEN

> วันที่ตรวจ: 2026-06-22 · โหมด: **LOCKED (อ่าน/สืบ/reproduce — ไม่แก้)** ตามวินัย CLAUDE.md
> ขอบเขต: ทั้งระบบ (parser / rules / validators / reporting / agents / resource / date / runtime)
> วิธี: ยืนยันฐานจริง + รัน CI + reproduce ทุกบั๊กด้วยการรันจริง + สืบเชิงลึก 4 หมวดขนาน
> ผู้ตรวจ: Claude Code (remote) · เครื่องนี้ Python 3.11.15 (ทางการล็อก 3.12)

> **🟢 อัปเดต 2026-06-22 (หลังเจ้าของอนุมัติ "แก้ M-2/M-3/M-4 golden-neutral"):**
> **M-2 / M-3 / M-4 แก้แล้ว + พิสูจน์ golden-neutral + 1 ADR ต่อจุด** (ADR-061/062/063) — fixture `b5c415bb` ไม่ขยับ · doc-sync PASS · run_ci.sh exit 0 (เพิ่มเทส `[3x14e]`).
> **M-1 (r_dt003) ยัง "ไม่แตะ"** — golden-sensitive ต้อง STOP-AND-ASK + regression 148 ไฟล์ก่อน (รออนุมัติ). รายละเอียดในข้อ 6.

---

## 0) สรุปผู้บริหาร (อ่านบรรทัดเดียวจบ)

**ระบบ "พร้อมทำงานยาว" จริง — คุณภาพระดับ production สูงมาก** (determinism/ตาข่ายนิรภัย/crash-isolation/offline แข็งแรง พิสูจน์เชิงประจักษ์แล้ว).
แต่จะให้ "นิ่งครบทั้ง 5 ปี (2026→2031)" ต้องปิด **1 ระเบิดเวลาในกรอบ 5 ปี** + ดูแล operational อีก 3 จุด.

| คำถามของคุณ | คำตอบ |
|---|---|
| **บั๊กร้ายแรง (CRITICAL)** | **ไม่มี** — ยืนยันทั้งของผม + 3 สาย audit ขนาน + golden ทางการ `ae84d3f0` ที่เจ้าของรันบน 3.12/148 ไฟล์ |
| **บั๊กกลาง (MEDIUM)** | **4 จุด** — ตัวสำคัญสุดคือ **ระเบิดเวลา r_dt003 ปี 2031** (ปีที่ 5 พอดี) |
| **บั๊กต่ำ (LOW)** | ~10 จุด (ส่วนใหญ่ documented/edge/นอกกรอบ 5 ปี/defensive) |
| **พร้อมทำงาน 5 ปี?** | **พร้อม ✅ แต่มีเงื่อนไข** — แก้ r_dt003 ก่อนถึงปี 2031 + วางแผน Python 3.12 EOL (ต.ค. 2028) + housekeeping ดิสก์ |

---

## 1) ยืนยันฐาน (สิ่งที่ผม reproduce ได้ในเครื่องนี้)

| Oracle | ค่าที่ได้ | คาดหวัง | ผล |
|---|---|---|---|
| baseline.json._sha256 (corpus) | `ae84d3f0` | `ae84d3f0` | ✅ ตรง (ค่าในไฟล์ — corpus จริงรันที่นี่ไม่ได้ ไม่มี /mnt/project + Python 3.11) |
| fixture golden (engine==agent==baseline) | `b5c415bb` | `b5c415bb` | ✅ ตรงเป๊ะ |
| check_invariants.py | 4/4 | 4/4 | ✅ |
| run_ci.sh (ไม่มี data dir) | exit 0, ทุก step ผ่าน | — | ✅ |

> หมายเหตุ: golden ทางการ 148 ไฟล์ (`ae84d3f0`) เจ้าของยืนยันแล้วบน Python 3.12.3 (ดู `_ส่งมอบ_v9_3_4_ADR060`).
> เครื่องนี้ทำซ้ำไม่ได้ (ไม่มี corpus + เป็น 3.11) — แต่ fixture/CI/invariant ที่ทำได้ **ผ่านหมด**.

---

## 2) 🔴 บั๊กร้ายแรง (CRITICAL) — **ไม่มี**

ตรวจครบทุกเส้นทางหลัก ไม่พบบั๊กที่ทำ batch ล่ม/ข้อมูลหายถาวร/ผลตรวจเพี้ยนเงียบบนเส้นทางจริง:
- **Crash isolation จริง**: per-file / per-sheet / per-bill ห่อ try/except → ไฟล์เสีย 1 ไฟล์ ไม่ล้มทั้งชุด (พิสูจน์: ยิง input พยาธิสภาพ 8 แบบ → 0 crash, ที่เหลือยังตรวจครบ)
- **master kill-safe** (เส้นทางหลัก ADR-039/040/049): atomic write + `.user.bak` + atexit restore + stub-marker — reproduce kill/restart แล้ว master จริงรอด
- **Determinism**: 5 รอบใน process เดียว hash เท่ากันเป๊ะ (`95852c68`), parallel==serial, ไม่มี wall-clock รั่วเข้า logic
- **Offline**: default ห้ามออกเน็ต (`offline_guard`), LLM/web เป็น opt-in + มี timeout — ไม่ค้างยาว
- ไม่มี bare `except:` บนเส้นทางจริง (ที่เจอ 3 จุดเป็น "คอมเมนต์"), ไม่มี assert บน critical path (ปลอดภัยใต้ `python -O`), ไม่มี recursion ลึก

---

## 3) 🟡 บั๊กกลาง (MEDIUM) — 4 จุด

### M-1 · ⏰ ระเบิดเวลา `r_dt003` — ฟ้องผิด "ทุกบิล" ตั้งแต่ปี ค.ศ. 2031 (= ปีที่ 5 พอดี) ★ สำคัญสุดต่อคำถาม "5 ปี"
- **ตำแหน่ง**: `rules_engine_rules_a.py:532` → `if yr > 2030 and yr < 2500:`
- **อาการ**: parser แปลง พ.ศ.→ค.ศ. แล้ว (เก็บ iv_date เป็น ค.ศ.). พอเวลาจริงเดินถึง **ค.ศ. 2031 (พ.ศ. 2574)** บิลปกติทุกใบจะมี `iv_date.year ≥ 2031` → เข้าแบรนช์นี้ → ติดหมายเหตุเพี้ยน
- **reproduce จริง** (ตั้ง `PUOPUY_AUDIT_DATE` ไปข้างหน้า แล้วเรียก r_dt003 บนบิลปกติ):
  ```
  audit 2030, bill ค.ศ. 2030 : []                                                  ✅ ปกติ
  audit 2031, bill ค.ศ. 2031 : ['ปี 2031 (พ.ศ. 2574) อาจเป็น digit swap ของ 2574 (สลับหลัก?)']  ❌
  audit 2031, bill ค.ศ. 2032 : ['ปี 2032 อาจคลุมเครือ (ค.ศ./พ.ศ.?)']                             ❌
  audit 2033, bill ค.ศ. 2033 : ['ปี 2033 (พ.ศ. 2576) อาจเป็น digit swap ของ 2576 (สลับหลัก?)']  ❌
  ```
  (ยืนยัน end-to-end ผ่าน full engine ด้วย ไม่ใช่แค่เรียกฟังก์ชันเดี่ยว)
- **root cause**: แบรนช์ ค.ศ. (บรรทัด 535) **ขาด guard `yr+543 != current_year_be`** ที่แบรนช์ พ.ศ. (บรรทัด 541) มี → `_is_digit_swap_of(x, x)` คืน True เสมอ (sorted เท่ากัน) → "บิลปีปัจจุบัน = digit-swap ของตัวเอง". ส่วน else (บรรทัด 538) ฟ้อง "คลุมเครือ" กับบิลปีถัด ๆ ไป
- **ทำไมไม่เคยเห็น/golden ไม่ขยับ**: corpus ทางการลงวันที่ ≤2026 (audit pin 2026-06-02) ไม่แตะแบนด์ >2030 → hash ไม่ขยับ → ซ่อนมานาน
- **เลน/ผลกระทบ**: DT003 อยู่เลน **NOTE (ข้อสังเกต)** ไม่ใช่ "ต้องแก้" → ไม่บล็อก. **แต่** ฟ้อง 100% ของบิลตั้งแต่ปี 2031 = ท่วมรายงาน → ผู้ตรวจ "ชินกับการเมิน DT003" → **digit-swap จริงจะถูกเมินตาม (false-negative จากการ desensitize)** ซึ่งขัดปรัชญาระบบ ("false-neg แย่กว่า false-pos")
- **เคยถูกบันทึก**: `BUGHUNT_REPORT_v9_3_1_TH.md` ("Validators-M1", สถานะ = *รายงาน ยังไม่แก้*). recheck #9 แก้แค่ "ถ้อยคำ" ไม่ได้แก้ขอบเขต `yr>2030`. รายงานส่งมอบล่าสุด (2026-06-22) จัดเป็น "L2 cosmetic" — **ประเมินต่ำไป**: ไม่ใช่แค่ปีขยะ 9999 แต่กระทบ **บิลจริงในกรอบ 5 ปี**
- **ทิศทางแก้ (golden-sensitive → STOP-AND-ASK)**: ทำขอบเขต ค.ศ. ให้ "ตามเวลา" เหมือนแบรนช์ พ.ศ. — เติม guard `(yr+543) != current_year_be` และ/หรือใช้เกณฑ์ `yr > audit_today().year + 1` แทนเลข 2030 ตายตัว. **golden-neutral บน corpus ปัจจุบัน** (≤2026) แต่แตะ logic กฎ → ต้อง regression 148 ไฟล์ + อนุมัติ

### M-2 · 💾 `master.save_master` ไม่รู้จัก stub → สำรอง stub ทับ `.bak` กู้คืนของจริง (ข้อมูลหาย — วงแคบ)
- **ตำแหน่ง**: `master.py:56-62` — guard `keep = _json_dict_len(current) >= _json_dict_len(bak)` (นับจำนวน key อย่างเดียว ไม่ดู `_golden_stub`)
- **พบโดยอิสระ 2 สาย audit + ผมยืนยันโค้ดเอง** (สัญญาณแน่น)
- **อาการ**: ต่างจาก `golden_snapshot.write_master_file` ที่ "รู้จัก stub", ตัว `save_master` (ที่ผู้ใช้เรียกผ่าน `input_master_data`/`เพิ่ม_master.py`) ไม่เช็ค marker. ถ้าเครื่องมือ golden/test ทิ้ง **stub** ไว้เป็นไฟล์ live (stub มี 1 บริษัท + key `_golden_stub` → นับได้ ≥ ของจริง) แล้วผู้ใช้ save → **คัดลอก stub ทับ `.bak`** ที่เป็นจุดกู้คืนจริง
- **reproduce จริง**: `.bak=[ก,ข]` + live=stub → หลัง save → `.bak` กลายเป็นข้อมูล stub
- **ผลกระทบ (จำกัด)**: ไฟล์ master **live ที่ผู้ใช้เพิ่ง save ยังถูกต้อง** (ไม่หายทันที) + `.bak` (ไม่ใช่ `.user.bak`) ระบบ **ไม่ auto-restore** → กระทบเฉพาะ "สำเนากู้คืนด้วยมือ" รุ่นก่อนหน้า. แต่เป็นความ "ไม่สอดคล้อง" ระหว่าง 2 ชั้น (golden_snapshot รู้ stub / save_master ไม่รู้)
- **ทิศทางแก้ (golden-neutral)**: ให้ `save_master` ข้ามสำรองเมื่อ live มี `_golden_stub` (เลียน `_file_has_stub_marker`) และ/หรือไม่นับ `_golden_stub` ใน `_json_dict_len`

### M-3 · 🗄️ รายงาน/โฟลเดอร์ "ตรวจแล้ว" โตไม่จำกัดบนดิสก์ (operational — ไม่มี rotation)
- **ตำแหน่ง**: รายงานหลัก `audit_v58_<ts>.xlsx` (ตั้งชื่อตามเวลา) + โหมด AUTO สร้าง `ตรวจแล้ว_<ts>_<pid>/` ทุกรอบ — **ไม่มีโค้ดลบ/หมุนเวียนเลย**
- **ผลกระทบ**: ไม่ใช่ปัญหา RAM/fd (RAM/fd นิ่ง พิสูจน์แล้ว) แต่ **ดิสก์โตเรื่อย ๆ** ตลอด 5 ปี. ไฟล์ input ถูก *ย้าย* ออก (input dir ไม่บวม) — ที่โตคือ report/archive dir
- **หมายเหตุดี**: `audit_system_issues.jsonl` เปิดโหมด `'w'` (เขียนทับทุกรอบ) → **ไม่โต** ✅ ; การย้ายไฟล์ AUTO collision-safe (ts+pid + กัน path traversal) ✅
- **ทิศทางแก้ (golden-neutral)**: เพิ่มขั้น retention (ลบ/บีบไฟล์เก่าเกิน N วัน) หรือ cron ภายนอก

### M-4 · 🌐 `print()` ภาษาไทย crash ถ้า locale เป็น ascii (เช่น `LANG=C`) — environmental
- **อาการ**: ถ้ารันใต้ stdout ที่ไม่ใช่ UTF-8 (LANG=C / บาง cron / systemd ที่ไม่ตั้ง locale) `print()` ไทยจะ `UnicodeEncodeError` **ตั้งแต่เริ่ม** (ก่อนแตะไฟล์ใด ๆ)
- **ผลกระทบ 5 ปี**: เป็นความเสี่ยง "สภาพแวดล้อม" ตอน deploy/cron มากกว่าบั๊กโค้ด — แต่ควร hardening
- **ทิศทางแก้ (golden-neutral)**: ตั้ง `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` ใน runner/cron หรือ `reconfigure(encoding='utf-8')` ตอน start

---

## 4) ⚪ บั๊กต่ำ (LOW) — ส่วนใหญ่ documented / นอกกรอบ 5 ปี / defensive

| # | ตำแหน่ง | เรื่อง | สถานะ |
|---|---|---|---|
| L-1 | `validators.py` DT004 | false-positive: เลขรันล้วน ≥5 หลัก ถูกตีเป็น YYMM งวด → ฟ้องวันที่ผิด | **open item เดิม** (live rule, ต้อง regression 148 ไฟล์ + อนุมัติ) |
| L-2 | `puopuy_dates.py:92` strptime fallback | ปี 2 หลักช่วงกำกวม (40–57 / 00–14) ควรคืน None แต่ strptime "เดา" วันให้ | **บิตจริงปี ค.ศ. 2040** (นอกกรอบ 5 ปี) |
| L-3 | `parser_p0a.py:161` parse_filename | แปลงปีชื่อไฟล์ 2 หลักไม่สอดคล้องกับ `_filename_period_ce` (ช่วง gap) | นอกกรอบ 5 ปี / ไม่พัง แค่ inconsistent |
| L-4 | `puopuy_units.py:_D` | ยอดติดลบไม่สมมาตร (subtotal/total รับ >0, VAT กรอง \|v\|≤1) | defensible (ไม่ใช่ใบกำกับปกติ) |
| L-5 | BE→CE ไม่มีเพดานบน | ปี 9999 → 9456 (โดน DT002/003/004 ฟ้องอยู่แล้ว) | cosmetic |
| L-6 | `reporting_p0.py:243/219` | dashboard/display เรียกแบบไม่ห่อ try ใน main() — KeyError/TypeError ได้ | **ยังไม่ reachable** (บิลจาก parser มี key ครบเสมอ) — defensive |
| L-7 | `master.py:67-70`, `golden_snapshot.py:50-57` | เหลือ `.tmp` ค้างถ้า `os.replace` ล้ม (atomicity ยังครบ) | cosmetic |
| L-8 | `reporting_p1.py:129`, `reporting_p2.py:326` | เขียนรายงานไม่ atomic | ลดความเสี่ยงด้วยชื่อไฟล์ตามเวลาแล้ว |
| L-9 | `make_release.py:80` `extractall` | ไม่มี zip-slip guard (ที่เอกสารอ้างว่ามี — จริง ๆ ไม่มีในโค้ด) | build-time/ไฟล์ที่เพิ่งสร้างเอง (trusted) + stdlib 3.11 กัน traversal ให้ |
| L-10 | `_SYSTEM_ISSUES` | ไม่มี hard cap (ต่าง TEXT_NUM@20k) | dedup + reset ทุกรอบ → theoretical |
| L-11 | `.github/workflows/ci.yml:16` | `runs-on: ubuntu-latest` ดริฟต์ข้ามปี | แนะนำ pin `ubuntu-24.04` เพื่อ reproducibility 5 ปี |

> ที่ verify แล้ว **"ไม่ใช่บั๊ก"**: 29 ก.พ. ปีอธิกสุรทิน (2028/พ.ศ.2571) parse ถูก · r_dt002 future-date เดินตามเวลาจริงถูก (ไม่ฟ้องบิลปีปัจจุบันใน 2027–2031) · เพดานปี parser ขยายถึง ค.ศ.2056/พ.ศ.2599 (เกินกรอบ 5 ปีเยอะ) · ระเบิดเวลา `_filename_period_ce` พ.ศ.2582 ที่เอกสารเก่ากลัว **แก้แล้ว** · cache cap 50k/50k/20k + reset 11/11 global ครบ

---

## 5) 🗓️ ประเมินความพร้อม "ทำงานยาว 5 ปี" (2026 → 2031) แยกเสา

| เสา | สถานะ | หมายเหตุ |
|---|---|---|
| **Determinism / golden** | ✅ ดีเยี่ยม | version_gate + golden oracle + doc-sync + ADR ledger — governance ชั้นเยี่ยม |
| **หน่วยความจำ (RAM)** | ✅ สะอาด | พิสูจน์ flat 5 รอบ (~89MB คงที่), reset+trim+gc ครบ, ไม่มี lru_cache รั่ว |
| **File descriptor** | ✅ สะอาด | พิสูจน์ flat 600 รอบเปิดไฟล์ (fd=4 ตลอด) |
| **Temp / atomic write** | ✅ ดี | atomic ทุกจุดสำคัญ, exception-safe (เหลือแค่ .tmp cosmetic) |
| **Crash-safety input ใหม่** | ✅ แข็งแรง | 8 input พยาธิสภาพ 0 crash + file_guard (size/zip-bomb) fail-open |
| **ข้อมูล master** | ✅ เส้นหลักนิ่ง / ⚠️ M-2 วงแคบ | kill-safe หลักผ่าน, เหลือ `.bak` stub-blind แคบ ๆ |
| **Offline 5 ปี** | ✅ | default-deny + timeout, ไม่ค้าง |
| **📅 ปฏิทิน/ปี** | ⚠️ **M-1 ในกรอบ** | ระเบิดเวลาเดียวในกรอบ 5 ปี = `r_dt003` ปี 2031 — ที่เหลือเพดานถึง 2056 |
| **🐍 Runtime (Python)** | ⚠️ **ต้องวางแผน** | **Python 3.12 EOL ~ต.ค. 2028** (อยู่ในกรอบ 5 ปี!) → หลังนั้นไม่มี security patch |
| **📦 Dependency 5 ปี** | ✅ | pin ครบ + อยู่บน PyPI ถาวร → `pip install -c constraints.txt` reproduce ได้ตลอด |
| **💽 ดิสก์** | ⚠️ M-3 | report/archive ไม่มี rotation → ต้อง housekeeping ภายนอก |

### เรื่อง Python 3.12 EOL (สำคัญสำหรับ "5 ปี")
- 3.12 หมด security support ~**ต.ค. 2028** = ปีที่ 3 ของกรอบ. หลังนั้นยังรันได้แต่ไม่มี patch
- ระบบ **รู้ตัวแล้ว** (CLAUDE.md §7.3 มี "ขั้นตอนหนี" เมื่อต้องเปลี่ยน runtime) — เป็นความเสี่ยงที่ "จัดการไว้แล้ว" ไม่ใช่บั๊ก
- **คำแนะนำ**: ทำตามที่เอกสารบอก — เก็บ **snapshot ถาวร 1 ชุด (container/venv freeze บน Python 3.12)** ตั้งแต่ตอนนี้ → ปี 2030 ยัง rebuild `ae84d3f0` เป๊ะได้แม้ OS โลกภายนอกไปไกลแล้ว

---

## 6) สิ่งที่ควรทำ (เรียงตามผลกระทบ · ทุกอย่างเคารพวินัย LOCKED)

1. **[⏳ รออนุมัติ · ในกรอบ 5 ปี · ก่อนปี 2031] M-1 r_dt003** — golden-sensitive → **STOP-AND-ASK**: ผมเสนอ delta + simulate 148 ไฟล์ก่อน (คาดว่า golden-neutral เพราะ corpus ≤2026) แล้วรออนุมัติ **← จุดเดียวที่ยังเหลือในกรอบ 5 ปี**
2. **[✅ แก้แล้ว · ADR-061] M-2 master `.bak` stub-aware** — `master.py` เพิ่ม `_text_is_golden_stub` (สมมาตร `golden_snapshot`) · เทส `[3x14e]` · golden เท่าเดิม
3. **[✅ แก้แล้ว · ADR-062/063] M-3 disk rotation + M-4 locale** — `_prune_old_reports` (env `PUKPUI_REPORT_RETENTION_DAYS`, default ปิด) + `_ensure_utf8_console()` ใน entry · golden เท่าเดิม
4. **[วางแผนล่วงหน้า] Python 3.12 EOL** — เก็บ container/venv snapshot ถาวรเดี๋ยวนี้ (เอกสารแนะนำไว้แล้ว)
5. **[เก็บกวาด] L-11** pin `ubuntu-24.04` ใน CI ; L-1 DT004 รอ batch regression

> วินัย: ผมอยู่โหมด **LOCKED** — ทั้งหมดข้างบนคือ "รายงาน" ยังไม่แตะโค้ด.
> M-1/L-1 แตะ logic กฎ = ต้องอนุมัติ + rebaseline ถ้า hash ขยับ. M-2/M-3/M-4 เป็น golden-neutral แก้ได้เมื่อสั่ง (พิสูจน์ + 1 ADR).
> **บอกมาได้เลยว่าจะให้ผมลงมือจุดไหน** — ผมจะเริ่มจากตัว golden-neutral (M-2/M-3/M-4) ที่ปลอดภัยสุดก่อน หรือเสนอแผนแก้ M-1 พร้อม simulate.

---

### สรุป 1 บรรทัด
**ไม่มีบั๊กร้ายแรง · ระบบ production-grade พร้อมรันยาว · เพื่อให้นิ่งครบ 5 ปีต้องปิดระเบิดเวลา r_dt003 (ปี 2031) + ดูแล Python-3.12-EOL/ดิสก์/locale + อุดรู `.bak` stub วงแคบ — ความจริงอยู่ที่ baseline.json + run_ci.sh เสมอ.**
