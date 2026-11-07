"""DXF export: one drawing per sheet, parts as real DXF blocks (BLOCK + INSERT) that carry their
data as attributes (TAG, DESCRIPTION, PART_NUMBER, MANUFACTURER, XREF, TERM1..n, block data).
Needs the `ezdxf` package. Wire numbers are written as text on the layer WIRE_NUMBERS.

What does not carry over: field codes inside a block's own static text (other than the label codes,
which become attributes), logo images, bundles and slot marks."""
from __future__ import annotations
import re
from . import model as m
from . import blocks as bk
from . import numbering as nb
from . import richtext
from .geometry import leaves
from .templates import display_frame

LINEWEIGHTS = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]
LABEL_ATTR = {"{description}": "DESCRIPTION", "{part_label}": "PART_LABEL", "{tag}": "TAG", "{xref}": "XREF"}
HALIGN = {"left": 0, "center": 1, "right": 2}
ATTACH = {"left": 1, "center": 2, "right": 3}
_BAD = re.compile(r'[<>/\\":;?*|=`,\n\r]')


def safe_name(name: str) -> str:
    """A layer / block name DXF accepts."""
    s = _BAD.sub("_", name).strip() or "_"
    return s[:250]


def attr_tag(name: str) -> str:
    """Attribute tags: no spaces, upper case."""
    return re.sub(r"\W+", "_", name).strip("_").upper() or "DATA"


def lineweight(mm: float) -> int:
    """mm -> the nearest lineweight DXF allows (1/100 mm); 0 -> by default (-3)."""
    if mm <= 0:
        return -3
    v = mm * 100
    return min(LINEWEIGHTS, key=lambda w: abs(w - v))


def mtext_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def mtext_markup(text: str, rich: bool, font: str = "") -> str:
    """Text with line breaks (\\P) and, for rich text, bold / italic / underline / size / colour."""
    if not rich:
        return "\\P".join(mtext_escape(l) for l in text.split("\n"))
    out = []
    fam = (font or "Arial").replace("|", "")
    for runs in richtext.parse(text):
        s = ""
        for r in runs:
            codes = ""
            if r.bold or r.italic:
                codes += f"\\f{fam}|b{int(r.bold)}|i{int(r.italic)};"
            if r.color:
                codes += f"\\C{int(r.color)};"
            if abs(r.size - 1.0) > 1e-6:
                codes += f"\\H{r.size:g}x;"
            body = mtext_escape(r.text)
            if r.underline:
                body = "\\L" + body + "\\l"
            s += "{" + codes + body + "}" if codes else body
        out.append(s)
    return "\\P".join(out)


def text_value(t: m.Text) -> str:
    if getattr(t, "hidden", False):
        return ""
    return t.resolved or t.source


def ref_attributes(project, sheet, blk: m.BlockDef, ref: m.BlockRef):
    """[(tag, value, (x, y), height, align, visible)] for one placed part: the label texts at
    their world position (upright), the rest invisible at the insertion point."""
    ctx = bk.block_context(project, sheet, blk, ref)
    hidden = {"{" + k + "}" for k in ref.props.get("hide", "").split(",") if k}
    out, used = [], set()
    for t in blk.entities:
        if isinstance(t, m.Text) and t.source in LABEL_ATTR:
            tag = LABEL_ATTR[t.source]
            code = t.source[1:-1]
            val = "" if t.source in hidden else ctx.get(code, "")
            out.append((tag, val, bk._to_world((t.x, t.y), ref), t.height, t.align, True))
            used.add(tag)
    hid = [("TAG", ref.tag), ("DESCRIPTION", ctx.get("description", "")), ("PART_NUMBER", ctx.get("part", "")),
           ("MANUFACTURER", ctx.get("manufacturer", "")), ("XREF", ctx.get("xref", ""))]
    for tag, val in hid:
        if tag not in used:
            out.append((tag, val, (ref.x, ref.y), 0.1, "left", False))
    for i, (slot, _) in enumerate(bk.block_slots(blk, ref), 1):
        out.append((f"TERM{i}", bk.slot_name(ref, i - 1, slot), (ref.x, ref.y), 0.1, "left", False))
    for k, v in blk.data.items():
        tag = attr_tag(str(k))
        if tag not in {o[0] for o in out}:
            out.append((tag, str(v), (ref.x, ref.y), 0.1, "left", False))
    return out


def block_attdefs(blk: m.BlockDef):
    """[(tag, (x, y), height, align, visible)] the attribute definitions of a block."""
    out, used = [], set()
    for t in blk.entities:
        if isinstance(t, m.Text) and t.source in LABEL_ATTR:
            out.append((LABEL_ATTR[t.source], (t.x, t.y), t.height, t.align, True))
            used.add(LABEL_ATTR[t.source])
    for tag in ("TAG", "DESCRIPTION", "PART_NUMBER", "MANUFACTURER", "XREF"):
        if tag not in used:
            out.append((tag, (0.0, 0.0), 0.1, "left", False))
    for i in range(len(blk.slots)):
        out.append((f"TERM{i + 1}", (0.0, 0.0), 0.1, "left", False))
    for k in blk.data:
        tag = attr_tag(str(k))
        if tag not in {o[0] for o in out}:
            out.append((tag, (0.0, 0.0), 0.1, "left", False))
    return out


class Exporter:
    def __init__(self, project: m.Project, ez=None):
        if ez is None:
            import ezdxf as ez
        self.ez = ez
        self.project = project
        self.doc = ez.new("R2010", setup=True)
        self.doc.header["$INSUNITS"] = 1                    # inches
        self.layers = {}
        self.blocknames = {}
        self.add_layer("0", 7, "continuous", 0.0)
        for ly in project.layers.values():
            self.add_layer(ly.name, ly.color, ly.linetype, ly.lineweight)

    # ------------------------------------------------------------ tables
    def add_layer(self, name, color=7, linetype="continuous", weight=0.0):
        """Layer names are case-insensitive in DXF: 'Dashed' and 'DASHED' are one layer."""
        n = safe_name(name)
        key = n.lower()
        if key in self.layers:
            return self.layers[key]
        existing = next((l.dxf.name for l in self.doc.layers if l.dxf.name.lower() == key), None) \
            if not isinstance(self.doc.layers, list) else None
        if existing is not None:
            self.layers[key] = existing
            return existing
        self.layers[key] = n
        if n == "0":
            return n
        lt = self.linetype(linetype)
        attrs = {"color": abs(int(color)) or 7}
        if lt:
            attrs["linetype"] = lt
        if weight > 0:
            attrs["lineweight"] = lineweight(weight)
        self.doc.layers.add(n, dxfattribs=attrs)
        return n

    def linetype(self, name):
        if not name or name.lower() == "continuous":
            return None
        for cand in (name, name.upper()):
            if cand in self.doc.linetypes:
                return cand
        return None

    def attribs(self, st: m.Style):
        d = {"layer": self.add_layer(st.layer or "0", 7)}
        if st.color is not None:
            d["color"] = abs(int(st.color))
        lt = self.linetype(st.linetype)
        if lt:
            d["linetype"] = lt
        return d

    def block_name(self, name):
        if name not in self.blocknames:
            base, n, k = safe_name(name), safe_name(name), 1
            while n.lower() in {v.lower() for v in self.blocknames.values()}:
                k += 1; n = f"{base}_{k}"
            self.blocknames[name] = n
        return self.blocknames[name]

    # ------------------------------------------------------------ entities
    def add_entity(self, lay, e):
        a = self.attribs(e.style)
        if isinstance(e, m.Line):
            lay.add_line((e.x1, e.y1), (e.x2, e.y2), dxfattribs=a)
        elif isinstance(e, m.Rect):
            lay.add_lwpolyline([(e.x, e.y), (e.x + e.w, e.y), (e.x + e.w, e.y + e.h), (e.x, e.y + e.h)],
                               close=True, dxfattribs=a)
        elif isinstance(e, m.Circle):
            lay.add_circle((e.cx, e.cy), e.r, dxfattribs=a)
            if e.filled:
                h = lay.add_hatch(color=a.get("color", 256), dxfattribs={"layer": a["layer"]})
                h.paths.add_edge_path().add_arc((e.cx, e.cy), e.r, 0, 360)
        elif isinstance(e, m.Arc):
            lay.add_arc((e.cx, e.cy), e.r, e.start, e.end, dxfattribs=a)
        elif isinstance(e, m.Text):
            self.add_text(lay, e, a)

    def add_text(self, lay, t: m.Text, a):
        txt = text_value(t)
        if not txt:
            return
        rich = getattr(t, "rich", False)
        if rich or "\n" in txt:
            d = dict(a, insert=(t.x, t.y + t.height), char_height=t.height, rotation=t.rotation,
                     attachment_point=ATTACH.get(t.align, 1))
            lay.add_mtext(mtext_markup(txt, rich, t.font), dxfattribs=d)
            return
        d = dict(a, insert=(t.x, t.y), height=t.height, rotation=t.rotation)
        if t.align in ("center", "right"):
            d.update(halign=HALIGN[t.align], align_point=(t.x, t.y))
        lay.add_text(txt, dxfattribs=d)

    def define_block(self, name):
        blk = self.project.blocks[name]
        dn = self.block_name(name)
        if dn in self.doc.blocks:
            return dn
        for ly in blk.layers.values():
            self.add_layer(ly.name, ly.color, ly.linetype, ly.lineweight)
        b = self.doc.blocks.new(name=dn)
        for e in leaves(blk.entities):
            if isinstance(e, m.Text) and e.source in LABEL_ATTR:
                continue                                     # these become attributes
            self.add_entity(b, e)
        for tag, (x, y), h, al, vis in block_attdefs(blk):
            d = {"insert": (x, y), "height": h, "layer": "0"}
            if not vis:
                d["flags"] = 1
            if al in ("center", "right"):
                d.update(halign=HALIGN[al], align_point=(x, y))
            b.add_attdef(tag, (x, y), "", dxfattribs=d)
        return dn

    def add_ref(self, lay, sheet, ref: m.BlockRef):
        blk = self.project.blocks.get(ref.block)
        if blk is None:
            return
        dn = self.define_block(ref.block)
        d = {"layer": self.add_layer(ref.style.layer or "0", 7), "rotation": ref.rotation}
        if ref.mirror:
            d["xscale"] = -1.0
        if ref.style.color is not None:
            d["color"] = abs(int(ref.style.color))
        ins = lay.add_blockref(dn, (ref.x, ref.y), dxfattribs=d)
        for tag, val, (x, y), h, al, vis in ref_attributes(self.project, sheet, blk, ref):
            ad = {"height": h, "rotation": 0.0, "layer": d["layer"]}
            if not vis:
                ad["flags"] = 1
            if al in ("center", "right"):
                ad.update(halign=HALIGN[al], align_point=(x, y))
            ins.add_attrib(tag, val, (x, y), dxfattribs=ad)

    # ------------------------------------------------------------ sheets
    def add_sheet(self, sheet: m.Sheet):
        from . import fields
        fields.refresh_sheet(self.project, sheet)
        msp = self.doc.modelspace()
        for e in leaves(display_frame(sheet)):
            self.add_entity(msp, e)
        for e in leaves(sheet.entities):
            if isinstance(e, m.BlockRef):
                self.add_ref(msp, sheet, e)
            elif isinstance(e, (m.Line, m.Rect, m.Circle, m.Arc, m.Text)):
                self.add_entity(msp, e)
        lay = self.add_layer("WIRE_NUMBERS", 7)
        for x, y, rot, text, mode in nb.net_labels(self.project, sheet):
            msp.add_text(text, dxfattribs={"layer": lay, "insert": (x, y), "height": 0.09, "rotation": rot,
                                           "halign": 1, "align_point": (x, y)})

    def save(self, path):
        self.doc.saveas(path)


def export_sheet(project: m.Project, sheet: m.Sheet, path: str, ez=None) -> None:
    ex = Exporter(project, ez)
    ex.add_sheet(sheet)
    ex.save(path)


def export_project(project: m.Project, folder: str, ez=None, sheets=None):
    """One file per sheet, named after its tab (01 Title.dxf), into `folder` (created). -> [paths]."""
    import os
    from .exportnames import sheet_stem
    os.makedirs(folder, exist_ok=True)
    paths = []
    for pg in (sheets if sheets is not None else sorted(project.sheets)):
        p = os.path.join(folder, sheet_stem(project.sheets[pg]) + ".dxf")
        export_sheet(project, project.sheets[pg], p, ez)
        paths.append(p)
    return paths
