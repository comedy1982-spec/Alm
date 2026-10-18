#!/usr/bin/env bash
# ECU-ALM macOS 원샷 실행기
# Finder 에서 더블클릭하면 바로 실행됩니다.

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
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        VER=$("$candidate" -c "import sys; print(sys.version_info[:2])")
        if "$candidate" -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌  Python 3.10+ 가 필요합니다."
    echo ""
    echo "   설치 방법:"
    echo "     brew install python@3.12"
    echo "   또는  https://www.python.org/downloads/macos/"
    echo ""
    read -p "엔터를 누르면 창이 닫힙니다..."
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
(sleep 2 && open "http://localhost:8765") &

echo ""
echo "🚀  서버 시작: http://localhost:8765"
echo "   종료하려면 Ctrl+C 를 누르세요."
echo ""

python -m ecualm serve --host 127.0.0.1 --port 8765
