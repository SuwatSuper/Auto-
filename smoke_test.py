# -*- coding: utf-8 -*-
"""smoke_test.py — ด่านกันพังเร็ว (เบา/เร็ว/ไม่ต้องใช้ข้อมูลจริง)

ออกแบบมาเพื่อ "ดักบั๊กที่เคยทำให้แพ็กเกจส่งมอบรันไม่ได้เลย" โดยเฉพาะ:
  1) ไฟล์ .py ขนาด 0 ไบต์ (เคสจริง: analytics.py ถูกส่งมาว่างเปล่า → import เงียบ → พังทีหลัง)
  2) โมดูลที่ import ไม่ได้ (เคสจริง: puopuy_units.py หายทั้งไฟล์ → ModuleNotFoundError)
  3) สัญลักษณ์ที่ import-gate ของ agent ต้องการ (core_access._REQUIRED) ต้องครบ
  4) ฟังก์ชันที่สร้างใหม่ทำงานได้กับ fixture เล็กๆ (ไม่ crash, คืน contract ถูก)

รันก่อน commit / ก่อน deploy ทุกครั้ง — เร็วพอจะใส่ CI:
    PYTHONHASHSEED=0 python3 smoke_test.py
exit 0 = ผ่านหมด, 1 = พบปัญหา
"""
import os, sys, glob, io, contextlib, datetime, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_fail = []
_pass = 0


def check(cond, label):
    global _pass
    if cond:
        _pass += 1
        print(f'  ✅ {label}')
    else:
        _fail.append(label)
        print(f'  ❌ {label}')


print('=' * 64)
print('SMOKE TEST — packaging & import integrity')
print('=' * 64)

# ── 0) version gate (P1) — เพี้ยนระดับอันตราย = ล้มทันที (ไม่ใช่เตือนเงียบ) ──────
print('\n[0] version gate (เวอร์ชัน lib เทียบ golden lock)')
try:
    import version_gate
    _vrep = version_gate.check(strict=False)
    print(version_gate.format_report(_vrep))
    check(_vrep.ok, 'เวอร์ชันไม่เพี้ยนระดับอันตราย (major/minor ของ lib หัวใจ ครบ)'
          + (f' — อันตราย: {[f"{i.name}{i.got}≠{i.want}" for i in _vrep.failures]}'
             if _vrep.failures else ''))
except Exception as e:
    check(False, f'รัน version gate ไม่ได้ — {type(e).__name__}: {e}')

# ── 1) ไม่มีไฟล์ .py ขนาด 0 ไบต์ ────────────────────────────────────────────
print('\n[1] ไฟล์ .py ต้องไม่ว่างเปล่า (0 ไบต์)')
py_files = glob.glob(os.path.join(HERE, '*.py')) + glob.glob(os.path.join(HERE, 'agents', '*.py'))
empties = [os.path.relpath(f, HERE) for f in py_files if os.path.getsize(f) == 0]
check(not empties, f'ไม่มีไฟล์ .py ว่างเปล่า ({len(py_files)} ไฟล์ตรวจแล้ว)'
      + (f' — พบว่าง: {empties}' if empties else ''))

# ── 2) โมดูลไลบรารีหลัก import ได้ + gate ของ agent ผ่าน ─────────────────────
print('\n[2] โมดูลหลัก import ได้ (รวม import-gate ของ agent)')
LIB_MODULES = [
    'config', 'state', 'puopuy_core', 'puopuy_dates', 'puopuy_units',
    'analytics', 'parser', 'rules_engine', 'validators', 'reporting',
    'thai_text', 'diagnostics', 'core_utils',
]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    for mod in LIB_MODULES:
        try:
            importlib.import_module(mod)
            ok = True
        except Exception as e:
            ok = False
            _err = f'{type(e).__name__}: {e}'
        # บันทึกผลนอก redirect ไม่ได้ตรงๆ → เก็บลง list
        globals().setdefault('_imp', {})[mod] = (ok, locals().get('_err', '') if not ok else '')
for mod in LIB_MODULES:
    ok, err = globals()['_imp'][mod]
    check(ok, f'import {mod}' + (f' — {err}' if not ok else ''))

# main module + agent gate
try:
    with contextlib.redirect_stdout(io.StringIO()):
        app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
    check(True, 'import โมดูลหลัก (ปุ้มปุ้ย_ultimate_v9_modular)')
except Exception as e:
    app = None
    check(False, f'import โมดูลหลัก — {type(e).__name__}: {e}')

try:
    with contextlib.redirect_stdout(io.StringIO()):
        from agents.orchestrator import run_pipeline  # noqa: F401
    check(True, 'import agents.orchestrator (import-gate ผ่าน)')
except Exception as e:
    check(False, f'import agents.orchestrator (gate) — {type(e).__name__}: {e}')

# ── 3) สัญลักษณ์ที่ gate ต้องการครบ ─────────────────────────────────────────
print('\n[3] สัญลักษณ์ที่ import-gate (core_access._REQUIRED) ต้องการ')
try:
    with contextlib.redirect_stdout(io.StringIO()):
        from agents import core_access as core
    required = list(getattr(core, '_REQUIRED', []))
    missing = [n for n in required if core.get(n) is None]
    check(bool(required), f'อ่าน _REQUIRED ได้ ({len(required)} สัญลักษณ์)')
    check(not missing, 'สัญลักษณ์ครบทุกตัว' + (f' — ขาด: {missing}' if missing else ''))
except Exception as e:
    check(False, f'ตรวจ _REQUIRED ไม่ได้ — {type(e).__name__}: {e}')

# ── 4) fixture เล็ก ผ่านฟังก์ชันที่สร้างใหม่ (ไม่ crash + contract ถูก) ─────────
print('\n[4] ฟังก์ชันที่สร้างใหม่ทำงานกับ fixture เล็ก')
if app is not None:
    try:
        b = {
            'file': 'KRR 69.012.xls', 'sheet': 'Sheet1',
            'company': 'บริษัท ทดสอบ จำกัด', 'master_key': 'ทดสอบ',
            'tax_id': '0105536000021', 'iv_number': 'IV68-001',
            'iv_date': datetime.date(2025, 11, 5), 'iv_number_raw': 'IV68-001',
            'items': [
                {'seq': 1, 'name': 'ค่าบริการติดตั้ง', 'unit': 'งาน', 'amount': 5000},
                {'seq': 2, 'name': 'สีน้ำมัน 5 ลิตร', 'unit': 'แกลลอน', 'amount': 800},
            ],
            'subtotal': 5800, 'vat': 406, 'total': 6206,
        }
        app.compute_bill_confidence(b)
        check(b.get('parse_confidence') in ('HIGH', 'MID', 'LOW')
              and isinstance(b.get('parse_confidence_reasons'), list),
              "compute_bill_confidence ตั้ง parse_confidence + reasons")

        summary = app.summarize_by_company([b])
        s0 = summary[0] if summary else {}
        check(summary and all(k in s0 for k in ('key', 'period', 'bill_count', 'subtotal', 'vat', 'total', 'bills'))
              and isinstance(s0['subtotal'], (int, float)),
              "summarize_by_company คืน contract ครบ (subtotal เป็นตัวเลข)")

        idx = app.build_unit_index([b])
        check(idx.get('สีน้ำมัน 5 ลิตร') == {'แกลลอน'},
              "build_unit_index รวม name→set(units) ถูก")

        wht = app.addon_check_withholding([b])
        check(isinstance(wht, list) and wht and wht[0].get('expected_wht_3pct') == 150.0,
              "addon_check_withholding จับค่าบริการ 5000 → คาดหัก 150 (3%)")

        from puopuy_units import _D, _unit_canon, extract_unit_hint, _vat_tolerance
        check(_D('1,234.50') is not None and _D('abc') is None and _D(None) is None,
              "_D แปลงเลข/comma/None/ขยะ ถูกต้อง")
        check(extract_unit_hint('สีน้ำมัน 5 ลิตร') == 'ลิตร',
              "extract_unit_hint ดึงหน่วยจากชื่อสินค้าได้")
        check(_unit_canon('กิโลกรัม') == _unit_canon('กก.'),
              "_unit_canon ยุบหน่วยพ้องความหมายเป็นตัวเดียวกัน")
        check(float(_vat_tolerance(10000)) == 0.6,
              "_vat_tolerance(10000) = 0.6 (RESTORED 0.5 + |sub|/100000)")
    except Exception as e:
        import traceback
        check(False, f'fixture ล้ม — {type(e).__name__}: {e}')
        traceback.print_exc()
else:
    check(False, 'ข้าม fixture (โมดูลหลัก import ไม่ได้)')

# ── สรุป ────────────────────────────────────────────────────────────────────
print('\n' + '=' * 64)
print(f'SMOKE: ผ่าน {_pass} / ล้มเหลว {len(_fail)}')
print('=' * 64)
if _fail:
    for f in _fail:
        print(f'  ❌ {f}')
    sys.exit(1)
print('RESULT: ✅ แพ็กเกจครบ import ได้ ฟังก์ชันหลักทำงาน')
sys.exit(0)
