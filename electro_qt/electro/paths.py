"""Where the program's own files are (Qt-free). Run from source they sit next to the package; in a packaged
build (PyInstaller) they are unpacked beside the program, which may be read-only (Program Files), so
anything the program WRITES (the default block library) goes to the user's data folder instead."""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """The folder that holds the electro package (source) or the unpacked program files (packaged)."""
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Per-user, writable: %APPDATA%\\Electro_qt on Windows, ~/.local/share/Electro_qt elsewhere."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Electro_qt"


def default_library() -> Path:
    """Source run: 'blocks' next to run_electro.py. Packaged: a 'blocks' folder in the user's data folder,
    filled once from the blocks that ship with the program."""
    if not frozen():
        return app_dir() / "blocks"
    dst = user_data_dir() / "blocks"
    src = app_dir() / "blocks"
    try:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                dst.mkdir(parents=True)
    except OSError:
        pass
    return dst


def manual_path() -> Path | None:
    """The PDF user manual, if it is there."""
    for p in (app_dir() / "docs" / "Electro_qt_Manual.pdf", app_dir() / "Electro_qt_Manual.pdf"):
        if p.is_file():
            return p
    return None
