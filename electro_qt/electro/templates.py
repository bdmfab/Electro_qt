"""Sheet templates. The 11x17 geometry is taken from the sample drawings
(AC Example / Safety Example): a 17" x 11" landscape sheet, hexagon zone markers
down the left (rows 00-24 at 0.35" pitch, row 00 centred at y = 9.45), and a
title-block column on the right."""
from __future__ import annotations
import copy
import math
from . import model as m
from .geometry import walk

LINE_COLOR, TEXT_COLOR = 8, 7        # palette: gray frame, white/black text


def _line(x1, y1, x2, y2):
    return m.Line(x1, y1, x2, y2, m.Style("0", color=LINE_COLOR))


def _arc(cx, cy, r, a0, a1):
    return m.Arc(cx, cy, r, a0, a1, m.Style("0", color=LINE_COLOR))


def _text(x, y, source, h, align="center"):
    return m.Text(x, y, source, source, h, 0.0, m.Style("0", color=TEXT_COLOR), align=align)


def _border(out):
    # drawing area: x 0.084..14.884, y 0.3..10.8, corners chamfered 0.125
    L, B, R, T, c = 0.084, 0.3, 14.884, 10.8, 0.125
    out += [_line(L + c, B, R - c, B), _line(R, B + c, R, T - c), _line(R - c, T, L + c, T),
            _line(L, T - c, L, B + c), _line(L, T - c, L + c, T), _line(R - c, T, R, T - c),
            _line(L, B + c, L + c, B), _line(R, B + c, R - c, B)]


def _rounded_box(out, x0, y0, x1, y1, r=0.125):
    out += [_line(x0 + r, y0, x1 - r, y0), _line(x1, y0 + r, x1, y1 - r),
            _line(x1 - r, y1, x0 + r, y1), _line(x0, y1 - r, x0, y0 + r),
            _arc(x0 + r, y0 + r, r, 180, 270), _arc(x1 - r, y0 + r, r, 270, 360),
            _arc(x1 - r, y1 - r, r, 0, 90), _arc(x0 + r, y1 - r, r, 90, 180)]


def _title_block(out):
    x0, x1 = 15.084, 16.584
    xm = (x0 + x1) / 2
    _rounded_box(out, x0, 0.3, x1, 6.3)           # information box
    _rounded_box(out, x0, 6.5, x1, 10.8)          # logo box (left empty)
    for y in (0.8, 1.3, 1.8, 4.3, 4.8, 5.3, 5.8):
        out.append(_line(x0, y, x1, y))
    out += [_line(x0 + 0.75, 1.3, x0 + 0.75, 1.8), _line(x0 + 0.75, 4.3, x0 + 0.75, 5.8)]
    out += [_text(x0 + 0.016, 1.7, "DRAWN", 0.08, "left"), _text(x0 + 0.757, 1.703, "DATE", 0.08, "left"),
            _text(x0 + 0.025, 1.195, "JOB", 0.08, "left")]
    out += [_text(x0 + 0.375, 1.40, "{drawn}", 0.1), _text(x0 + 1.125, 1.40, "{date}", 0.1),
            _text(xm, 0.94, "{job}", 0.125), _text(xm, 0.47, "{page} OF {pages}", 0.1)]
    for i, y in enumerate((3.684, 3.31, 2.936, 2.562), 1):      # four title lines
        out.append(_text(xm, y, f"{{title{i}}}", 0.125))


def _zone_ruler(out, cx, first_zone, rows, pitch, y0):
    """Hexagon markers: sheet page number above the zone number."""
    for i in range(rows):
        y = y0 - i * pitch
        h = 0.126
        pts = [(cx - 0.073, y + h), (cx + 0.073, y + h), (cx + 0.146, y),
               (cx + 0.073, y - h), (cx - 0.073, y - h), (cx - 0.146, y)]
        out += [_line(*pts[k], *pts[(k + 1) % 6]) for k in range(6)]
        out.append(_text(cx, y + 0.02, "{page}", 0.06))
        out.append(_text(cx, y - 0.106, f"{first_zone + i:02d}", 0.08))


def tabloid_template(columns: int = 1) -> m.Sheet:
    """11x17 landscape. columns=1: zones 00-24; columns=2: 00-49 (second ruler mid-sheet)."""
    if columns not in (1, 2):
        raise ValueError("columns must be 1 or 2")
    s = m.Sheet(1, "", zone_count=25 * columns, row_pitch=0.35, width=17.0, height=11.0,
                zone0_y=9.45, grid_x0=0.0)
    out = []
    _border(out)
    _title_block(out)
    _zone_ruler(out, 0.354, 0, 25, 0.35, s.zone0_y)
    if columns == 2:
        mid = (0.084 + 14.884) / 2
        s.col_split_x = mid
        _zone_ruler(out, mid + 0.27, 25, 25, 0.35, s.zone0_y)
    s.frame = out
    s.logo_box = (15.134, 6.55, 1.4, 4.2)        # inside the logo box
    return s


def default_templates() -> dict:
    return {"11x17 - 1 column (zones 00-24)": tabloid_template(1),
            "11x17 - 2 columns (zones 00-49)": tabloid_template(2)}


def sheet_from_template(template: m.Sheet, page: int, title: str = "") -> m.Sheet:
    """A new empty sheet that carries the template's geometry and frame (fresh ids)."""
    s = copy.deepcopy(template)
    s.page, s.title = page, title
    s.entities, s.bundles, s.gotos = [], [], []
    s.title_lines = ["", "", "", ""]
    for e in walk(s.frame):
        e.id = m.new_id()
    return s


def zone_of(sheet: m.Sheet, x: float, y: float) -> int:
    """Zone number (0-based, 00-24 or 00-49) of a point on the sheet."""
    row = max(0, min(24, round((sheet.zone0_y - y) / sheet.row_pitch)))
    col = 1 if (sheet.col_split_x is not None and x >= sheet.col_split_x) else 0
    return row + 25 * col


TITLE_BLOCK_MM = 0.7        # twice the default line (1.5 px = 0.33 mm on screen)


def _border_box(sheet):
    """(left, bottom, right, top) of the drawing-area border: the four long lines left of the title block."""
    x0 = sheet.width - 2.0
    long_ = [e for e in sheet.frame if isinstance(e, m.Line) and min(e.x1, e.x2) < x0
             and math.hypot(e.x2 - e.x1, e.y2 - e.y1) > 1.0]
    if not long_:
        return None
    xs = [v for e in long_ for v in (e.x1, e.x2)]; ys = [v for e in long_ for v in (e.y1, e.y2)]
    return min(xs), min(ys), max(xs), max(ys)


def display_frame(sheet: m.Sheet) -> list:
    """The sheet's frame as it is drawn: the border and the title block (the column on the right, the
    last 2 units of the sheet) at double weight. Copies; the stored frame is not changed."""
    x0 = sheet.width - 2.0
    box = _border_box(sheet)

    def on_box(x, y, t=1e-3):
        L, B, R, T = box
        return (abs(x - L) < t or abs(x - R) < t or abs(y - B) < t or abs(y - T) < t) \
            and L - t <= x <= R + t and B - t <= y <= T + t

    out = []
    for e in sheet.frame:
        inside = (isinstance(e, m.Line) and min(e.x1, e.x2) >= x0) or (isinstance(e, m.Arc) and e.cx >= x0)
        border = box is not None and isinstance(e, m.Line) and on_box(e.x1, e.y1) and on_box(e.x2, e.y2)
        if (inside or border) and e.style.width <= 0:
            e = copy.copy(e)
            e.style = copy.copy(e.style)
            e.style.width = TITLE_BLOCK_MM
        out.append(e)
    return out
