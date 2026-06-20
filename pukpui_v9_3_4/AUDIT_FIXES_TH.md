# รายงานตรวจสอบโค้ด (Code Audit) — ปุ้มปุ้ย v9.1

> มุมมอง: Principal Software Architect / Production Reliability Engineer / Code Auditor / Long-Term Maintainer
> ขอบเขต: หาบั๊ก (ร้ายแรง/กลาง/ต่ำ) + ซ่อม + ลดหนี้เทคนิค **โดยไม่เพิ่มฟีเจอร์** และ **ไม่ทำให้ผลตรวจเพี้ยน**
> ผลลัพธ์โดยรวม: **แก้แล้ว 8 รายการในชั้น advisory — พิสูจน์ว่าผลตรวจ byte-identical (`ec61907f…`) ไม่ขยับแม้แต่บิตเดียว**

---

## 0. บทสรุปผู้บริหาร (TL;DR)

- แพ็กเกจ **ครบสมบูรณ์และรันได้** (49 ไฟล์ .py + เครื่องยนต์ + baseline + ชุดทดสอบ). คำเตือน “ระบบรันไม่ได้/ไฟล์เครื่องยนต์หาย” ในรอบแรกเป็น **ความผิดพลาดฝั่งผม** (แตกไฟล์ zip ไม่ครบ) — **ขอถอนคำพูดนั้นอย่างเป็นทางการ** (ดู §1).
- ตรวจพบประเด็นจริง **2 กลาง-ค่อนสูง + 4 กลาง + 4 ต่ำ** ส่วนใหญ่อยู่ใน **ชั้น agent (advisory)** ซึ่งแก้ได้ปลอดภัยเพราะไม่แตะผลตรวจที่ออก Excel.
- **ซ่อมแล้ว 8 รายการ** และ **พิสูจน์ด้วยเครื่องมือของระบบเอง** ว่า hash ผลตรวจไม่เปลี่ยน:
  `engine == agent == baseline = ec61907f…` + ชุดทดสอบทุกชุดผ่าน (38/38, 27/27, 16/16, 48/48).
- **เครื่องยนต์หลัก (parser/rules_engine/validators/analytics/ฯลฯ ~5,500 บรรทัด) ผมตั้งใจไม่แก้** เพราะมันคือ “แกนที่พิสูจน์แล้ว” ที่ถูกล็อกด้วย golden hash — การแก้บนข้อสันนิษฐานโดยไม่มีเหตุระดับวิกฤตจะเสี่ยงสัญญา byte-identical ที่เป็นหัวใจของระบบ. ประเด็นที่พบในชั้นนี้บันทึกเป็น “ข้อแนะนำ” (§5) ให้พิจารณาแก้ผ่าน golden-master gate.

---

## 1. การแก้ความเข้าใจผิดสำคัญ (สิ่งที่ต้องพูดให้ชัด)

รอบแรกผมรายงานว่า “แพ็กเกจไม่สมบูรณ์ — เครื่องยนต์หลัก (`ปุ้มปุ้ย_ultimate_v9_modular.py`, `state.py`, `puopuy_core.py`, `rules_engine.py`, …) หายไป → ระบบรันไม่ได้”. **เรื่องนี้ไม่จริง.**

สาเหตุที่แท้จริง: คำสั่งแตกไฟล์ (`unzip`) รอบแรกของผม **ถูกตัดกลางคัน** จึงได้ไฟล์มาเพียง 33/49 ไฟล์ (ไฟล์เครื่องยนต์ขนาดใหญ่ + ชื่อภาษาไทยตกหล่น). เมื่อแตกไฟล์ใหม่อย่างครบถ้วนพบว่า zip ต้นฉบับมี **49 ไฟล์ .py ครบ** รวมเครื่องยนต์ทั้งหมด, ชุดทดสอบ (`test_agents.py`, `verify_golden.py`, `regression_full.py`, …), และ `baseline.json`.

บทเรียน (ฝั่งผม): ก่อนสรุปว่า “ของหาย” ต้องยืนยันกับสารบบ zip จริง (`unzip -l`) ไม่ใช่เชื่อผล `find` หลังการแตกไฟล์ที่อาจไม่ครบ. ผมขออภัยในความสับสนนี้ และรายงานฉบับนี้คือข้อสรุปที่ถูกต้องหลังตรวจกับเครื่องยนต์จริง.

---

## 2. วิธีการตรวจ (Methodology)

1. อ่านสถาปัตยกรรมจากเอกสาร (`HANDOVER_TH.md`, `MESH_MANUAL_TH.md`) + อ่านโค้ดทุกไฟล์ในชั้น agent และโมดูล leaf.
2. แยกประเภทไฟล์: **(ก) ชั้น advisory (agents/) แก้ได้ปลอดภัย** — เอกสารรับประกันว่า `ReportAgent` ไม่อ่าน mesh จึงไม่กระทบ Excel; **(ข) เครื่องยนต์/leaf ที่ถูก golden-protected** — ห้ามแตะถ้าไม่จำเป็นวิกฤต.
3. สแกนรูปแบบเสี่ยง: `eval/exec`, bare `except:`, `subprocess/shell`, `pickle`, mutable default args, การ split คีย์, การกลืน exception, การ format ค่า `None`, dead/duplicate code.
4. **ติดตั้งไลบรารีให้ตรง pin** (pandas 2.2.2, rapidfuzz 3.10.1, pythainlp 5.0.5) ให้ผ่าน version-gate แล้ว **รัน golden-master จริงบนข้อมูล 81 ไฟล์ (`/mnt/project`)**.
5. ใส่การแก้ → รัน `verify_golden`/`regression_full`/`test_agents`/`smoke_test`/`test_mesh_contract`/`test_pinned_logic` ทั้งหมด เพื่อพิสูจน์ว่า **ผลตรวจไม่เปลี่ยน**.

---

## 3. ตารางสรุปผล (Findings)

| ID | ระดับ | ประเด็น | ไฟล์ | สถานะ |
|----|-------|---------|------|--------|
| F1 | 🟠 กลาง-สูง | ชั้น `agents/__init__.py` import แบบ eager → โมดูล “บริสุทธิ์” (contracts/base/mesh/llm_provider) import ไม่ได้ถ้าเครื่องยนต์มีปัญหา; symbol เดียวหาย = ทั้ง namespace ล่ม | `agents/__init__.py` | ✅ แก้ + verified |
| F2 | 🟡 กลาง | โค้ดซ้ำหนัก: `_parse_llm_json` ×3, `_SEV_RANK`/`_max_sev` ×4–6, bill-key สร้างเองซ้ำ ×3 | agents/* | ✅ แก้ (รวมเป็น `_shared.py`) |
| F3 | 🟡 กลาง | `bkey.split("|",2)` แปลงคีย์กลับแบบ lossy — ถ้าชื่อไฟล์/ชีตมี `\|` จะแยกผิด (ผลสังเคราะห์เพี้ยนเงียบ) | `mesh.py`, `confidence_agent.py` | ✅ แก้ |
| F4 | 🟡 กลาง | LLM `chat()` ล้มชั่วคราว → agent กลายเป็น `error` ทำให้ SuperAgent QA เข้าใจผิดว่า “ระบบพัง” | ai_review/synthesis/super | ✅ แก้ (degrade → skipped/statistical) |
| F5 | 🟡 กลาง | `run_agents.py` ตั้ง `source="drive"` ที่ทั้ง dead และทำให้เข้าใจผิดว่าดึงจาก Google Drive | `run_agents.py` | ✅ แก้ |
| F6 | 🔵 ต่ำ | `notepad_report` format `{rank:>2}`/`{priority:>5}` จะ crash ถ้าคีย์หาย (latent) | `notepad_report.py` | ✅ แก้ (กัน None) |
| F7 | 🔵 ต่ำ | `COMPANY_TYPO_PREFIXES` มีสมาชิกซ้ำ (`'บริษัส'` 2 ครั้ง) — dead/สับสน | `config.py` | ✅ แก้ |
| F8 | 🔵 ต่ำ | `gen_explanation(state, …)` ชื่อพารามิเตอร์บัง module `state` ที่ import มา (อ่านยาก) | `thai_text.py` | 📝 แนะนำ (engine — ไม่แตะ) |
| F9 | 🔵 ต่ำ | `webverify.run_product_verification` เปิด sqlite `conn` ไม่มี `try/finally` (leak ถ้า exception หลุด) | `webverify.py` | 📝 แนะนำ (engine — ไม่แตะ) |
| F10| 🔵 ต่ำ | `validate_master_entry` เรียก `len(clean_tax_id(...))` อาจ crash ถ้าคืน `None` (latent, flow ปัจจุบันส่ง `""` ไม่ส่ง `None`) | `master.py` | 📝 แนะนำ (engine — ไม่แตะ) |

> หมายเหตุ: เครื่องยนต์ผ่านการสแกนรูปแบบอันตราย — **ไม่พบ** `eval/exec`, bare `except:`, `subprocess/shell`, `pickle`, หรือ mutable default args. ถือว่ามีวินัยโค้ดดีมาก.

---

## 4. รายละเอียดแต่ละรายการที่ “แก้แล้ว” (พร้อม 6 มิติตามที่ขอ)

### F1 — แยกชั้น “บริสุทธิ์” ออกจากเครื่องยนต์ (lazy package init) 🟠
- **Current risk:** `agents/__init__.py` import ทุก agent ทันที → ลาก `core_access` (เครื่องยนต์ทั้งก้อน) มาเสมอ. ผลคือ `import agents.contracts` (ซึ่งไม่พึ่งเครื่องยนต์เลย) ก็ล้มถ้าเครื่องยนต์ขาด symbol เดียว → namespace `agents` ทั้งชุดใช้ไม่ได้ รวมถึงเครื่องมือทดสอบ. (พิสูจน์: ตอนเครื่องยนต์หาย โมดูลบริสุทธิ์ทั้ง 13 ตัว import ไม่ได้เลย)
- **Root cause:** การ re-export แบบ eager ใน `__init__` ทำให้เกิด import-time coupling ระหว่างชั้น advisory กับชั้น engine ที่ไม่ควรผูกกัน.
- **Long-term impact:** เปราะต่อการ refactor (เปลี่ยนชื่อ 1 symbol = ล้มทั้งชั้น), เทสต์ชั้น mesh/contract แยกไม่ได้, partial import ช้า/พังโดยไม่จำเป็น.
- **Recommended solution (ที่ทำ):** เปลี่ยนเป็น **lazy `__getattr__` (PEP 562)** — ผูกชื่อ→โมดูลย่อย แล้ว import เมื่อถูกอ้างถึงครั้งแรก. `from agents import FindingsMesh/Severity` → ไม่แตะเครื่องยนต์; `from agents import ImportAgent` → จึงโหลด `core_access` (พึ่งเครื่องยนต์จริง — ถูกต้อง).
- **Migration risk:** ต่ำมาก. `__all__` คงเดิม, ทุก call site (`from agents import X`, `from agents.orchestrator import …`) ทำงานเหมือนเดิม (`smoke_test` ยืนยัน). หลังแก้: โมดูลบริสุทธิ์ 13/13 import ได้แม้ไม่มีเครื่องยนต์.
- **Priority:** สูง (สุขภาพสถาปัตยกรรม/ความยืดหยุ่น)

### F2 — รวมโค้ดซ้ำเป็น `agents/_shared.py` 🟡
- **Current risk:** `_parse_llm_json` ถูกก๊อปเป๊ะ 3 ไฟล์; ตารางลำดับความรุนแรง (`_SEV_RANK` 3/2/1/0) + `_max_sev` ซ้ำ 4–6 ที่; การสร้างคีย์ `file|sheet|iv` เขียนเองซ้ำ. แก้บั๊กในสำเนาเดียวแล้วลืมอีกสำเนา = พฤติกรรมต่างกันเงียบ ๆ.
- **Root cause:** ไม่มีโมดูลกลางสำหรับ helper ที่ใช้ข้าม agent.
- **Long-term impact:** หนี้เทคนิคโตขึ้นทุกครั้งที่เพิ่ม agent; แก้/อัปเกรดยากและเสี่ยง drift.
- **Recommended solution (ที่ทำ):** สร้าง `agents/_shared.py` (บริสุทธิ์ ไม่พึ่งเครื่องยนต์) รวม `SEV_RANK`, `max_severity()`, `bill_key()`, `parse_llm_json()` แล้วให้ทุก agent import จากที่เดียว. คง `_SEV_WEIGHT` ที่ “ตั้งใจต่างกัน” (confidence 10/6/3/1 vs super 40/25/12/4) ไว้ที่เดิม.
- **Migration risk:** ต่ำ. รักษาพฤติกรรมเดิม: `parse_llm_json` ยังคง raw-text fallback ให้ ai_review/synthesis (ผ่าน `raw_fallback_key`) — ผล hash ไม่เปลี่ยน (verified).
- **Priority:** กลาง (ลดหนี้เทคนิค/กัน bug drift)

### F3 — เลิก “แยกคีย์กลับ” ที่ทำข้อมูลเพี้ยนถ้าชื่อมี `|` 🟡
- **Current risk:** `file, sheet, iv = bkey.split("|", 2)` คืนค่าผิดถ้า `file`/`sheet` มีอักขระ `|` (เช่น `B|weird.xls`) → finding ของ Tier-2 ชี้บิลผิดใบ/ชี้ที่ผิด.
- **Root cause:** ใช้คีย์ที่ join ด้วย `|` แล้ว reconstruct ด้วยการ split (lossy) แทนการเก็บ tuple ต้นฉบับ.
- **Long-term impact:** correctness bug ที่ซ่อนเงียบ (ไม่ throw) — โผล่เมื่อชื่อไฟล์/ชีตมีอักขระพิเศษ.
- **Recommended solution (ที่ทำ):** เก็บแผนที่ `key -> (file, sheet, iv)` ขนานไว้ (`_bill_ref` ใน mesh, `per_bill_ref` ใน confidence) แล้วอ่านจาก map แทน split. (SuperAgent ทำถูกอยู่แล้วด้วย `ref` dict — ใช้เป็นแบบ.)
- **Migration risk:** ต่ำมาก. กรณีปกติ (ไม่มี `|`) ผลเท่าเดิม; verified ด้วยเทสต์เฉพาะที่ใส่ `|` ในชื่อไฟล์ + golden hash ไม่ขยับ.
- **Priority:** กลาง

### F4 — LLM ล้มชั่วคราวต้อง “degrade” ไม่ใช่ “error” 🟡
- **Current risk:** หลัง `available()` ผ่านแล้ว ถ้า `chat()` timeout/เน็ตหลุด → exception หลุดไป base.Agent → `status=error`. แล้ว SuperAgent QA จะรายงานว่า “ระบบทำงานไม่ครบ/มี agent ล้ม” ทั้งที่เป็นแค่ LLM สะดุดชั่วคราว (ชั้น advisory ล้วน).
- **Root cause:** ไม่มีการดัก exception รอบ `chat()` ในตัว agent (ปล่อยให้ error boundary จับ ซึ่งจัดเป็น error).
- **Long-term impact:** สัญญาณ QA หลอก (false alarm) ลดความน่าเชื่อถือของ SuperAgent verdict; ผู้ใช้เข้าใจผิดว่างานพัง.
- **Recommended solution (ที่ทำ):** ห่อ `chat()` — ai_review → `skipped`, synthesis → ตกไปใช้ “สรุปสถิติ” (statistical fallback ที่มีอยู่แล้ว), super → ข้ามเฉพาะบท LLM brief (ผล deterministic ยังครบ).
- **Migration risk:** ต่ำ. สอดคล้องปรัชญา degrade-graceful เดิมของระบบ; กรณีไม่มี LLM (ปกติ) hash ไม่เปลี่ยน (verified).
- **Priority:** กลาง

### F5 — ลบ `source="drive"` ที่ dead/ทำให้เข้าใจผิดใน `run_agents.py` 🟡
- **Current risk:** ตัวรันนี้ resolve `file_list` เองเสมอจาก `--files/--data` แล้วส่งเข้า pipeline → `ImportAgent` ไม่เคยอ่านสาขา `source`. ค่า `"drive"` จึงไม่ทำงานจริง แต่ทำให้ผู้อ่านเข้าใจผิดว่าโปรแกรมไปดึงไฟล์จาก Google Drive.
- **Root cause:** ตัวเลือกตกค้างจากโหมดโต้ตอบเดิม.
- **Long-term impact:** เข้าใจผิดเชิงปฏิบัติการ (operator confusion), debug ยาก.
- **Recommended solution (ที่ทำ):** ลบคีย์ออก + ใส่คอมเมนต์อธิบายว่า `file_list` ถูก resolve ในตัวรันแล้ว.
- **Migration risk:** ไม่มี (เป็น dead key).
- **Priority:** กลาง-ต่ำ

### F6 — กัน `notepad_report` crash จากค่า `None` (latent) 🔵
- **Current risk:** `f"{t.get('rank'):>2}"` / `f"{t.get('priority'):>5}"` จะ `TypeError` ถ้าคีย์หาย. ปัจจุบัน SuperAgent ใส่ค่าให้เสมอ → ยังไม่เกิด แต่เปราะถ้า schema summary เปลี่ยน.
- **Root cause:** format ตัวเลขตรง ๆ โดยไม่กัน None.
- **Long-term impact:** รายงาน Notepad (advisory) อาจล้มในอนาคตจากการเปลี่ยน upstream.
- **Recommended solution (ที่ทำ):** cast เป็น `str(...)` ก่อนจัดความกว้าง — ผลกรณีปกติเหมือนเดิมเป๊ะ, กรณีคีย์หายแสดง `-` แทน crash.
- **Migration risk:** ไม่มี (เอาต์พุตปกติไม่เปลี่ยน).
- **Priority:** ต่ำ

### F7 — ลบสมาชิกซ้ำใน `COMPANY_TYPO_PREFIXES` 🔵
- **Current risk:** `('บริษัส','บริสัท','บริษาท','บริษัส')` — `'บริษัส'` ซ้ำ. ใช้เชิง membership เท่านั้น → ผลเหมือนเดิม แต่เป็น dead/สับสน.
- **Root cause:** พิมพ์ตกค้าง.
- **Long-term impact:** สับสนเวลาบำรุงรักษา/นับสถิติ prefix.
- **Recommended solution (ที่ทำ):** ตัดตัวซ้ำ + คอมเมนต์กำกับว่า “ลำดับ/ตัวซ้ำไม่มีผลต่อผลตรวจ”.
- **Migration risk:** ไม่มี (membership เหมือนเดิม; golden hash ไม่ขยับ — verified).
- **Priority:** ต่ำ

---

## 5. ประเด็นที่ “แนะนำแต่ตั้งใจไม่แตะ” (เครื่องยนต์ที่ถูก golden-protected)

หลักการ Production Reliability: **ไม่แก้แกนที่ถูก fingerprint บนข้อสันนิษฐาน** หากไม่ใช่เหตุวิกฤต. รายการต่อไปนี้เป็น latent/ต่ำ และอยู่ในไฟล์ที่ถูกล็อกด้วย golden hash — ควรแก้ผ่านขั้นตอน `golden_master → verify_golden → regression_full` พร้อมรีวิวหน้าตารายงานด้วยตา.

- **F8 (`thai_text.gen_explanation`)** — พารามิเตอร์ชื่อ `state` บัง module `state`. ไม่ใช่บั๊ก (ฟังก์ชันไม่ใช้ module ภายใน) แต่ควรเปลี่ยนชื่อพารามิเตอร์เป็น `state_name` เพื่ออ่านง่าย.
- **F9 (`webverify.run_product_verification`)** — sqlite `conn` ควรอยู่ใน `try/finally: conn.close()` กัน leak ถ้า exception หลุดก่อนปิด (ชั้น online เสริม ไม่อยู่ใน critical path).
- **F10 (`master.validate_master_entry`)** — ใส่ guard `tc = clean_tax_id(tax_id) or ""` ก่อน `len(tc)` กัน `None` (flow โต้ตอบปัจจุบันส่ง `""` จึงยังไม่เกิด).
- **เอกสารไม่ตรงโค้ดเล็กน้อย:** `HANDOVER_TH.md` ระบุ baseline 81 ไฟล์ = `7b60b01f…` แต่สภาพแวดล้อมจริง (ไลบรารีตาม pin) ให้ `ec61907f…` ซึ่งตรงกับค่าที่ฝังใน `orchestrator.py` เป๊ะ. แนะนำอัปเดต HANDOVER ให้ตรง (นับ metrics ทั้งหมดตรงกัน — ต่างเฉพาะค่า hash จาก environment ที่ใช้ generate baseline).

---

## 6. หลักฐานการทดสอบ (Verification Evidence)

รันบนเครื่องยนต์จริง + ข้อมูลจริง 81 ไฟล์ (`/mnt/project`) หลังติดตั้งไลบรารีตาม pin (ผ่าน version-gate):

```
golden_master.py  (engine path, FIXED) → ec61907fd8061bd314b4e4c573a40f4564184936e292c8d6323b5278239e4628
verify_golden.py  (AGENT path, FIXED)  → ec61907f…   AGENT == BASELINE : ✅
regression_full.py                     → engine == agent == baseline : ✅✅✅
                                          BILLS=632 FILES=81 dup=1 iv_seq=26 iv_date=0 typos=34 companies=2
test_agents.py        ผ่าน 38 / ล้มเหลว 0   (isolation/degrade/tier-2/tier-3/super/mesh/determinism/notepad)
smoke_test.py         ผ่าน 27 / ล้มเหลว 0   (packaging + import-gate 22 symbols + ฟังก์ชันหลัก)
test_mesh_contract.py ผ่าน 16 / ล้มเหลว 0   (Tier-1 producer contract — ครอบ mesh.py ที่แก้)
test_pinned_logic.py  ผ่าน 48 / ล้มเหลว 0   (pinned date logic, reproducible)
pure-layer import (ไม่มีเครื่องยนต์) : 13/13 โมดูลบริสุทธิ์ import ได้  ← พิสูจน์ผล F1
```

**ข้อสรุปสำคัญ:** การแก้ทั้งหมดอยู่ในชั้น advisory และ **ไม่เปลี่ยนผลตรวจที่ออก Excel แม้แต่บิตเดียว** (hash เท่าเดิม).

---

## 7. วิธีตรวจซ้ำด้วยตัวเอง (Reproduce)

```bash
cd ปุ้มปุ้ย_v9_multiagent
pip install -r requirements.txt -c constraints.txt        # ให้ผ่าน version-gate (สำคัญต่อ hash)

PYTHONHASHSEED=0 python3 golden_master.py . out.json /mnt/project        # → ec61907f…
PYTHONHASHSEED=0 python3 verify_golden.py . out.json /mnt/project        # → AGENT == BASELINE ✅
PYTHONHASHSEED=0 python3 regression_full.py . /mnt/project out.json      # → engine==agent==baseline ✅
PYTHONHASHSEED=0 python3 test_agents.py . /mnt/project                   # → 38/38
PYTHONHASHSEED=0 python3 smoke_test.py                                   # → 27/27
```

ดูรายละเอียดการเปลี่ยนแปลงทุกบรรทัดได้ที่ **`CHANGES_v9_1_AUDIT.diff`** (แนบในแพ็กเกจ).

---

## 8. ภาคผนวก — ไฟล์ที่แก้ (รวม 12 ไฟล์)

| ไฟล์ | การเปลี่ยน | finding |
|------|-----------|---------|
| `agents/_shared.py` | **ไฟล์ใหม่** — helper กลาง (parse_llm_json/SEV_RANK/max_severity/bill_key) | F2 |
| `agents/__init__.py` | lazy `__getattr__` (PEP 562) | F1 |
| `agents/mesh.py` | เก็บ `_bill_ref` แทน split คีย์ + ใช้ shared rank/bill_key | F2, F3 |
| `agents/confidence_agent.py` | `per_bill_ref` แทน split + shared bill_key | F2, F3 |
| `agents/ai_review_agent.py` | shared parse/rank + degrade `chat()` | F2, F4 |
| `agents/synthesis_agent.py` | shared parse + degrade `chat()`→statistical | F2, F4 |
| `agents/super_agent.py` | shared parse/rank/bkey + กัน LLM brief ล้ม | F2, F4 |
| `agents/vat_agent.py` | ใช้ shared `max_severity` (ลบสำเนา) | F2 |
| `agents/taxid_agent.py` | ใช้ shared `max_severity` (ลบสำเนา) | F2 |
| `agents/notepad_report.py` | shared SEV_RANK + กัน None format | F2, F6 |
| `config.py` | ตัดสมาชิกซ้ำใน COMPANY_TYPO_PREFIXES | F7 |
| `run_agents.py` | ลบ `source="drive"` ที่ dead | F5 |

— จบรายงาน —
