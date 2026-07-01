"""test_unit_lang_note.py — ล็อกพฤติกรรม company_unit_notes (ADR-091).

เจตนา (จาก comment เดิม notepad_report:264): หมายเหตุ "ปนไทย+อังกฤษ" = เตือนเมื่อ
"หน่วยเดียวกัน" ถูกเขียน 2 สคริปต์ (เช่น เมตร/m, กก./kg) = inconsistency จริง.
เดิม implementation flag เมื่อ "หน่วยไทยใดๆ + หน่วยอังกฤษใดๆ" อยู่ด้วยกัน → FP เมื่อ
'PCS'(ชิ้น) อยู่กับ 'เมตร'(ยาว) ซึ่งคนละหน่วย. เจ้าของยืนยัน: อังกฤษที่เห็นคือ "ชื่อสินค้า"
ไม่ใช่หน่วย. เทสนี้ตรึง: flag เฉพาะ family เดียวกันปรากฏทั้ง 2 สคริปต์.

golden-neutral: company_unit_notes อยู่ใน report layer (ไม่ถูกเรียกโดย rule engine).
"""
import sys
import unit_detection_ext as ux

_fail = []


def _check(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        _fail.append(msg)


def _bill(units):
    """สร้างบิลสังเคราะห์: 1 รายการต่อ 1 หน่วย (คิดเงินจริง)."""
    return {"company": "ทดสอบ", "tax_id": "0000000000000",
            "items": [{"name": f"ของ{i}", "unit": u, "amount": 100} for i, u in enumerate(units)]}


def _has_lang(units):
    notes = ux.company_unit_notes([_bill(units)])
    return any("ภาษาไทยและภาษาอังกฤษ" in n for n in notes)


def main():
    print("=== [A] flag เฉพาะ 'หน่วยเดียวกัน 2 สคริปต์' (ADR-091) ===")
    # ควร flag — family เดียวกัน คนละสคริปต์
    _check(_has_lang(["เมตร", "m"]), "เมตร + m (length เดียวกัน) → flag")
    _check(_has_lang(["กก.", "kg"]), "กก. + kg (weight เดียวกัน) → flag")
    _check(_has_lang(["ตรม.", "sqm"]), "ตรม. + sqm (area เดียวกัน) → flag")
    _check(_has_lang(["ชิ้น", "PCS"]), "ชิ้น + PCS (pieces เดียวกัน) → flag")

    print("\n=== [B] ต้อง 'ไม่' flag เมื่อเป็นคนละหน่วย (กัน FP ที่เจ้าของเจอ) ===")
    # PCS (ชิ้น) + เมตร (ยาว) = คนละหน่วย → ไม่ใช่ inconsistency
    _check(not _has_lang(["PCS", "เมตร"]), "PCS(ชิ้น) + เมตร(ยาว) คนละหน่วย → ไม่ flag")
    _check(not _has_lang(["เส้น", "ท่อน", "PCS."]), "เส้น/ท่อน(ไทย) + PCS.(อังกฤษ) คนละหน่วย → ไม่ flag")
    _check(not _has_lang(["กล่อง", "ชุด", "EA", "M", "Pcs"]),
           "ไอน์ชไตน์-เคส: กล่อง/ชุด + EA/M/Pcs คนละหน่วย → ไม่ flag")
    _check(not _has_lang(["กระป๋อง", "ขวด", "ซอง", "แพ็ค", "EA."]),
           "ไทยยูคิง-เคส: ภาชนะไทย + EA. คนละหน่วย → ไม่ flag")

    print("\n=== [C] หน่วยไทยล้วน / อังกฤษล้วน → ไม่ flag ===")
    _check(not _has_lang(["เมตร", "กก.", "ชิ้น"]), "ไทยล้วน → ไม่ flag")
    _check(not _has_lang(["m", "kg", "PCS"]), "อังกฤษล้วน → ไม่ flag")

    print("\n=== [D] blank-only ต้องไม่ติดป้าย 'ปนภาษา' (แยกจากหน่วยขาด) ===")
    blank_bill = {"company": "x", "items": [{"name": "a", "unit": "", "amount": 50},
                                            {"name": "b", "unit": "เมตร", "amount": 50}]}
    ns = ux.company_unit_notes([blank_bill])
    _check(not any("ภาษาไทยและภาษาอังกฤษ" in n for n in ns),
           "หน่วยว่าง + เมตร(ไทยล้วน) → ไม่ติดป้ายปนภาษา")
    _check(any("ไม่มีหน่วย" in n for n in ns), "หน่วยว่าง → ยังเตือน 'หน่วยขาด' ตามเดิม")

    print()
    if _fail:
        print(f"RESULT: ❌ FAIL — {len(_fail)} เคส")
        sys.exit(1)
    print("RESULT: ✅ PASS — company_unit_notes flag เฉพาะหน่วยเดียวกัน 2 สคริปต์ (ADR-091)")


if __name__ == "__main__":
    main()
