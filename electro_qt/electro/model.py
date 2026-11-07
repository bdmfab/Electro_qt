"""Electro_qt data model. Pure Python, no Qt, so scripts and tests can use it."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Optional

SCHEMA_VERSION = 1


def new_id() -> str:
    return str(uuid.uuid4())


def page_str(page: int) -> str:
    if not 1 <= page <= 99:
        raise ValueError(f"page must be 01-99, got {page}")
    return f"{page:02d}"


# ---------------------------------------------------------------- entities
@dataclass
class WireNumber:
    mode: str = "auto"          # auto | override | locked | ignore
    value: str = ""

    def __post_init__(self):
        if self.mode not in ("auto", "override", "locked", "ignore"):
            raise ValueError(f"bad wire number mode {self.mode!r}")


@dataclass
class Style:
    layer: str = "0"
    color: Optional[int] = None   # None = by layer
    width: float = 0.0
    linetype: str = "continuous"


@dataclass
class Line:
    x1: float; y1: float; x2: float; y2: float
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    number: Optional[WireNumber] = None     # only meaningful on wire layers
    mark: str = ""                           # 'Mark wire': numbering starts here; value = start incident
    TAG = "line"


@dataclass
class Rect:
    x: float; y: float; w: float; h: float
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "rect"


@dataclass
class Circle:
    cx: float; cy: float; r: float
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    filled: bool = False                    # solid dot = terminal/junction
    TAG = "circle"


@dataclass
class Arc:
    cx: float; cy: float; r: float; start: float; end: float   # degrees, CCW
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "arc"


@dataclass
class Text:
    x: float; y: float
    source: str                              # raw, may contain {field} codes
    resolved: str = ""                       # last-resolved value
    height: float = 0.1
    rotation: float = 0.0
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    font: str = ""                           # family; "" = application default
    align: str = "left"                      # left | center | right of the anchor point
    tstyle: str = "Default"                  # name of a TextStyle (values are copied in)
    TAG = "text"


@dataclass
class BlockRef:
    block: str
    x: float; y: float
    rotation: float = 0.0
    mirror: bool = False
    tag: str = ""                            # resolved device tag
    props: dict = field(default_factory=dict)   # per-instance overrides
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "blockref"


@dataclass
class SlotMark:
    """A `wire#` slot drawn on a sheet while a block is being made. Making the block
    turns each mark into a Slot of the block definition."""
    x: float; y: float
    terminal: str = ""
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "slot"


@dataclass
class Group:
    """Entities that move, copy and select as one. Children keep their own
    styles; groups may be nested."""
    children: list = field(default_factory=list)
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "group"


ENTITY_TYPES = {c.TAG: c for c in (Line, Rect, Circle, Arc, Text, BlockRef, SlotMark, Group)}


# ---------------------------------------------------------------- blocks
@dataclass
class Slot:
    """A `wire#` slot: the only connection point of a block."""
    terminal: str               # L1, T1, 13 ...
    x: float; y: float          # block-local
    num_dx: float = 0.0         # where printed wire number sits, relative to slot
    num_dy: float = 0.0


@dataclass
class BlockDef:
    name: str
    description: str = ""
    part_number: str = ""
    tag_prefix: str = ""
    hyperlink: str = ""
    manufacturer: str = ""
    data: dict = field(default_factory=dict)      # extra BOM fields
    increment: int = 0                            # 0 none, 1 = +1
    connector: int = 0                            # 1 = off-page connector: parts with the same tag are one wire
    prefix_rule: str = ""                         # e.g. "motor" -> L becomes T
    poles: int = 1
    terminal_text_editable: bool = False         # (kept for old files; terminals are always editable per part)
    label_pos: str = "above"                      # stacked label: above | right
    folder: str = ""                              # library folder path, e.g. "Contactors/Auxiliary"
    entities: list = field(default_factory=list)
    slots: list = field(default_factory=list)
    layers: dict = field(default_factory=dict)    # layer definitions the graphics use: name -> Layer


# ---------------------------------------------------------------- layers
@dataclass
class Layer:
    name: str
    color: int = 7
    kind: str = "graphics"        # graphics | wire
    numbered: bool = False
    scheme: str = ""              # pattern, e.g. "<page><zone><incident>"
    linetype: str = "continuous"
    lineweight: float = 0.0       # mm; 0 = application default
    phase: str = ""               # L1 / L2 / L3 / N / PE ... (used by wire numbering)

    def __post_init__(self):
        if self.kind not in ("graphics", "wire"):
            raise ValueError(f"bad layer kind {self.kind!r}")


# ---------------------------------------------------------------- sheet
@dataclass
class Bundle:
    members: list                 # wire entity ids
    preset: str = "3ph"           # 1ph | 3ph | 3ph+PE
    spacing: float = 0.35
    id: str = field(default_factory=new_id)


@dataclass
class Goto:
    x: float; y: float
    targets: list = field(default_factory=list)   # [(wire_number, page)]
    id: str = field(default_factory=new_id)


@dataclass
class Sheet:
    page: int
    title: str = ""
    zone_count: int = 25          # 25 (single band) or 50 (double)
    row_pitch: float = 0.35
    units: str = "in"
    grid_divisions: int = 1       # grid lines between the major (row) lines
    entities: list = field(default_factory=list)
    bundles: list = field(default_factory=list)
    gotos: list = field(default_factory=list)
    width: float = 17.0           # sheet size in `units` (11x17 landscape)
    height: float = 11.0
    zone0_y: float = 9.45         # y of the centre of zone row 00 (rows go down by row_pitch)
    grid_x0: float = 0.0          # x of a grid line
    logo_box: Optional[tuple] = None       # (x, y, w, h) where the project logo image is drawn
    col_split_x: Optional[float] = None    # two-column sheets: x >= this is zones 25-49
    title_lines: list = field(default_factory=lambda: ["", "", "", ""])
    frame: list = field(default_factory=list)   # border, zone markers, title block (not user-editable objects)

    def __post_init__(self):
        page_str(self.page)
        if self.zone_count not in (25, 50):
            raise ValueError("zone_count must be 25 or 50")

    def find(self, ent_id):
        return next((e for e in self.entities if e.id == ent_id), None)


@dataclass
class MultilinePreset:
    """A named wire-colour standard (e.g. "480 VAC"): draw 2-4 parallel wires at
    once, one layer each, in order (first = top / left). labels name each wire
    (L1, L2, L3, N, PE), colors are palette indices, spacing 0 = sheet row pitch."""
    name: str
    layers: list
    spacing: float = 0.0
    colors: Optional[list] = None
    labels: Optional[list] = None

    def __post_init__(self):
        n = len(self.layers)
        if not 2 <= n <= 4:
            raise ValueError("a multiline preset has 2-4 wires")
        if self.labels is None:
            self.labels = list(self.layers)
        if self.colors is None:
            self.colors = [7] * n
        if len(self.labels) != n or len(self.colors) != n:
            raise ValueError("labels and colors must match the wires")


def make_standard(name, prefix, wires):
    """wires = [(label, palette colour)] -> preset whose layers are '<prefix> <label>'."""
    return MultilinePreset(name, [f"{prefix} {lb}" for lb, _ in wires],
                           colors=[c for _, c in wires], labels=[lb for lb, _ in wires])


def default_multiline_presets():
    """Starting colour standards. Palette: 10 brown, 11 orange, 2 yellow, 3 green,
    7 black/white, 1 red, 5 blue, 9 light gray. All editable by the user."""
    w480 = [("L1", 10), ("L2", 11), ("L3", 2), ("PE", 3)]
    w240 = [("L1", 7), ("L2", 1), ("L3", 5), ("PE", 3)]
    return {p.name: p for p in (
        make_standard("480 VAC 3ph+PE", "480V", w480),
        make_standard("480 VAC 3ph", "480V", w480[:3]),
        make_standard("240 VAC 3ph+PE", "240V", w240),
        make_standard("240 VAC 1ph+PE", "240V", [w240[0], w240[1], w240[3]]),
        make_standard("120 VAC", "120V", [("L1", 7), ("N", 9), ("PE", 3)]))}


@dataclass
class TextStyle:
    """Named look for single-line/simple text: like a layer, but for text."""
    name: str
    font: str = ""                 # "" = application default font
    height: float = 0.12
    color: Optional[int] = None    # None = by layer
    align: str = "left"            # left | center | right


def default_text_styles():
    return {"Default": TextStyle("Default")}


@dataclass
class PrefixRule:
    """Letter rule: in a layer scheme, `pattern` (e.g. <L|T>) becomes `if_true` when a block
    whose Letter rule is `name` touches the wire, otherwise `if_false`."""
    name: str
    pattern: str = "<L|T>"
    if_true: str = "T"
    if_false: str = "L"


def default_prefix_rules():
    return [PrefixRule("motor", "<L|T>", "T", "L")]


@dataclass
class Project:
    name: str = "Untitled"
    layers: dict = field(default_factory=dict)     # name -> Layer
    sheets: dict = field(default_factory=dict)     # page -> Sheet
    blocks: dict = field(default_factory=dict)     # name -> BlockDef
    templates: dict = field(default_factory=dict)  # name -> Sheet
    block_folders: list = field(default_factory=list)   # library folders (even empty ones)
    multiline_presets: dict = field(default_factory=default_multiline_presets)
    text_styles: dict = field(default_factory=default_text_styles)
    prefix_rules: list = field(default_factory=default_prefix_rules)
    schemes: dict = field(default_factory=dict)    # user wire-number schemes: name -> pattern
    info: dict = field(default_factory=lambda: {"job": "", "drawn": "", "date": ""})
    lead_zero_suppress: bool = False
    assets: dict = field(default_factory=dict)     # path -> bytes
    schema_version: int = SCHEMA_VERSION

    def add_sheet(self, sheet: Sheet) -> Sheet:
        if sheet.page in self.sheets:
            raise ValueError(f"page {sheet.page:02d} already exists")
        self.sheets[sheet.page] = sheet
        return sheet
