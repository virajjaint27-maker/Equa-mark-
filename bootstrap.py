"""AquaMark runtime bootstrap — makes `python3 bot.py` work on a bare VPS.

Responsibilities (stdlib only, runs before anything else is imported):
  1. Put the vendored pure-python packages (Telegram bot library etc.) on sys.path.
  2. Make Pillow importable: unzip the matching wheel from wheels/ into vendor/
     (works fully offline, no pip required). Falls back to a best-effort
     online pip install for unusual platforms (e.g. ARM).
  3. Extract the bundled static ffmpeg binary from bin/ffmpeg.xz (one-time).
     A system ffmpeg, when present, is preferred instead.
"""
import logging
import os
import platform
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(ROOT, "vendor")
WHEELS = os.path.join(ROOT, "wheels")
BIN = os.path.join(ROOT, "bin")
FFMPEG_XZ = os.path.join(BIN, "ffmpeg.xz")
# the bundled static binary is a Linux ELF; on Windows we look for ffmpeg.exe
FFMPEG_BIN = os.path.join(
    BIN, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

_DONE = False


def _log():
    return logging.getLogger("aquamark.bootstrap")


def _machine_arch():
    m = platform.machine().lower()
    if m in ("x86_64", "amd64", "x86", "x64"):
        return "x86_64"
    if m in ("aarch64", "arm64", "armv8", "armv8l"):
        return "aarch64"
    return m


def _python_tag():
    return "cp%d%d" % sys.version_info[:2]


def _install_pillow():
    """Ensure PIL is importable. Offline-first: bundled wheels, then pip."""
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass

    tag = _python_tag()
    arch = _machine_arch()

    # normalize wheels dir (some pip versions lowercase the name)
    candidates = []
    if os.path.isdir(WHEELS):
        for fn in os.listdir(WHEELS):
            if not fn.lower().endswith(".whl"):
                continue
            low = fn.lower()
            if not low.startswith("pillow-"):
                continue
            if tag in fn and arch in fn and ("manylinux" in fn or "linux" in fn):
                candidates.append((fn, os.path.join(WHEELS, fn)))

    if candidates:
        # prefer newest version string
        candidates.sort(reverse=True)
        fn, path = candidates[0]
        _log().info("Installing bundled Pillow wheel for %s/%s: %s", tag, arch, fn)
        with zipfile.ZipFile(path) as z:
            z.extractall(VENDOR)
        try:
            import PIL  # noqa: F401
            return
        except ImportError as exc:
            _log().warning("Bundled wheel did not satisfy import: %s", exc)

    # last resort: online pip into vendor/ (keeps system clean)
    _log().info("No bundled Pillow wheel for %s/%s — trying online pip install "
                "(one-time, needs internet)", tag, arch)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--target", VENDOR, "--no-cache-dir", "Pillow"],
            timeout=300,
        )
    except Exception as exc:  # pragma: no cover - environment specific
        raise SystemExit(
            "ERROR: Could not make Pillow importable.\n"
            "  Bundled wheels cover Python 3.8-3.14 on x86_64 Linux.\n"
            "  This machine: Python %s on %s.\n"
            "  Fix: `pip3 install Pillow` on the server and re-run.\n"
            "  Original error: %s" % (sys.version.split()[0], arch, exc)
        )
    import PIL  # noqa: F401


def _extract_ffmpeg():
    """One-time extraction of the bundled static ffmpeg (xz -> binary)."""
    if sys.platform == "win32":
        return False  # bundled binary is Linux-only; Windows needs ffmpeg.exe
    if os.path.isfile(FFMPEG_BIN) and os.access(FFMPEG_BIN, os.X_OK):
        return True
    if not os.path.isfile(FFMPEG_XZ):
        return False
    _log().info("Extracting bundled ffmpeg (one-time, ~a few seconds)...")
    import lzma
    tmp_path = FFMPEG_BIN + ".part"
    with lzma.open(FFMPEG_XZ, "rb") as src, open(tmp_path, "wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
    os.chmod(tmp_path, 0o755)
    os.replace(tmp_path, FFMPEG_BIN)
    return True


def ffmpeg_path():
    """Return a working ffmpeg executable path, preferring a system install."""
    import shutil
    system = shutil.which("ffmpeg")
    if system:
        return system
    if _extract_ffmpeg():
        try:
            ok = subprocess.run(
                [FFMPEG_BIN, "-version"], capture_output=True, timeout=20
            ).returncode == 0
            if ok:
                return FFMPEG_BIN
        except Exception:
            pass
    raise SystemExit(
        "ERROR: No usable ffmpeg found.\n"
        "  The bundled binary covers Linux x86_64 (fully static).\n"
        "  On Windows: `winget install Gyan.FFmpeg` or download from\n"
        "  https://www.gyan.dev/ffmpeg/builds/ and put ffmpeg.exe on PATH\n"
        "  (or place it at: %s).\n"
        "  On other systems install ffmpeg (e.g. `apt install ffmpeg`)."
        % FFMPEG_BIN
    )


def setup():
    """Idempotent. Call once at process start, before importing telegram/PIL."""
    global _DONE
    if _DONE:
        return
    if sys.version_info < (3, 8):
        raise SystemExit("ERROR: Python 3.8+ required (you have %s)."
                         % sys.version.split()[0])
    if os.path.isdir(VENDOR) and VENDOR not in sys.path:
        sys.path.insert(0, VENDOR)
    _install_pillow()
    _extract_ffmpeg()
    _DONE = True
