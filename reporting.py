# -*- coding: utf-8 -*-
"""reporting.py — OBJ-MAINT: ซอยเพื่อ maintainability (≲600/ไฟล์) แบบ pure extraction + re-export.
logic/golden ไม่เปลี่ยน. โครง: reporting_p0, reporting_p1, reporting_p2 (cascade import) → ไฟล์นี้ re-export + __all__ เดิม.
ทุก body extract ด้วย AST line-slice (byte-identical). public API เดิมครบ."""
from reporting_p2 import *  # noqa: F401,F403

