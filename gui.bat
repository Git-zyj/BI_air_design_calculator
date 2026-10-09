@echo off
rem BI_SOV 飞机选型 —— Windows 侧启动器（双击即可）
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo 找不到 python。请先安装 Python 3 并在安装时勾选 "Add python.exe to PATH"。
  pause
  exit /b 1
)

python gui.py %*
if not errorlevel 1 goto :eof

echo.
echo 程序异常退出。若提示缺少模块（如 openpyxl），请在本目录执行：
echo     python -m pip install openpyxl
pause
