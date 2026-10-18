#!/usr/bin/env bash
# ECU-ALM Linux 원샷 실행기
# 터미널에서:  bash run_linux.sh
# 또는:        chmod +x run_linux.sh && ./run_linux.sh

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ECU-ALM  v0.3  ASPICE PAM 4.0         ║"
echo "║   요구사항 관리 도구 — 시작 중...        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Python 확인 ──────────────────────────────────────
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c "import sys; exit(0 if sys.version_info >= (3,9) else 1)" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌  Python 3.9+ 가 필요합니다."
    echo ""
    echo "   Ubuntu/Debian:  sudo apt install python3.12"
    echo "   Fedora:         sudo dnf install python3.12"
    echo "   또는: https://www.python.org/downloads/"
    echo ""
    exit 1
fi

echo "✅  $($PYTHON --version) 확인됨"

# ── venv 생성 / 재사용 ───────────────────────────────
VENV="$DIR/.venv"
if [ ! -f "$VENV/bin/activate" ]; then
    echo "   가상환경 생성 중..."
    "$PYTHON" -m venv "$VENV"
fi

source "$VENV/bin/activate"

# ── 패키지 설치 ──────────────────────────────────────
if ! pip show ecualm &>/dev/null; then
    echo "   패키지 설치 중 (최초 1회)..."
    pip install -e "$DIR" --quiet
    echo "✅  설치 완료"
else
    echo "✅  패키지 이미 설치됨"
fi

# ── 브라우저 자동 열기 ───────────────────────────────
(sleep 2 && {
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:8765"
    elif command -v gnome-open &>/dev/null; then
        gnome-open "http://localhost:8765"
    fi
}) &

echo ""
echo "🚀  서버 시작: http://localhost:8765"
echo "   종료하려면 Ctrl+C 를 누르세요."
echo ""

python -m ecualm serve --host 127.0.0.1 --port 8765
