"""Electro_qt data model. Pure Python, no Qt, so scripts and tests can use it."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import Optional

SCHEMA_VERSION = 1


def new_id() -> str:
    return str(uuid.uuid4())


def page_str(page: int) -> str:
    if not 0 <= page <= 99:                      # 00 is the cover sheet
        raise ValueError(f"page must be 00-99, got {page}")
    return f"{page:02d}"


# ---------------------------------------------------------------- entities
@dataclass
class WireNumber:
    mode: str = "auto"          # auto | override | locked | ignore | goto
    value: str = ""

    def __post_init__(self):
        if self.mode not in ("auto", "override", "locked", "ignore", "goto"):
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
    rich: bool = False                       # source holds richtext markup (<b> <i> <u> <size=> <color=>)
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


@dataclass
class PanelObj:
    """An object of a panel layout (to scale, front view): the back plate, a DIN rail, a wire duct or a
    part's footprint. `w` runs along the object's own x axis (the length of a rail / duct), `h` across it;
    `rot` (0 / 90 / 180 / 270) turns it on the sheet. Kept as a profile + length (+ `depth`) so it can be
    extruded to 3D later."""
    kind: str                     # plate | rail | duct | part | terminals
    cx: float; cy: float          # centre on the sheet
    w: float; h: float            # footprint in its own frame (inches)
    rot: float = 0.0
    depth: float = 0.0            # how far it stands off the plate (3D); duct depth, part depth
    locked: bool = False          # rail / duct: ends cannot be dragged
    block: str = ""               # part: the block it stands for
    tag: str = ""                 # part: the schematic tag (KM1)
    mount: str = ""               # part: rail | plate
    cl: float = 0.0               # part: DIN rail centre line, offset from the centre across the part (own y)
    qty: int = 1                  # terminals: how many blocks are stacked side by side (w = qty x one block's width)
    xbom: bool = False            # layout-only parts (terminals): left out of the BOM
    ident: str = ""               # terminal block identifier (TB1); its terminals are TB1.1, TB1.2 ...
    first: int = 1                # number of the first terminal
    names: str = ""               # custom terminal labels, "|" separated ("" = automatic), one per terminal
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "panel"


@dataclass
class Dim:
    """A horizontal or vertical dimension between two points (the layout is to scale, so it measures real
    size). `pos` is where the dimension line sits: its y for a horizontal one, its x for a vertical one."""
    x1: float; y1: float
    x2: float; y2: float
    orient: str = "h"             # h | v
    pos: float = 0.0
    th: float = 0.0               # text height, inches (0 = the sheet's default)
    a1: str = ""                  # what the first / second end is attached to: "<panel object id>:<x0|xc|x1|y0|yc|y1>"
    a2: str = ""                  # (edge or centre of the object; "" = a free point). Attached ends follow their object
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    TAG = "dim"


ENTITY_TYPES = {c.TAG: c for c in (Line, Rect, Circle, Arc, Text, BlockRef, SlotMark, Group, PanelObj, Dim)}


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
    exclude_bom: int = 0                          # 1 = left out of the bill of materials
    fp_w: float = 0.0                             # panel footprint (inches): width along the rail / plate x,
    fp_h: float = 0.0                             #   height across it,
    fp_d: float = 0.0                             #   depth off the plate
    mount: str = ""                               # rail | plate ("" = no footprint yet)
    rail_cl: float = 0.0                          # DIN rail centre line, offset from the footprint centre (across)
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
    dim_th: float = 0.14          # default dimension text height (inches)
    dim_units: str = "in"         # panel layout dimensions are shown in: in | mm
    panel: bool = False           # a panel layout sheet (to scale, no title block / zones)
    cover: bool = False           # the cover sheet: page 00, not numbered, no title block / zones

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

    def _apply_order(self, order) -> dict:
        """Give the numbered sheets (a list of their current pages, in the wanted order) the pages 01, 02, 03 ...
        The cover stays 00. Goto targets follow. -> {old page: new page} for the sheets that changed."""
        mapping = {pg: pg for pg, sh in self.sheets.items() if sh.cover}
        order = [pg for pg in order if not self.sheets[pg].panel] + [pg for pg in order if self.sheets[pg].panel]
        for i, pg in enumerate(order, 1):                 # panel layouts always come last
            mapping[pg] = i
        changed = {a: b for a, b in mapping.items() if a != b}
        if changed:
            new = {}
            for pg in sorted(self.sheets):
                sh = self.sheets[pg]
                sh.page = mapping[pg]
                new[sh.page] = sh
            self.sheets = dict(sorted(new.items()))
            for sh in new.values():
                for g in sh.gotos:
                    g.targets = [(n, mapping.get(p, p)) for n, p in g.targets]
        return changed

    def renumber_sheets(self) -> dict:
        """Close the gaps: the numbered sheets become 01, 02, 03 ... in their current order (the cover
        stays 00). -> {old page: new page} for the sheets that changed."""
        return self._apply_order([pg for pg in sorted(self.sheets) if not self.sheets[pg].cover])

    def move_sheet(self, page: int, new_page: int) -> dict:
        """Move a numbered sheet to position `new_page`; the sheets in between shift by one (move 2 to 3: the old 3
        becomes 2). -> {old page: new page}."""
        order = [pg for pg in sorted(self.sheets) if not self.sheets[pg].cover]
        if page not in order:
            raise ValueError("only numbered sheets can be moved")
        order.remove(page)
        order.insert(max(0, min(new_page - 1, len(order))), page)
        return self._apply_order(order)

    def add_sheet_before_panels(self, sheet: Sheet) -> int:
        """Add a numbered sheet after the last ordinary sheet; the panel layouts (always last) move up one page.
        -> the new sheet's page."""
        tmp = 10_000
        sheet.page = tmp
        self.sheets[tmp] = sheet
        order = [pg for pg in sorted(self.sheets) if pg != tmp and not self.sheets[pg].cover]
        k = next((i for i, pg in enumerate(order) if self.sheets[pg].panel), len(order))
        order.insert(k, tmp)
        self._apply_order(order)
        return sheet.page

    def add_sheet(self, sheet: Sheet) -> Sheet:
        if sheet.page in self.sheets:
            raise ValueError(f"page {sheet.page:02d} already exists")
        self.sheets[sheet.page] = sheet
        return sheet
