@echo off
REM ============================================================================
REM  START.bat — เปิดแดชบอร์ดแบบง่ายสุด (ดับเบิลคลิกไฟล์นี้ → โปรแกรมเปิดเลย)
REM  ไม่ต้อง build .exe ไม่ต้องเปิด VS Code — แค่มี Python 3.12 บนเครื่อง
REM  (ครั้งแรกจะลงไลบรารีให้อัตโนมัติ ครั้งต่อไปเปิดได้ทันที)
REM ============================================================================
chcp 65001 >nul
cd /d "%~dp0"
title ปุ้มปุ้ย Dashboard

REM --- หา Python (ลอง python ก่อน แล้ว py) ---
set PY=python
where python >nul 2>&1 || set PY=py
%PY% --version >nul 2>&1 || (
  echo.
  echo  X  ไม่พบ Python บนเครื่อง
  echo     โหลด Python 3.12 ที่ https://www.python.org/downloads/
  echo     ** ตอนติดตั้ง ติ๊ก [v] Add python.exe to PATH **  แล้วดับเบิลคลิก START.bat อีกครั้ง
  echo.
  pause
  exit /b 1
)

REM --- ครั้งแรก: ถ้าไลบรารียังไม่ครบ ติดตั้งให้อัตโนมัติ (รอสักครู่ ครั้งเดียว) ---
%PY% -c "import pandas, openpyxl, rapidfuzz, numpy, xlrd" 2>nul || (
  echo.
  echo  === ครั้งแรก: กำลังติดตั้งไลบรารี รอสักครู่ ^(ต้องต่อเน็ต ทำครั้งเดียว^) ===
  %PY% -m pip install -r requirements.txt -c constraints.txt
)

REM --- เปิดแดชบอร์ด ---
%PY% dashboard.py
if errorlevel 1 pause
