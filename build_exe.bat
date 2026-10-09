@echo off
chcp 65001 >nul
rem Build a single-file exe (data bundled).
rem Keep this file UTF-8 (no BOM) + CRLF; keep "chcp 65001" on line 2.
cd /d "%~dp0"

rem Use "python -m PyInstaller" instead of the pyinstaller.exe on PATH:
rem pip installs it into <Python>\Scripts, which is often NOT on PATH.
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PyInstaller not importable by this "python".
  echo         Run:  python -m pip install pyinstaller
  echo         then check:  python -c "import PyInstaller; print(PyInstaller.__version__)"
  pause
  exit /b 1
)

rem beta 分支：适配「黑冰测试版」（Blackice HOI IV TEST, workshop id 1851181613）
set EXE_NAME=飞机设计计算器_黑冰测试版v12.3.0

echo Building "%EXE_NAME%" ...
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "%EXE_NAME%" ^
  --add-data "data;data" ^
  --add-data "BI_SOV.xlsx;." ^
  --hidden-import openpyxl ^
  --exclude-module numpy --exclude-module matplotlib --exclude-module PIL ^
  gui.py

echo.
if exist "dist\%EXE_NAME%.exe" (
  echo [OK] dist\%EXE_NAME%.exe
  echo Ship that exe together with the readme txt.
) else (
  echo [FAILED] send the log above to the maintainer.
)
pause
