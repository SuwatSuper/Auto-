# -*- mode: python ; coding: utf-8 -*-
# pukpui_dashboard.spec — สเปก PyInstaller สร้าง .exe ของแดชบอร์ด (รันบน Windows)
#   build:  pyinstaller --noconfirm pukpui_dashboard.spec
#   ได้:    dist\PukpuiDashboard.exe  (ดับเบิลคลิกใช้ได้เลย ไม่ต้องลง Python)
#
# หมายเหตุสำคัญ (กันพังเวลา bundle):
#   • agents โหลดแบบ dynamic (agents/__init__:_LAZY ผ่าน importlib) → PyInstaller มองไม่เห็น
#     ต้องใส่ hiddenimports = ทุก agents.* + โมดูล engine ที่ถูก import แบบไดนามิก.
#   • pythainlp/matplotlib มี data file → ใช้ collect_all ดึงให้ครบ.
#   • โมดูลหลักชื่อไทย 'ปุ้มปุ้ย_ultimate_v9_modular.py' ต้องถูกรวม (อยู่ใน datas + hiddenimports).
from PyInstaller.utils.hooks import collect_all, collect_submodules
import os, glob

datas, binaries, hiddenimports = [], [], []

# ── lib ที่มี data file ───────────────────────────────────────────────────
for pkg in ("pythainlp", "matplotlib", "openpyxl", "xlrd", "rapidfuzz"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# ── agents ทั้งหมด (dynamic _LAZY) + engine modules ที่ agent เรียก ──────────
hiddenimports += collect_submodules("agents")
hiddenimports += [
    "ปุ้มปุ้ย_ultimate_v9_modular", "run_agents", "super_ultra_viewer", "report_precision",
    "parser", "parser_p0a", "parser_p0", "parser_p1", "parser_p2",
    "rules_engine", "rules_engine_base", "rules_engine_rules_a",
    "rules_engine_rules_b", "rules_engine_rules_c", "validators",
    "reporting", "reporting_p0", "reporting_p1", "reporting_p2",
    "config", "config_base", "state", "puopuy_core", "puopuy_dates", "puopuy_units",
    "thai_text", "diagnostics", "code_labels", "code_registry", "core_utils",
    "version_gate", "hashseed_guard", "viewers", "mesh_contract", "analytics",
    "pandas", "numpy",
]

# โมดูลหลักชื่อไทย — รวมเป็น data ด้วย (กันกรณี import แบบ importlib ตามชื่อไฟล์)
for f in glob.glob("ปุ้มปุ้ย_*.py"):
    datas.append((f, "."))

block_cipher = None

a = Analysis(
    ["dashboard.py"],
    pathex=[os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # baseline.json (4.5MB) = ใช้ verify golden เท่านั้น ไม่ใช้ตอนตรวจจริง → ตัดออกให้ .exe เล็กลง
    excludes=["tkinter.test", "test", "pytest", "coverage"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="PukpuiDashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # อย่าใช้ UPX (มักโดน antivirus เตือน false-positive)
    runtime_tmpdir=None,
    console=False,                   # หน้าต่าง GUI ล้วน (ไม่มี console ดำ) — stdout ถูก redirect ในแอป
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="pukpui.ico",            # ใส่ไอคอนเองได้ถ้ามี
)
