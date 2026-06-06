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

# [P2-FIX] บังคับ PYTHONHASHSEED=0 ก่อน import โมดูลหลัก (เฉพาะเส้น CLI production) —
#   ให้ผลตรวจตรงเงื่อนไขที่ golden ถูกสร้าง แม้รันนอก VS Code. no-op ถ้า seed=0 อยู่แล้ว/ถูก import.
if __name__ == "__main__":
    from hashseed_guard import enforce_hashseed
    enforce_hashseed()

_APP = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")

# re-export ทุกชื่อสาธารณะของตัวจริง → `from main import X` ใช้ได้เหมือนอ้างตัวจริง
globals().update({k: v for k, v in vars(_APP).items() if not k.startswith("__")})

# ชื่อที่ผู้เรียกน่าจะใช้บ่อย (ระบุชัดเพื่อ static tooling)
main = _APP.main


if __name__ == "__main__":
    _APP.main()
