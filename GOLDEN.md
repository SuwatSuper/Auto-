# 🔒 GOLDEN — แหล่งความจริงเดียวของค่า hash (อ่านตรงนี้ก่อน "ตื่นตูม")

> เห็นค่า hash ที่ไหนแล้วสงสัยว่า *"ระบบเพี้ยนหรือเปล่า?"* — เช็คที่นี่ที่เดียวจบ.
> เอกสารเก่าหลายฉบับมี hash คนละค่า นั่น **ปกติ** (เป็นบันทึกอดีต) — ค่าที่ "จริงตอนนี้" มีค่าเดียว ดูด้านล่าง.

---

## ✅ ค่าที่ถือเป็น "จริง" ตอนนี้ = `baseline.json._sha256`

อย่าเชื่อเอกสาร — **เชื่อไฟล์** เช็คของจริงเสมอด้วยคำสั่งนี้:

```bash
python3 -c "import json;print(json.load(open('baseline.json'))['_sha256'])"
# ปัจจุบัน: f05358aa...  (golden ทางการ: 152 ไฟล์ /mnt/project, 1153 บิล — master ว่าง ไม่มีบริษัทฝัง)
```

ยืนยันบนข้อมูลจริง (ต้องได้ค่าเดียวกันนี้ทั้ง 3 บรรทัด):

```bash
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . <โฟลเดอร์ 152 ไฟล์>
```

---

## 🧭 hash อื่นๆ ที่คุณ "อาจเห็น" และมันคืออะไร (ไม่ใช่บั๊ก)

| hash (prefix) | คืออะไร | ตรวจด้วย |
|---|---|---|
| **`f05358aa`** | ✅ **golden ปัจจุบัน** — 152 ไฟล์ / 1153 บิล — rebaseline 2026-07-01 (ADR-157: **+2 typo** ยืนยัน 4 ทาง [ค้นเน็ตคำผิดตรงๆ 0 ร้านใช้ · OOV พจนานุกรม 62k · near-duplicate · อ่านมือ 1,257 ชื่อ] — บุซซิ่ง→บุชชิ่ง [TKH/TSH_69_052] · แคลมปึ→แคลมป์ [KNT_69_012] : **+4 flag ITM010 · FP=0** · fixture `ad0c9dad` ไม่ขยับ) · รวม corpus refresh 148→152 (บิลเดือน 06 เพิ่ม) · path-independent (ADR-037) | `regression_full.py . <data>` |
| `23b315e8` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-07-01 (ADR-157 — +2 typo บุซซิ่ง/แคลมปึ +4 flag ; corpus refresh 148→152) — ปลดระวาง · เคยเป็น golden ของ ADR-123 (เคลียร์คำก้ำกึ่ง กลุ่ม B −34 + กลุ่ม A หล็กฉาก +1) · path-independent (ADR-037) | — |
| `757751e7` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-28 (ADR-123 — เคลียร์คำก้ำกึ่ง: กลุ่ม B เลิกฟ้อง −34 + กลุ่ม A หล็กฉาก +1) — ปลดระวาง · เคยเป็น golden ของ ADR-122 (เพิ่มกฎ VAT012/ADDR010/ADDR007 + total_text) · path-independent (ADR-037) | — |
| `0c575c61` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-28 (ADR-122 — เพิ่มกฎ VAT012/ADDR010/ADDR007 + total_text) — ปลดระวาง · เคยเป็น golden ของ ADR-121 (เลิกฟ้อง "เจียร์" −6) · path-independent (ADR-037) | — |
| `d8adc143` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-28 (ADR-121 — เลิกฟ้อง "เจียร์") — ปลดระวาง · เคยเป็น golden ของ ADR-119 (BUG-1 ตัด FP "บสังกะสี" คลาสตัดคำ −1) + ADR-120 (GAP-A กฎครัช non-str → false-negative, golden-neutral) · path-independent (ADR-037) | — |
| `31013a31` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-28 (ADR-119 — ตัด FP "บสังกะสี" คลาสตัดคำ) — ปลดระวาง · rebaseline 2026-06-27 (ADR-104/105/106: ITM020 +52 + ITM019 +9 + P2 ZWNJ/header unit-data-quality) · path-independent (ADR-037) | — |
| `9aded0ad` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-27 (ADR-104/105/106 — เพิ่ม ITM020 + P2 unit-data-quality) — ปลดระวาง · rebaseline 2026-06-26 (ADR-102: ลบบริษัทตัวอย่าง ฉี อัน ออกจาก `golden_snapshot.MASTER` → master ว่าง `{}` · CMP006 −50) · path-independent (ADR-037) | — |
| `d0330308` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-26 (ADR-102 — ลบ master ฉี อัน → master ว่าง) — ปลดระวาง · rebaseline 2026-06-24 (ADR-095: completeness check — อ่าน token len=2 ครบ + singleton ที่ค้าง → `สึตำ→สีดำ`·`เปือย→เปลือย`·`เหลือง-ตำ→เหลือง-ดำ` +4 flag, FP=0) · path-independent (ADR-037) | — |
| `a5b39d00` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-24 (ADR-095 — +3 typo completeness) — ปลดระวาง · rebaseline 2026-06-24 (ADR-094: เพิ่ม typo 16 ตัวจาก **exhaustive scan ทุก token (923 คำ) ทุกไฟล์** + OOV เทียบ wordlist ราชบัณฑิต 62k → +31 flag, FP=0) · path-independent (ADR-037) | — |
| `5f23e9f4` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-24 (ADR-094 — +16 typo exhaustive) — ปลดระวาง · rebaseline 2026-06-24 (ADR-092: typo `วาวล์→วาล์ว`·`แป็ป→แป๊บ`·`ครีลิ→คริลิ` +9, FP=0) · ADR-093 พิจารณา ยิปซั่ม แล้ว **คงไว้** (industry-canonical) · path-independent (ADR-037) | — |
| `587db268` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-24 (ADR-092 — +3 typo ชื่อสินค้า) — ปลดระวาง · rebaseline 2026-06-23 (ADR-087 F1: ITM005 `_kw_in_name('สี')`+คำบอกสีล้วน exclusion → ลบ false-positive −64 [สวิตช์/สายไฟ/ท่อ/กระเบื้อง/ซิลิโคน], recall คงเดิม, collateral 0) · path-independent (ADR-037) | — |
| `853ce4ab` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-23 (ADR-087 — F1 ITM005 สีล้วน exclusion) — ปลดระวาง · rebaseline ADR-084 (whitelist `'สวิตซ์'`) · path-independent (ADR-037) | — |
| `08e6abfd` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-23 (ADR-084 — สวิตซ์ whitelist) — ปลดระวาง · path-independent (ADR-037) · rebaseline 2026-06-22 (ADR-064..076 deep audit: M-1 r_dt003 ระเบิดเวลา ค.ศ.2031 + ลด false-positive ITM004 ["5นิ้ว"/"60x30มม."=เขียนไทยปกติ] · ITM010 "วาว" [ประกายวาว] · ITM016 dup-key+qty/amount · DT004 4-หลักกำกวม · non-finite money guard [inf/NaN] · ADDR005 ตัดเบอร์โทร · DOC003 ไม่มีวันที่) · ฐาน 148 ไฟล์ ADR-048 | `regression_full.py . <data>` |
| `ae84d3f0` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-22 (ADR-064..076 — M-1 time-bomb fix + FP-reduction batch ITM004/ITM010/ITM016/DT004/ADDR005/DOC003 + non-finite guard) — ปลดระวาง | — |
| `c50fec27` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-21 (ADR-058 — DOC001 SHORT-format FP guard; ลบ TNT_69_03 "2" + TSH_69_039 "1") — ปลดระวาง | — |
| `be6398d2` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-20 (ADR-057 — DOC001 LONG sub-index false-positive guard; ลบ TNT 5.1/5.2) — ปลดระวาง | — |
| `0563245c` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-20 (ADR-056 — whitelist บริสุทธิ์/กระเบื้องพื้น) — ปลดระวาง | — |
| `ba9deda0` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-20 (ADR-055 — money-serial 43600→date misread ใน _pb_scan_header; แทน DT004+DOC001+IV004(false) ด้วย DT006 ต้นตอ) — ปลดระวาง | — |
| `ddd06191` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-19 (ADR-051 — DT001 "012": int("012")=12 อ่านเป็น ธ.ค.ผิด บิลเป็น ม.ค. → ลบ false positive 22; ITM007/ITM015→advisory) — ปลดระวาง | — |
| `df91493f` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline 2026-06-19 (ADR-048 — corpus 106→148, BR สํา nikhahit, TKH discount qty misread) — ปลดระวาง | — |
| **`ad0c9dad`** | ✅ **fixture golden ปัจจุบัน** (3 บิล, เร็ว — ไม่ต้องใช้ข้อมูลจริง) — rebaseline 2026-06-28 (ADR-122: เพิ่ม field total_text + ADDR010 flag จังหวัด 'ทดสอบ'/'สาม' [ชื่อ synthetic ในเทส = ไม่ใช่จังหวัดจริง → ฟ้องถูก]) | `INVARIANTS/check_invariants.py` |
| `72cb832c` | ⏮️ fixture golden **ก่อน** rebaseline 2026-06-28 (ADR-122 — total_text + ADDR010 synthetic) — ปลดระวาง · เคย rebaseline 2026-06-26 (ADR-102 — ลบ master ฉี อัน) | — |
| `b5c415bb` | ⏮️ fixture golden **ก่อน** rebaseline 2026-06-26 (ADR-102 — ลบ master ฉี อัน → master ว่าง) — ปลดระวาง · rebaseline ADR-058 (ชีต 2/4/6 เลิกฟ้อง DOC001) | — |
| `269ddaed` | ⏮️ fixture golden **ก่อน** rebaseline 2026-06-21 (ADR-058 — SHORT-format DOC001 guard) — ปลดระวาง | — |
| `fff69fc6` | report hash (รายงาน Excel, normalize timestamp) | `verify_report_det.py` |
| `ec61907f` | golden ของ corpus **ย่อย 81 ไฟล์** (คนละชุดข้อมูล — ไม่ใช่ค่าผิด) | เครื่องที่มีชุด 81 ไฟล์ |
| `662c9132` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline 2026-06-18 (ADR-047 — CMP006 ตัดชื่อ บจ. ยาวกลางคำ "จำกัด"→"จำ") — ปลดระวาง | — |
| `bb042554` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline 2026-06-18 (ADR-046 — F-1 ปัดเงิน round()→HALF_UP, F-2 provenance) — ปลดระวาง | — |
| `d6b23d12` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline 2026-06-18 (ADR-044 — TNT_69_03 float-tail IV misread) — ปลดระวาง | — |
| `d3c01886` | ⏮️ golden 106 ไฟล์ ก่อน portable v9.3 (hash ผูก path — ADR-037) — ปลดระวาง | — |
| `35b2f7c8` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline 2026-06-10 (ADR-036) — ปลดระวาง | — |
| `73f5bf87` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline (ADR-021) — ปลดระวาง | — |
| `f1ac8421` | ⏮️ golden 106 ไฟล์ รุ่น v9.1 — ปลดระวาง | — |
| `7b60b01f` | ⏮️ golden รุ่นเก่ามาก — ปลดระวาง | — |

> ค่าที่ขึ้น ⏮️ "ปลดระวาง" จะพบได้ใน **เอกสารประวัติ** (AUDIT_*/CHANGELOG/HANDOFF/ADR ledger)
> ซึ่ง **ถูกต้องตามเวลาที่เขียน** — ไม่ใช่ค่าปัจจุบัน และจงใจไม่เขียนทับ (เก็บไว้เป็นบันทึก).

---

## 📏 กฎเหล็ก (กัน drift / กันตื่นตูม)

1. **แหล่งความจริงเดียว** = `baseline.json._sha256`. เอกสารทุกฉบับอ้างอิงมัน ไม่ใช่ตรงข้าม.
2. **พื้นผิว operational** (README / `.vscode/tasks.json` / `constraints.txt` / version_gate ฯลฯ)
   ถูกบังคับให้ตรง `baseline.json` อัตโนมัติด้วย **`test_golden_single_source.py`** (อยู่ใน CI).
   ลืมอัปเดต → CI แดงทันที ไม่ใช่รู้ตอน ship.
3. **เอกสารประวัติ** เก็บ hash เก่าได้ (เป็นหลักฐานอดีต) — ไม่ถูกสแกน, ห้ามเขียนทับ.
4. **จะ re-baseline:** แก้ `baseline.json` แล้วรัน `test_golden_single_source.py` —
   มันจะบอกชัดว่าต้องอัปเดตพื้นผิว operational ตัวใดบ้างให้ตรงค่าใหม่.


---

## 🔍 golden ข้อมูลจริงไม่ reproduce — "data drift" หรือ "code drift"? [ADR-158]

golden ข้อมูลจริง (`baseline.json`) ผูกกับ corpus สดใน `/mnt/project`. ถ้ามันไม่ reproduce **อย่าเพิ่งตกใจว่า code พัง** — เช็คก่อนว่า corpus เปลี่ยนไหม:

```bash
python3 verify_corpus_manifest.py /mnt/project
```

- **MATCH** → corpus ตรง manifest → golden *ต้อง* reproduce. ถ้ายังแดง = **CODE DRIFT** (บั๊กจริง ต้องสืบ)
- **DRIFT** → corpus เปลี่ยน (tool จะลิสต์ไฟล์ที่ เพิ่ม/ลบ/แก้) → golden *คาดว่าจะเปลี่ยน* = **DATA DRIFT ปกติ ไม่ใช่บั๊ก**
  - ตั้งใจเปลี่ยน (เพิ่มบิลเดือนใหม่) → rebaseline: `golden_master.py . baseline.json /mnt/project` แล้ว `verify_corpus_manifest.py /mnt/project --write` แล้ว `test_golden_single_source.py`
  - ไม่ได้ตั้งใจ → restore ไฟล์ให้ตรง manifest

**fixture golden (`ad0c9dad`) ไม่ผูก corpus** → reproduce เสมอไม่ว่า corpus จะเปลี่ยนแค่ไหน = ตัวพิสูจน์ code ที่แท้จริง (CI ใช้ตัวนี้เป็นหลัก · `run_ci.sh` ไม่ต้องมี corpus ก็เขียวได้)
