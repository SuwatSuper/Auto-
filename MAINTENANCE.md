# MAINTENANCE — กฎโดยนัยที่คนดูแลต้องรู้ (ปุ้มปุ้ย v9.3.4)

> เอกสารนี้รวบ "กฎที่ต้องจำ" ซึ่งเดิมกระจายเป็นคอมเมนต์ติดป้ายเวอร์ชันหลายที่ — เพื่อให้ผู้รับช่วง
> เห็นภาพรวมในหน้าเดียว. **แหล่งความจริงของ ADR/ตัวเลข baseline ยังคงเป็น `INVARIANTS/DECISIONS.md`.**

## 0. กฎเหล็ก
1. **Golden hash ห้ามขยับโดยไม่ตั้งใจ.** ผลตรวจ (audit decision) ถูก fingerprint ด้วย SHA256.
   ทุกการแก้ "engine/leaf" ต้องผ่าน:
   ```
   PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
     python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json   # ad0c9dad… (fixture)
     python3 golden_master.py . /tmp/x.json /mnt/project                                # 23b315e8… (148 ไฟล์ ทางการ)
     python3 regression_full.py . <106-ไฟล์จริง>                                         # 23b315e8… (ทางการ)
   ```
2. **ออฟไลน์เป็นค่าตั้งต้น.** เน็ตเปิดได้เฉพาะตั้งใจผ่าน `PUOPUY_ALLOW_NETWORK=1` (ดู `offline_guard.py`).
3. **ห้ามเพิ่มฟีเจอร์** เว้นแต่ได้รับอนุญาตชัดเจน. งานคุณภาพ (เสถียร/น่าเชื่อถือ/บำรุงรักษา) มาก่อน.

## 1. แหล่งความจริงเดียว (อย่าทำซ้ำ)
| เรื่อง | อยู่ที่ | อย่าทำ |
|---|---|---|
| หมายเลขเวอร์ชัน | `config.APP_VERSION` | อย่าฮาร์ดโค้ด "vX.Y" ที่อื่น — อ่านจาก APP_VERSION |
| ลำดับศักดิ์สิทธิ์ของ audit | `run_audit_core()` ใน main | อย่าก๊อปลำดับไปไว้ที่อื่น (เดิมเคยเพี้ยน) |
| ลำดับความรุนแรง | `agents/_shared.SEV_RANK` + `config.SEVERITY_ORDER` | อย่าตั้งตารางใหม่ใน agent |
| helper ข้าม agent | `agents/_shared.py` (`max_severity/bill_key/parse_llm_json`) | อย่าก๊อปวางในแต่ละ agent |
| เวอร์ชัน lib ที่ล็อก | `config._LOCKED` (+ constraints.txt) | อย่าตั้งซ้ำใน version_gate |

## 2. กฎ "ต้องเรียกครั้งเดียว" (side-effect cross-checks)
ฟังก์ชันเหล่านี้ **เติม issue ลงบิลเป็น side-effect** → เรียกซ้ำ = issue ซ้ำ = hash เพี้ยน:
- `apply_iv_period_crosscheck` (DT004), `apply_sheet_date_crosscheck` (DOC001)
- `_iv_check_cross_day` (IV003), `_iv_check_ascending` (IV004) — เรียกผ่าน `check_invoice_sequence`

→ ใน pipeline เรียกผ่าน `_audit_core_crosschecks()` **ครั้งเดียว** เท่านั้น.
สัญญานี้ถูกตรึงด้วย **`test_crosscheck_idempotency.py`** (ถ้าใครเผลอเรียกซ้ำ golden tests จับ ;
ถ้าทำให้ idempotent เทสนี้ fail บังคับให้รับรู้).

## 3. lazy cache ต้องมี guard เสมอ
ทุกจุดที่อ่าน cache ใน `state.py` (`_CONSTRUCTION_DICT_BY_LEN`, `_PYTHAINLP_STEM_BLOCKLIST`,
`_CAT_KEYWORDS`, `_PRODUCT_WHITELIST`) **ต้อง** lazy-init ก่อน:
```python
if state._XXX is None: _build_xxx()
```
`reset_run_state()` ตั้งทั้งหมดกลับเป็น None ต้นรอบ (rebuild ได้ค่าเดิม เพราะ build จาก static dict/CFG).

## 4. determinism
- ตั้ง `PYTHONHASHSEED=0` ก่อนรันเสมอ (กัน set-iteration order เพี้ยน) — tie-break ถูกปักด้วย
  secondary key (`(len, name)`) แล้ว แต่ env นี้ยังเป็นมาตรฐานของทุก gate.
- โหมด golden/ทดสอบใช้ `PUOPUY_AUDIT_DATE=2026-06-02` (ปักวันตรวจ). production ไม่ตั้ง = ใช้วันนี้
  (ผลกฎวันที่จึงต่างตามวันรันโดยตั้งใจ).

## 5. ขนาน (parallel) opt-in
`parse_all_files_parallel` (ใน `parallel_audit.py`) ผลเท่า serial เป๊ะ (พิสูจน์: `verify_parallel.py`
+ `test_parallel_merge_nonempty.py`). ก่อนใช้จริงบนข้อมูลใหม่ ให้รัน `verify_parallel.py <data> <workers>`
ยืนยัน `serial == parallel` ก่อนเสมอ.

## 6. ชั้น advisory (agents) ไม่กระทบผลตรวจ
agent review/AI/synthesis/super เป็น **read-only** → ผลไปอยู่ใน mesh เท่านั้น. `ReportAgent` อ่านเฉพาะ
`(bills, summary, iv_issues, typos, filename_issues)` ไม่อ่าน mesh → เพิ่ม agent กี่ตัวก็ไม่ขยับ Excel.

## 7. รายการที่ "แนะนำแต่ยังเป็น Tier 2/อนาคต" (ต้อง golden gate + อนุมัติ)
- ✅ **(ทำแล้ว · ADR-017)** cross-check idempotent ด้วย `_append_issue_unique` — §2 ปลอดภัยเมื่อเรียกซ้ำแล้ว (เดิมเป็นรากของ non-idempotency).
- ✅ **(ทำแล้ว · ADR-017)** `webverify` sqlite `conn` ห่อ `try/finally` แล้ว (กัน leak).
- ⏳ **(รอ golden gate 148 ไฟล์ + อนุมัติ)** ลด hot loop ใน parser (`_dic_int_run`/`_row_label_match`) เพื่อ perf — แตะ parse core (byte-sensitive) ห้ามแก้แบบเดา.
