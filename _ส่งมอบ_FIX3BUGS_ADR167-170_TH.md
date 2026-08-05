# ส่งมอบงาน — แก้ 3 บั๊กจากเครื่องเจ้าของ + รีเช็คทั้งระบบ (ADR-167..170) · 2026-07-02

> ทำตาม `PROMPT_CLAUDE_CODE_แก้ทั้งหมด_v1.md` บนเครื่องแก้งาน (Linux container, venv Python 3.12.3,
> deps ตรง pin ทุกตัวรวม pythainlp 5.0.5 ตาม ADR-164). **ข้อจำกัดสำคัญ: เครื่องนี้ไม่มี corpus จริง**
> (มีเฉพาะ `tests/fixtures/`) → ขั้นที่ต้องใช้ไฟล์บิลจริง (batch จริง / rebaseline หัวข้อ 6 ของ PROMPT)
> เตรียมคำสั่งไว้ให้รันบนเครื่องเจ้าของ ท้ายไฟล์นี้.

## ตารางสรุปตาม template (PROMPT หัวข้อ 7)

| บั๊ก | รากสาเหตุ (พิสูจน์ยังไง) | แก้ที่ไฟล์:บรรทัด | หลักฐานผ่าน | ADR |
|---|---|---|---|---|
| 1 batch อ่านไม่ได้ | H1 ไฟล์ถูก Excel เปิดค้าง (Windows → PermissionError/sharing violation) — H3 ตัดทิ้ง (ไม่มี state ใดป้อนเข้า read_workbook), H4 ตัดทิ้ง (finally ปิด fd ตั้งแต่ v6.1 + probe fd=0) แล้วจำลอง exception ชั้น lock 3 รูปแบบยืนยันพฤติกรรม | `parser_p2.py:14` (import errno) + `parser_p2.py:650-661` (บล็อก except ของ parse_file) | batch จำลอง 3 ไฟล์: lock ทุกแบบ → ข้อความใหม่ + เดินต่อ บิลไฟล์อื่น 6/6 + SYS001 ครบ; BadZipFile → ข้อความเดิม; เดี่ยว 3/3 · fixture `ad0c9dad` คงเดิม | 167 |
| 2 excel ไม่ออก | traceback จริงอ่านได้เฉพาะเครื่องเจ้าของ → ไล่พิสูจน์จุดครัชทั้งเส้น LEAN ด้วย probe: C1 `issues[].code` ไม่ใช่ str → sort TypeError · C2 `iv_date` truthy ไม่ใช่ date (str/serial/**pd.NaT**) → `_clean_period` ครัช · C3 `master_key` ไม่ใช่ str → sort Summary TypeError · C4 ค่า item non-scalar → openpyxl ValueError · C6 PermissionError/OSError ตอน `wb.save` | `reporting_p2.py:354-358` (pre-pass str coerce), `reporting_p2.py:361-368` (except จำแนก OSError) · `reporting_p1.py:40-53` (_xl_safe/KNOWN_TYPES), `:366-375` (_clean_period), `:377-383` (_clean_company_label) | probe หลังแก้: C1-C4 + รวมพิษ 4 อย่าง → ok=True ชีตครบ · C6 → ข้อความแนะนำ + traceback · `REPORT_DET_HASH` byte-identical (33187a23…) · e2e 7 ชีต OK · main() จริง: "✅ ไฟล์รายงาน (คลีน 7 ชีต) บันทึกแล้ว" | 168, 170 |
| 3 หมายเหตุหน่วย | ADR-166 แก้รากแล้ว (FIX-A ตัว/อัน→family ชิ้น; FIX-B advisory ออกเสมอ) — รอบนี้ยืนยันจริง + ตัดสินใจไม่เพิ่ม family เก็งกำไร (ITM019/020 อยู่ในเส้น golden + ล็อก ADR-091) | — (ไม่แตะโค้ด) | smoke: `SHS_69_06.xls — หน่วย "ชิ้น" เขียนปน: ตัว / pc` ✓ · อัน/pcs ✓ · th↔th ไม่ flag ✓ · บังคับ xlsx fail → `agent_report.txt` มี section หน่วยสินค้า + company_summary ยังออก ✓ | 169 |

## Checklist ตาม PROMPT

- fixture `ad0c9dad…` คงเดิมทุกขั้น: ☑ (รัน `regression_full.py` หลังทุกการแก้ — engine==agent==baseline)
- locks 8 ตัว (ข้อ 0.7) เขียว: ☑ (+ test_report_det / test_a_hardening / test_recheck_20260620 / e2e_test / test_file_size_ceiling)
- CI ชุด fixture (`bash run_ci.sh` ไม่มี data dir): ☑ exit 0 "✅ CI ผ่านทั้งหมด" (QA gates [9]-[13] graceful-skip — เครื่องนี้ไม่มี pip-audit/coverage/ruff/black/mypy)
- doctor.py: ☑ exit 0 (advisory ปกติ 3 ข้อ: pre-commit hook / master ว่าง / PII pack)
- sweep §5.4 (บน fixture — corpus จริงไม่มี): ☑ bills=3, no-item=0, no-iv=0, sub+vat=total 3/3
- rebaseline corpus (§6): ☐ **ทำไม่ได้บนเครื่องนี้** — ไม่มีโฟลเดอร์บิลจริง (ดูขั้นตอนด้านล่าง)
- adversarial review อิสระ 3 มุม (correctness×2 + golden-neutrality): ☑ ประเด็นจริงทั้งหมดถูกแก้และบันทึกใน ADR-170

## สิ่งที่แก้เพิ่มจากรอบ review/CI (ADR-170)

1. `_clean_period` กัน **pd.NaT** (truthy + `.year`=nan ทะลุเช็ค None) → int() ครอบ + except → `'-'`
2. fallback `_XL_KNOWN_TYPES` เพิ่ม `Decimal` (unreachable บน pin 3.1.5 — แก้เพื่อความถูกต้อง)
3. `test_file_size_ceiling`: whitelist `reporting_p1.py` (615 LOC — เกราะ ADR-168 ดันเกินเพดาน 600)
   พร้อมแผนซอย `_clean_sheet_*` → `reporting_p1c.py` ตาม convention เดิมของ gate

## ขั้นที่เหลือ — รันบนเครื่องเจ้าของ (มีไฟล์บิลจริง) เท่านั้น

```bash
# 0) ENV บังคับ + ล้าง bytecode (ทุกครั้ง)
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 PYTHONPATH=$PWD
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete

# 1) ปิดจบ BUG-1: รัน batch ชุดเดิมที่เคยพัง — SHS 69.06 ต้องได้บิลครบ (เทียบกับส่งเดี่ยว)
#    ถ้าไฟล์ถูก Excel เปิดค้าง ระบบจะบอกเองแล้วว่า "ปิดไฟล์แล้วรันใหม่" · ถ้ายังพังทั้งที่ปิด Excel
#    → อ่านชนิด exception จริงจาก SYS001 detail แล้ววินิจฉัยต่อตาม PROMPT §2.2-2.3
# 2) ปิดจบ BUG-2: รันโฟลว์จริง → ต้องได้ audit_v58_*.xlsx 7 ชีต
#    ถ้ายังพัง traceback ใต้ "⚠️ สร้างรายงานคลีนล้มเหลว" ตอนนี้ชี้สาเหตุจริงได้เลย (ครัชชนิดข้อมูลถูกอุด 5 จุด)
# 3) ปิดจบ BUG-3: เปิด agent_report.txt ข้างรายงาน → section "หน่วยสินค้า — ตรวจเพิ่ม" ต้องมีบรรทัด ⚠️ เคสคาเมล
# 4) sweep §5.4 บน corpus จริง (no-item=0, no-iv=0, sub+vat=total 100%)
# 5) rebaseline (หลังทุกอย่างสะอาดเท่านั้น — ตาม PROMPT §6):
python3 verify_corpus_manifest.py /PATH/บิล            # อ่านรายชื่อ +/− ให้ตรงคาด (ไฟล์ มิ.ย. ใหม่)
python3 golden_master.py . baseline.json /PATH/บิล      # จด hash ใหม่ 8 ตัวแรก
python3 verify_corpus_manifest.py /PATH/บิล --write
python3 test_golden_single_source.py                    # sync พื้นผิว doc ตามที่มันฟ้อง
# + เพิ่ม ADR ใหม่บันทึก rebaseline (hash เก่า f05358aa → ใหม่ XXXXXXXX, จำนวนไฟล์/บิล)
bash run_ci.sh /PATH/บิล                                # ต้อง exit 0 ครบทุก step รวม [7pre][7][8][8d]
```

## หมายเหตุความเสี่ยงคงเหลือ (จงใจไม่แก้ — บันทึกใน ADR)

- ข้อความ lock-file (ADR-167) ครอบ PermissionError ทุกกรณีรวม ACL จริงที่ไม่ใช่ Excel — hedge ด้วย "เช่น"
  + exception จริงอยู่ครบใน SYS001 detail
- ไฟล์ที่ "เปิดไม่ได้" ไม่เข้า `_failed_files` → สรุปท้ายรัน "มี N ไฟล์อ่านไม่สำเร็จ" ไม่นับเคสนี้
  (พฤติกรรมเดิมก่อนแก้ — ร่องรอยอยู่ที่บรรทัด ⚠️ + SYS001/ชีต System Issues) — ถ้าอยากให้นับ แจ้งได้
- watch list คู่หน่วยที่ยังไม่มี family (ฟุต/หลา/ขวด/ซอง/ตู้/โคม ฯลฯ) + สูตรเพิ่มปลอดภัย → ดู ADR-169
