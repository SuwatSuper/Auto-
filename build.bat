@echo off
REM ============================================================================
REM  build.bat — สร้าง PukpuiDashboard.exe (ดับเบิลคลิกไฟล์นี้บน Windows ครั้งเดียว)
REM  ต้องมี: Python 3.12 (ติ๊ก "Add to PATH" ตอนติดตั้ง)  +  อินเทอร์เน็ต (ครั้งแรก)
REM  ผลลัพธ์: dist\PukpuiDashboard.exe  → ดับเบิลคลิกใช้ได้เลย ไม่ต้องลงอะไรอีก
REM ============================================================================
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo === [1/3] ติดตั้งไลบรารี (ตรึงเวอร์ชันให้ตรง golden) ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
if errorlevel 1 ( echo ❌ ติดตั้งไลบรารีไม่สำเร็จ & pause & exit /b 1 )

echo.
echo === [2/3] ติดตั้ง PyInstaller ===
python -m pip install pyinstaller
if errorlevel 1 ( echo ❌ ติดตั้ง PyInstaller ไม่สำเร็จ & pause & exit /b 1 )

echo.
echo === [3/3] สร้าง .exe (ใช้เวลาสักครู่ ~2-5 นาที) ===
python -m PyInstaller --noconfirm pukpui_dashboard.spec
if errorlevel 1 ( echo ❌ build ไม่สำเร็จ — ดู error ด้านบน & pause & exit /b 1 )

echo.
echo ============================================================
echo ✅ เสร็จ!  ไฟล์โปรแกรมอยู่ที่:  dist\PukpuiDashboard.exe
echo    ดับเบิลคลิกไฟล์นั้นเพื่อใช้งาน (ไม่ต้องเปิด VS Code อีก)
echo ============================================================
pause
