# -*- coding: utf-8 -*-
"""main.py — ASCII entrypoint shim (OBJ-CONSISTENCY / portability)

ตัวหลักจริงคือ `ปุ้มปุ้ย_ultimate_v9_modular.py` (ชื่อไฟล์ภาษาไทย). บางระบบไฟล์/เครื่องมือ/
CI runner จัดการ Unicode ในชื่อไฟล์ได้ไม่ดี — ไฟล์นี้เป็น "ทางเข้า ASCII" ที่ re-export ตัวจริง
ทั้งหมด โดย **ไม่ rename** ของเดิม (การ rename จะพัง import/test ทั่วระบบที่อ้างชื่อไทยอยู่).

ใช้:
    python3 main.py            # = รันตัวหลัก (production)
    from main import main      # = เรียกใช้ในโค้ด
    import main as app         # alias ทั้งโมดูล

ไม่กระทบ golden hash: เป็นเพียง re-export ชั้นบาง ๆ — พฤติกรรม/ผลตรวจวิ่งผ่านโมดูลตัวจริงเดิม.
"""
from __future__ import annotations

import importlib
import sys


def _utf8_console():
    """[ADR-171/BUGHUNT F-A] สำเนา logic ADR-063 มารันให้ "ก่อน import ตัวจริง" — banner version-gate
    (มี emoji) พิมพ์ตอน import ผ่าน pukpui_modular_base → บน Windows ที่ stdout ถูก redirect/pipe
    (encoding = cp874/cp1252) เดิม UnicodeEncodeError ฆ่าทั้ง run ก่อน parse ไฟล์ใด ๆ.
    guard เดิม (_ensure_utf8_console) อยู่ใน __main__ ของตัวจริง = รันหลัง import เสร็จ — สายเกินไป."""
    for _s in (sys.stdout, sys.stderr):
        try:
            if hasattr(_s, 'reconfigure') and (getattr(_s, 'encoding', '') or '').lower().replace('-', '') != 'utf8':
                _s.reconfigure(encoding='utf-8')
        except Exception:
            pass


# [P2-FIX] บังคับ PYTHONHASHSEED=0 ก่อน import โมดูลหลัก (เฉพาะเส้น CLI production) —
#   ให้ผลตรวจตรงเงื่อนไขที่ golden ถูกสร้าง แม้รันนอก VS Code. no-op ถ้า seed=0 อยู่แล้ว/ถูก import.
if __name__ == "__main__":
    from hashseed_guard import enforce_hashseed
    enforce_hashseed()
    _utf8_console()

_APP = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")

# re-export ทุกชื่อสาธารณะของตัวจริง → `from main import X` ใช้ได้เหมือนอ้างตัวจริง
globals().update({k: v for k, v in vars(_APP).items() if not k.startswith("__")})

# ชื่อที่ผู้เรียกน่าจะใช้บ่อย (ระบุชัดเพื่อ static tooling)
main = _APP.main


if __name__ == "__main__":
    # [ADR-171/BUGHUNT F-A] ห่อเหมือน entry ตัวจริง (ปุ้มปุ้ย…modular __main__) — เดิม shim เรียกเปล่า:
    #   Ctrl-C = traceback ดิบ / exception ไม่ถูกห่อ ทั้งที่เอกสารชี้ให้รันผ่านไฟล์นี้เป็นหลัก.
    try:
        _APP.main()
    except KeyboardInterrupt:
        print('\n⏹️ ยกเลิก')
    except Exception as e:
        import traceback
        print(f'\n❌ Error: {e}'); traceback.print_exc()
