@echo off
chcp 65001 >nul
rem Build a single-file exe (data bundled).
rem Keep this file UTF-8 (no BOM) + CRLF; keep "chcp 65001" on line 2.
rem Which python? 1) project-local venv .venv_build (setup_build_env.bat makes it)
rem               2) "python" from PATH
cd /d "%~dp0"

rem Use "python -m PyInstaller" instead of the pyinstaller.exe on PATH:
rem pip installs it into <Python>\Scripts, which is often NOT on PATH.
set "PY="
if exist ".venv_build\Scripts\python.exe" set "PY=.venv_build\Scripts\python.exe"
if not defined PY set "PY=python"

"%PY%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PyInstaller not importable by: %PY%
  echo         Run setup_build_env.bat first - it creates a local .venv_build.
  echo         Or:  "%PY%" -m pip install pyinstaller openpyxl
  pause
  exit /b 1
)

rem beta 分支：适配「黑冰测试版」（Blackice HOI IV TEST, workshop id 1851181613）
set EXE_NAME=飞机设计计算器_黑冰测试版v12.3.0

echo Building "%EXE_NAME%" using %PY% ...
"%PY%" -m PyInstaller --noconfirm --onefile --windowed ^
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
