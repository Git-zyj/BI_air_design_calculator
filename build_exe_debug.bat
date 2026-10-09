@echo off
chcp 65001 >nul
rem DEBUG build: keeps a console window so errors are visible.
rem Use this one first when something goes wrong, then build the release.
cd /d "%~dp0"

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PyInstaller not importable by this "python".
  echo         Run:  python -m pip install pyinstaller
  pause
  exit /b 1
)

set EXE_NAME=飞机设计计算器_黑冰正式版v12.1.0_调试版

echo Building (DEBUG, with console) "%EXE_NAME%" ...
python -m PyInstaller --noconfirm --onefile ^
  --name "%EXE_NAME%" ^
  --add-data "data;data" ^
  --add-data "BI_SOV.xlsx;." ^
  --hidden-import openpyxl ^
  --exclude-module numpy --exclude-module matplotlib --exclude-module PIL ^
  gui.py

echo.
if exist "dist\%EXE_NAME%.exe" (
  echo [OK] dist\%EXE_NAME%.exe
  echo Double-click it. If it fails, the traceback shows IN this console - send it to the maintainer.
) else (
  echo [FAILED] send the log above to the maintainer.
)
pause
