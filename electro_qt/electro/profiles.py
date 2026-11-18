"""Footprint profiles: how a real part (manufacturer + part number) looks on the panel layout.

The schematic uses one generic block for every breaker / contactor / fuse holder; the layout is where they
differ, so the footprint is tied to the part. Profiles live in a hidden, human-readable file in the block library's folder
(.electro_profiles.ini), one section per part:

    [3RT2015-1BB41]
    block = contactor
    manufacturer = Siemens
    part_number = 3RT2015-1BB41
    hyperlink = https://example.com/3rt2015
    width = 0.9
    height = 3.1
    depth = 3.5
    mounting = rail
    rail_cl = 0.0
    units = in

Qt-free. Sizes are inches unless the section says `units = mm`.
"""
from __future__ import annotations
import configparser
import os

FILE = ".electro_profiles.ini"
_folder = ""            # set by the application to the block library's folder ("" = the current directory)


def set_folder(folder):
    """The folder holding the profiles file: the block library's folder ("" = the current directory)."""
    global _folder
    _folder = str(folder) if folder else ""


def adopt(old_folder):
    """Profiles saved next to a project by 0.20.2-0.20.5: copy that file into the library folder when the
    library has none yet. Returns True when it did."""
    if not old_folder:
        return False
    old, new = os.path.join(old_folder, FILE), file_path()
    if os.path.abspath(old) == os.path.abspath(new) or os.path.exists(new) or not os.path.exists(old):
        return False
    try:
        import shutil
        shutil.copyfile(old, new)
        return True
    except OSError:
        return False


def file_path(folder=None):
    f = _folder if folder is None else folder
    return os.path.join(f or os.getcwd(), FILE)


def _norm(s):
    return " ".join((s or "").split()).lower()


def _parser():
    return configparser.ConfigParser(interpolation=None, default_section="__none__")


def load(folder=None):
    """-> {section: {manufacturer, part_number, hyperlink, width, height, depth, mounting, rail_cl}} (inches)."""
    path = file_path(folder)
    cp = _parser()
    try:
        cp.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return {}
    out = {}
    for name in cp.sections():
        s = cp[name]
        k = 25.4 if s.get("units", "in").strip().lower() == "mm" else 1.0
        def num(key):
            try:
                return float(s.get(key, "0")) / k
            except ValueError:
                return 0.0
        out[name] = {"block": s.get("block", "").strip(), "manufacturer": s.get("manufacturer", "").strip(), "part_number": s.get("part_number", "").strip(),
                     "hyperlink": s.get("hyperlink", "").strip(), "width": num("width"), "height": num("height"),
                     "depth": num("depth"), "mounting": s.get("mounting", "rail").strip().lower() or "rail",
                     "rail_cl": num("rail_cl")}
    return out


def for_block(profiles, block):
    """The profiles of one block: {section: profile}."""
    return {n: p for n, p in profiles.items() if p["block"] == block}


def find(profiles, manufacturer="", part_number="", hyperlink="", block=None):
    """The (section, profile) for a part: manufacturer + part number first; the hyperlink only decides when no
    part number is given. With `block`, only that block's profiles (and old ones that name no block)."""
    pn, mf, hl = _norm(part_number), _norm(manufacturer), (hyperlink or "").strip()
    cands = {n: p for n, p in profiles.items() if block is None or p["block"] in ("", block)}
    if pn:
        for name, p in cands.items():
            if _norm(p["part_number"]) == pn and (not mf or not p["manufacturer"] or _norm(p["manufacturer"]) == mf):
                return name, p
    elif hl:
        for name, p in cands.items():
            if p["hyperlink"] == hl:
                return name, p
    return None, None


def claim_legacy(project, folder=None):
    """Profiles saved before they were tied to a block: give each to the block of the parts that use it."""
    profs = load(folder)
    loose = {n for n, p in profs.items() if not p["block"]}
    if not loose:
        return
    from .geometry import leaves
    owner = {}
    for sh in project.sheets.values():
        if sh.panel:
            continue
        for r in leaves(sh.entities):
            n = getattr(r, "props", {}).get("profile") if hasattr(r, "block") else None
            if n in loose and n not in owner:
                owner[n] = r.block
    if not owner:
        return
    path = file_path(folder)
    cp = _parser()
    try:
        cp.read(path, encoding="utf-8")
        for n, b in owner.items():
            if n in cp:
                cp[n]["block"] = b
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Electro_qt footprint profiles: one [section] per part, sizes in inches.\n"
                    "# 'block' ties a profile to the schematic block it belongs to. Edit freely.\n\n")
            cp.write(f)
    except (OSError, configparser.Error):
        pass


def save(manufacturer, part_number, hyperlink, width, height, depth, mounting="rail", rail_cl=0.0, folder=None,
         section=None, return_name=False, block=""):
    """Create or update the profile of this part (`section`: update that one, else the one matching
    manufacturer + part number, else a new one). Returns the file path (None if nothing to key it by or the
    file cannot be written); with return_name, (path, section name)."""
    if not (manufacturer.strip() or part_number.strip()):
        return (None, "") if return_name else None
    path = file_path(folder)
    cp = _parser()
    try:
        cp.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        pass
    name = section if section and section in cp else find(load(folder), manufacturer, part_number, block=block or None)[0]
    if name is None or name not in cp:
        name = (part_number.strip() or manufacturer.strip()).replace("]", ")")
        base, n = name, 2
        while name in cp:
            name, n = f"{base} ({n})", n + 1
        cp.add_section(name)
    s = cp[name]
    if block:
        s["block"] = block
    s["manufacturer"] = manufacturer.strip()
    s["part_number"] = part_number.strip()
    s["hyperlink"] = hyperlink.strip()
    s["width"], s["height"], s["depth"] = (f"{v:.4f}".rstrip("0").rstrip(".") or "0" for v in (width, height, depth))
    s["mounting"] = mounting
    s["rail_cl"] = f"{rail_cl:.4f}".rstrip("0").rstrip(".") or "0"
    s["units"] = "in"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Electro_qt footprint profiles: one [section] per part, sizes in inches.\n"
                    "# Matched by manufacturer + part number (or hyperlink). Edit freely.\n\n")
            cp.write(f)
    except OSError:
        return (None, "") if return_name else None
    if os.name == "nt":                                    # "hidden" on Windows needs the attribute
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(path, 2)
        except Exception:
            pass
    return (path, name) if return_name else path
