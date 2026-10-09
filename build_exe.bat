@echo off
rem 打包成单文件 exe：dist\BI_air_design_calculator.exe
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo 找不到 pyinstaller，请先执行： python -m pip install pyinstaller
  pause
  exit /b 1
)

echo 正在打包（数据已内置，输出到 dist\）...
pyinstaller --noconfirm --onefile --windowed ^
  --name "BI_air_design_calculator" ^
  --add-data "data;data" ^
  --add-data "BI_SOV.xlsx;." ^
  --hidden-import openpyxl ^
  --exclude-module numpy --exclude-module matplotlib --exclude-module PIL ^
  gui.py

echo.
if exist "dist\BI_air_design_calculator.exe" (
  echo 打包完成： dist\BI_air_design_calculator.exe
  echo 分发时把这个 exe 和「开始使用前先看.txt」一起发给别人即可。
) else (
  echo 打包失败，请把上面的报错发给维护者。
)
pause
