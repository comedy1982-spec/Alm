@echo off
chcp 65001 >nul
title ECU-ALM 실행기

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   ECU-ALM  v0.3  ASPICE PAM 4.0         ║
echo  ║   요구사항 관리 도구 — 시작 중...        ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ── Python 확인 ──────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python 이 설치되어 있지 않거나 PATH 에 없습니다.
    echo.
    echo  Python 3.10 이상을 설치하세요:
    echo    https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python %PYVER% 확인됨

:: ── venv 생성 / 재사용 ───────────────────────────────
set VENV_DIR=%~dp0.venv
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo  가상환경 생성 중...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [오류] 가상환경 생성 실패
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

:: ── 패키지 설치 ──────────────────────────────────────
pip show ecualm >nul 2>&1
if errorlevel 1 (
    echo  패키지 설치 중 (최초 1회)...
    pip install -e "%~dp0." --quiet
    if errorlevel 1 (
        echo [오류] 패키지 설치 실패
        pause
        exit /b 1
    )
    echo  설치 완료
) else (
    echo  패키지 이미 설치됨
)

:: ── 서버 시작 + 브라우저 열기 ───────────────────────
echo.
echo  서버 시작 중 — http://localhost:8765
echo  종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.

:: 2초 후 브라우저 자동 오픈
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8765"

python -m ecualm serve --host 127.0.0.1 --port 8765

pause
