#!/usr/bin/env python3
"""
ECU-ALM 단일 실행파일 빌더
===========================
PyInstaller 를 사용해 플랫폼별 단일 실행파일을 생성합니다.

사용법:
  python build_exe.py          # 현재 플랫폼용 빌드
  python build_exe.py --clean  # dist/ build/ 삭제 후 빌드

결과:
  dist/ecualm          (Linux/macOS)
  dist/ecualm.exe      (Windows)
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def clean():
    for d in (DIST, BUILD, ROOT / "ecualm.spec"):
        if d.exists():
            shutil.rmtree(d) if d.is_dir() else d.unlink()
            print(f"  삭제: {d}")


def install_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "--quiet"])


def build():
    web_dir = ROOT / "ecualm" / "web"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "ecualm",
        "--add-data", f"{web_dir}{':' if sys.platform != 'win32' else ';'}ecualm/web",
        # 무거운 패키지 제외로 크기 절감
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        "--exclude-module", "PIL._imagingtk",
        # 진입점
        str(ROOT / "ecualm" / "__main__.py"),
    ]
    print("빌드 중...\n  " + " ".join(args))
    subprocess.check_call(args, cwd=ROOT)

    exe = DIST / ("ecualm.exe" if sys.platform == "win32" else "ecualm")
    if exe.exists():
        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"\n✅  빌드 완료: {exe}  ({size_mb:.1f} MB)")
        print("\n실행 방법:")
        if sys.platform == "win32":
            print("  .\\dist\\ecualm.exe serve")
        else:
            print("  ./dist/ecualm serve")
    else:
        print("❌  빌드 실패: dist/ecualm 파일을 찾을 수 없습니다.")
        sys.exit(1)


if __name__ == "__main__":
    if "--clean" in sys.argv:
        print("이전 빌드 정리...")
        clean()

    install_pyinstaller()
    build()
