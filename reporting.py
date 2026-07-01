# -*- coding: utf-8 -*-
"""reporting.py — OBJ-MAINT: ซอยเพื่อ maintainability (≲600/ไฟล์) แบบ pure extraction + re-export.
logic/golden ไม่เปลี่ยน. โครง: reporting_p0, reporting_p1, reporting_p2 (cascade import) → ไฟล์นี้ re-export + __all__ เดิม.
ทุก body extract ด้วย AST line-slice (byte-identical). public API เดิมครบ."""
from reporting_p2 import (   # [F3 de-star] explicit (เดิม `from reporting_p2 import *`)
    ANALYTICS_CFG, APP_VERSION, PYTHAINLP_AVAILABLE, RULES,
    build_clean_report, build_dashboard_figs, display_executive_dashboard, display_low_confidence_bills,
    export_excel, export_verification_to_excel, render_dashboard_html,
)

# [F3 de-star] public surface (re-export จาก reporting_p2) — ดับ F401 + ประกาศ API ชัด
__all__ = [
    'ANALYTICS_CFG', 'APP_VERSION', 'PYTHAINLP_AVAILABLE',
    'RULES', 'build_clean_report', 'build_dashboard_figs',
    'display_executive_dashboard', 'display_low_confidence_bills', 'export_excel',
    'export_verification_to_excel', 'render_dashboard_html',
]
