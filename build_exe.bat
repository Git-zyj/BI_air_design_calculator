@echo off
chcp 65001 >nul
rem Build a single-file exe (data bundled). Output: dist\BI_air_design_calculator.exe
rem NOTE: keep this file UTF-8 (no BOM) + CRLF, and keep "chcp 65001" on line 2.
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo [ERROR] pyinstaller not found. Run:  python -m pip install pyinstaller
  pause
  exit /b 1
)

set EXE_NAME=飞机设计计算器_黑冰正式版v1.19.2.0

echo Building "%EXE_NAME%" ...
pyinstaller --noconfirm --onefile --windowed ^
  --name "%EXE_NAME%" ^
  --add-data "data;data" ^
  --add-data "BI_SOV.xlsx;." ^
  --hidden-import openpyxl ^
  --exclude-module numpy --exclude-module matplotlib --exclude-module PIL ^
  gui.py

echo.
if exist "dist\%EXE_NAME%.exe" (
  echo [OK] dist\%EXE_NAME%.exe
  echo Ship that exe together with "开始使用前先看.txt".
) else (
  echo [FAILED] send the log above to the maintainer.
)
pause
