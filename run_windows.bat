@echo off
setlocal
chcp 65001 >nul
title ECU-ALM
cd /d "%~dp0"

echo.
echo  ========================================
echo   ECU-ALM  v0.3  ASPICE PAM 4.0
echo  ========================================
echo.

rem ---- Python check ----
python --version >nul 2>&1
if errorlevel 1 goto :nopython
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python %PYVER% OK

rem ---- venv ----
set "VENV=%~dp0.venv"
if exist "%VENV%\Scripts\python.exe" goto :venvok
echo  Creating virtual environment...
python -m venv "%VENV%"
if errorlevel 1 goto :venvfail
:venvok
set "PY=%VENV%\Scripts\python.exe"

rem ---- install (first run only) ----
"%PY%" -c "import ecualm" >nul 2>&1
if not errorlevel 1 goto :installed
echo  Installing packages - first run only, takes a few minutes...
"%PY%" -m pip install -e "%~dp0." --no-input
if errorlevel 1 goto :pipfail
:installed
echo  Packages OK

rem ---- start server + open browser ----
echo.
echo  Server: http://localhost:8765
echo  Press Ctrl+C to stop.
echo.
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8765"
"%PY%" -m ecualm serve --host 127.0.0.1 --port 8765
goto :end

:nopython
echo [ERROR] Python 3.9+ not found on PATH. https://www.python.org/downloads/
goto :end
:venvfail
echo [ERROR] Failed to create virtual environment.
goto :end
:pipfail
echo [ERROR] pip install failed. See messages above.
goto :end

:end
pause
