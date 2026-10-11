@echo off
chcp 65001 >nul
rem Create a project-local build venv (.venv_build) with pyinstaller + openpyxl.
rem The build scripts prefer this venv, so the state of the system python does not matter.
rem Keep this file UTF-8 (no BOM) + CRLF; keep "chcp 65001" on line 2.
cd /d "%~dp0"

set "BASE="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "BASE=python"
if not defined BASE (
  py -c "import sys" >nul 2>nul
  if not errorlevel 1 set "BASE=py"
)
if not defined BASE (
  echo [ERROR] no python found on PATH. Install Python 3.8+ first.
  pause
  exit /b 1
)

if exist ".venv_build\Scripts\python.exe" goto install

echo Creating .venv_build using %BASE% ...
%BASE% -m venv .venv_build
if errorlevel 1 (
  echo [ERROR] venv creation failed.
  pause
  exit /b 1
)

:install
echo Installing pyinstaller + openpyxl into .venv_build ...
".venv_build\Scripts\python.exe" -m pip install --disable-pip-version-check pyinstaller openpyxl
if errorlevel 1 (
  echo [ERROR] pip install failed - check network or proxy.
  pause
  exit /b 1
)

".venv_build\Scripts\python.exe" -c "import PyInstaller, openpyxl; print('[OK] pyinstaller', PyInstaller.__version__, '/ openpyxl', openpyxl.__version__)"
echo.
echo [OK] local build env ready: .venv_build
echo Now run build_exe_debug.bat ^(debug^) or build_exe.bat ^(release^).
pause
