@echo off
setlocal
chcp 65001 >nul
title Web Desktop
cd /d "%~dp0"

echo.
echo  ========================================
echo   Web Desktop  -  http://localhost:8000
echo  ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo  [!] Python is not installed. Install it from https://www.python.org
  pause
  exit /b 1
)

rem Open the browser after the server has started
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8000/web-desktop.html"

echo  Close this window to stop Web Desktop.
echo  (Run ECU ALM separately with run_windows.bat - http://localhost:8765)
echo.
python -m http.server 8000 --bind 127.0.0.1
