# 🔒 GOLDEN — แหล่งความจริงเดียวของค่า hash (อ่านตรงนี้ก่อน "ตื่นตูม")

> เห็นค่า hash ที่ไหนแล้วสงสัยว่า *"ระบบเพี้ยนหรือเปล่า?"* — เช็คที่นี่ที่เดียวจบ.
> เอกสารเก่าหลายฉบับมี hash คนละค่า นั่น **ปกติ** (เป็นบันทึกอดีต) — ค่าที่ "จริงตอนนี้" มีค่าเดียว ดูด้านล่าง.

---

## ✅ ค่าที่ถือเป็น "จริง" ตอนนี้ = `baseline.json._sha256`

อย่าเชื่อเอกสาร — **เชื่อไฟล์** เช็คของจริงเสมอด้วยคำสั่งนี้:

```bash
python3 -c "import json;print(json.load(open('baseline.json'))['_sha256'])"
# ปัจจุบัน: ae84d3f0...  (golden ทางการ: 148 ไฟล์ /mnt/project, 1056 บิล)
```

ยืนยันบนข้อมูลจริง (ต้องได้ค่าเดียวกันนี้ทั้ง 3 บรรทัด):

```bash
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . <โฟลเดอร์ 148 ไฟล์>
```

---

## 🧭 hash อื่นๆ ที่คุณ "อาจเห็น" และมันคืออะไร (ไม่ใช่บั๊ก)

| hash (prefix) | คืออะไร | ตรวจด้วย |
|---|---|---|
| **`ae84d3f0`** | ✅ **golden ปัจจุบัน** — 148 ไฟล์ / 1056 บิล — path-independent (ADR-037) · rebaseline ADR-058 (DOC001 SHORT-format false-positive guard: ชื่อชีตเลขล้วน "2"=เทมเพลตก๊อป [TNT_69_03] · "1"=บิลเดี่ยว [TSH_69_039] ถูกอ่านเป็น "วัน" ผิด — guard ด้วย corroborated day-naming ≥2 ชีต + ไม่มี Excel copy-sibling → ลบ 2 FP; true positive [SHS_68_02 "6"] ครบ) · ฐาน 148 ไฟล์ ADR-048 | `regression_full.py . <data>` |
| `c50fec27` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-21 (ADR-058 — DOC001 SHORT-format FP guard; ลบ TNT_69_03 "2" + TSH_69_039 "1") — ปลดระวาง | — |
| `be6398d2` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-20 (ADR-057 — DOC001 LONG sub-index false-positive guard; ลบ TNT 5.1/5.2) — ปลดระวาง | — |
| `0563245c` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-20 (ADR-056 — whitelist บริสุทธิ์/กระเบื้องพื้น) — ปลดระวาง | — |
| `ba9deda0` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-20 (ADR-055 — money-serial 43600→date misread ใน _pb_scan_header; แทน DT004+DOC001+IV004(false) ด้วย DT006 ต้นตอ) — ปลดระวาง | — |
| `ddd06191` | ⏮️ golden 148 ไฟล์ **ก่อน** rebaseline 2026-06-19 (ADR-051 — DT001 "012": int("012")=12 อ่านเป็น ธ.ค.ผิด บิลเป็น ม.ค. → ลบ false positive 22; ITM007/ITM015→advisory) — ปลดระวาง | — |
| `df91493f` | ⏮️ golden 106 ไฟล์ **ก่อน** rebaseline 2026-06-19 (ADR-048 — corpus 106→148, BR สํา nikhahit, TKH discount qty misread) — ปลดระวาง | — |
| **`b5c415bb`** | ✅ **fixture golden ปัจจุบัน** (3 บิล, เร็ว — ไม่ต้องใช้ข้อมูลจริง) — rebaseline ADR-058 (ชีต 2/4/6 เลิกฟ้อง DOC001) | `INVARIANTS/check_invariants.py` |
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
