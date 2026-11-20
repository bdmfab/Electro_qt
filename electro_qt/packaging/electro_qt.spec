# PyInstaller spec: pyinstaller packaging/electro_qt.spec   (run from the project folder)
import sys
from pathlib import Path

root = Path(SPECPATH).parent
datas = [(str(root / "blocks"), "blocks"),
         (str(root / "electro" / "ui" / "resources"), "electro/ui/resources")]
if (root / "docs" / "Electro_qt_Manual.pdf").exists():
    datas.append((str(root / "docs" / "Electro_qt_Manual.pdf"), "docs"))

a = Analysis([str(root / "run_electro.py")], pathex=[str(root)], datas=datas,
             hiddenimports=["ezdxf", "pypdf"], excludes=["tkinter"])
pyz = PYZ(a.pure)
icon = str(root / "electro" / "ui" / "resources" / "icon.ico") if sys.platform == "win32" else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Electro_qt", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="Electro_qt")
