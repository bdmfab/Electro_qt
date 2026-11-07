"""Shared block library on disk (Qt-free).

Layout: <root>/<folder>/<sub folder>/<Block name>.eqblock, one XML file per block
(the same block XML the project bundle uses). Folders on disk are the library
folders. The project keeps its own copy of every block it uses, so a project still
opens when the library is somewhere else.
"""
from __future__ import annotations
import copy
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from . import model as m
from . import xmlio

EXT = ".eqblock"


def default_root() -> Path:
    """'blocks' next to run_electro.py (the folder that holds the electro package)."""
    return Path(__file__).resolve().parent.parent / "blocks"


def safe_name(name: str) -> str:
    s = re.sub(r"[^\w\s().+-]", "_", name).strip()
    return s or "block"


class LibraryStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else default_root()
        self.blocks: dict = {}          # name -> BlockDef (folder set from its path)
        self.folders: list = []         # "A", "A/B" ...
        self.paths: dict = {}           # name -> Path of its file
        self.errors: list = []          # files that could not be read / duplicate names
        self.reload()

    # ---------------------------------------------------------------- reading
    def reload(self):
        self.blocks, self.folders, self.paths, self.errors = {}, [], {}, []
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            self.errors.append(f"{self.root}: {ex}")
            return
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames.sort()
            rel = Path(dirpath).relative_to(self.root)
            folder = "/".join(rel.parts)
            if folder:
                self.folders.append(folder)
            for fn in sorted(filenames):
                if not fn.lower().endswith(EXT):
                    continue
                path = Path(dirpath) / fn
                try:
                    b = xmlio.block_from_xml(ET.parse(path).getroot())
                except Exception as ex:          # noqa: BLE001 - one bad file must not hide the rest
                    self.errors.append(f"{path.name}: {ex}")
                    continue
                if b.name in self.blocks:
                    self.errors.append(f"{path.name}: block name '{b.name}' is already used by "
                                       f"{self.paths[b.name].name}")
                    continue
                b.folder = folder
                self.blocks[b.name] = b
                self.paths[b.name] = path
        self.folders.sort()

    # ---------------------------------------------------------------- writing
    def _dir(self, folder: str) -> Path:
        return self.root.joinpath(*[p for p in folder.split("/") if p])

    def _write(self, b: m.BlockDef, path: Path):
        el = xmlio.block_to_xml(b)
        ET.indent(el)
        tmp = path.with_suffix(path.suffix + ".tmp")
        ET.ElementTree(el).write(tmp, encoding="utf-8", xml_declaration=True)
        os.replace(tmp, path)

    def save_block(self, b: m.BlockDef) -> Path:
        """Write (or move, if its folder changed) the block's file."""
        d = self._dir(b.folder)
        d.mkdir(parents=True, exist_ok=True)
        path = d / (safe_name(b.name) + EXT)
        old = self.paths.get(b.name)
        self._write(b, path)
        if old is not None and old != path and old.exists():
            old.unlink()
        self.blocks[b.name], self.paths[b.name] = b, path
        self._note_folder(b.folder)
        return path

    def _note_folder(self, folder: str):
        parts = [p for p in folder.split("/") if p]
        for i in range(1, len(parts) + 1):
            f = "/".join(parts[:i])
            if f not in self.folders:
                self.folders.append(f)
        self.folders.sort()

    def delete_block(self, name: str):
        p = self.paths.pop(name, None)
        self.blocks.pop(name, None)
        if p is not None and p.exists():
            p.unlink()

    def copy_block(self, src: str, new_name: str, folder: str = "") -> m.BlockDef:
        if new_name in self.blocks:
            raise ValueError(f"a block named {new_name!r} already exists")
        b = copy.deepcopy(self.blocks[src])
        b.name, b.folder = new_name, folder
        from .geometry import leaves
        for e in leaves(b.entities):
            e.id = m.new_id()
        self.save_block(b)
        return b

    def new_folder(self, path: str):
        self._dir(path).mkdir(parents=True, exist_ok=True)
        self._note_folder(path)

    def rename_folder(self, old: str, new: str):
        src, dst = self._dir(old), self._dir(new)
        if dst.exists():
            raise ValueError("a folder with that name already exists")
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dst)
        self.reload()

    def delete_folder(self, path: str) -> int:
        """Remove a folder; its blocks (and sub-folders) move up one level."""
        src = self._dir(path)
        parent = src.parent
        n = 0
        for item in sorted(src.iterdir()):
            target = parent / item.name
            if target.exists():
                raise ValueError(f"'{item.name}' already exists one level up")
            os.rename(item, target)
            n += item.suffix.lower() == EXT
        src.rmdir()
        self.reload()
        return n

    def unique_name(self, name: str, also=()) -> str:
        used = set(self.blocks) | set(also)
        if name not in used:
            return name
        n = 2
        while f"{name} ({n})" in used:
            n += 1
        return f"{name} ({n})"
