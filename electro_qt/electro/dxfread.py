"""Minimal stdlib DXF (ASCII) reader: group-code pairs -> sections/entities.

Only what Electro_qt import needs. ezdxf can replace this later behind the same
`read_dxf()` interface.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RawEntity:
    type: str
    codes: list = field(default_factory=list)  # list of (int code, str value)

    def get(self, code, default=None):
        for c, v in self.codes:
            if c == code:
                return v
        return default

    def getf(self, code, default=0.0):
        v = self.get(code)
        return float(v) if v is not None else default

    def all(self, code):
        return [v for c, v in self.codes if c == code]


@dataclass
class RawDxf:
    layers: dict = field(default_factory=dict)      # name -> color int
    entities: list = field(default_factory=list)    # modelspace RawEntity
    blocks: dict = field(default_factory=dict)      # name -> list[RawEntity]


def _pairs(text: str):
    lines = text.splitlines()
    for i in range(0, len(lines) - 1, 2):
        try:
            yield int(lines[i].strip()), lines[i + 1].strip()
        except ValueError:
            continue


def read_dxf(path) -> RawDxf:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    out = RawDxf()
    section = None
    cur = None            # current entity being collected
    cur_block = None
    in_table_layer = None
    pairs = list(_pairs(text))
    i = 0
    n = len(pairs)
    expect_section_name = False
    expect_block_name = False
    while i < n:
        code, val = pairs[i]
        i += 1
        if code == 0:
            # finish previous entity
            if cur is not None:
                _store(out, section, cur_block, cur)
                cur = None
            if val == "SECTION":
                expect_section_name = True
            elif val == "ENDSEC":
                section = None
            elif val == "BLOCK":
                cur_block = None
                expect_block_name = True
                cur = RawEntity("BLOCK")
            elif val == "ENDBLK":
                cur_block = None
            elif val == "EOF":
                break
            else:
                cur = RawEntity(val)
            continue
        if expect_section_name and code == 2:
            section = val
            expect_section_name = False
            continue
        if cur is not None:
            cur.codes.append((code, val))
            if expect_block_name and cur.type == "BLOCK" and code == 2:
                cur_block = val
                out.blocks.setdefault(val, [])
                expect_block_name = False
    if cur is not None:
        _store(out, section, cur_block, cur)
    return out


def _store(out: RawDxf, section, block, ent: RawEntity):
    if section == "TABLES" and ent.type == "LAYER":
        out.layers[ent.get(2, "0")] = int(ent.get(62, "7"))
    elif section == "ENTITIES":
        out.entities.append(ent)
    elif section == "BLOCKS" and block and ent.type != "BLOCK":
        out.blocks[block].append(ent)
