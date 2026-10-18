"""Figure assets: content-addressed storage, legacy vector formats converted to PNG."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

WEB_OK = {"png", "jpg", "jpeg", "gif", "svg", "webp"}


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_with_soffice(src: Path, fmt: str, outdir: Path) -> Path | None:
    exe = _soffice()
    if not exe:
        return None
    try:
        subprocess.run([exe, "--headless", "--convert-to", fmt, "--outdir", str(outdir), str(src)],
                       check=True, capture_output=True, timeout=180)
    except Exception:
        return None
    out = outdir / (src.stem + "." + fmt.split(":")[0])
    return out if out.exists() else None


def to_web_image(blob: bytes, ext: str) -> tuple[bytes, str]:
    ext = (ext or "").lower().lstrip(".")
    if ext in WEB_OK:
        return blob, "jpg" if ext == "jpeg" else ext
    if ext in ("emf", "wmf"):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / f"img.{ext}"
            src.write_bytes(blob)
            out = convert_with_soffice(src, "png", Path(td) / "out")
            if out:
                return out.read_bytes(), "png"
    try:
        from PIL import Image
        im = Image.open(BytesIO(blob))
        buf = BytesIO()
        im.convert("RGBA" if im.mode in ("P", "LA", "RGBA") else "RGB").save(buf, "PNG")
        return buf.getvalue(), "png"
    except Exception:
        return blob, ext or "bin"


def save_asset(asset_dir: Path, blob: bytes, ext: str) -> dict:
    orig_ext = (ext or "").lower()
    data, web_ext = to_web_image(blob, orig_ext)
    sha = hashlib.sha1(blob).hexdigest()[:16]
    name = f"{sha}.{web_ext}"
    path = asset_dir / name
    if not path.exists():
        path.write_bytes(data)
    if web_ext != orig_ext and orig_ext:
        raw = asset_dir / f"{sha}.orig.{orig_ext}"
        if not raw.exists():
            raw.write_bytes(blob)
    return {"file": name, "sha": sha, "orig_ext": orig_ext, "converted": web_ext != orig_ext}
