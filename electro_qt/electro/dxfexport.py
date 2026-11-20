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
LABEL_ATTR = {"{description}": "DESCRIPTION", "{part_label}": "PART_LABEL", "{tag}": "TAG", "{xref}": "XREF",
              "{header}": "HEADER"}
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
            if r.bold or r.italic or r.font:
                codes += f"\\f{(r.font or fam).replace('|', '')}|b{int(r.bold)}|i{int(r.italic)};"
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
            if t.source == "{header}":
                val = bk.header_plain(project, blk, ref, ctx)
            wx, wy = bk._to_world((t.x, t.y), ref)
            ox, oy = bk.label_offset(ref)
            out.append((tag, val, (wx + ox, wy + oy), t.height, t.align, True))
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
        self.dim_units = "in"
        self.dim_th = 0.14
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
        elif isinstance(e, m.PanelObj):
            self.add_panel(lay, e, a)
        elif isinstance(e, m.Dim):
            self.add_dim(lay, e, a)

    def add_dim(self, lay, d, a, units="in"):
        """A horizontal / vertical dimension drawn as lines + text (extension lines, dimension line, arrow heads)."""
        import math
        from . import panel as pn
        p1, p2 = (d.x1, d.y1), (d.x2, d.y2)
        pa, pb = pn.dim_line(d)
        th = d.th or self.dim_th
        k = th / 0.14
        for p, q in ((p1, pa), (p2, pb)):
            dx, dy = q[0] - p[0], q[1] - p[1]
            n = math.hypot(dx, dy)
            if n > 0.05:
                ux, uy = dx / n, dy / n
                lay.add_line((p[0] + ux * 0.05, p[1] + uy * 0.05), (q[0] + ux * 0.08, q[1] + uy * 0.08), dxfattribs=a)
        lay.add_line(pa, pb, dxfattribs=a)
        L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        if L > 1e-9:
            ux, uy = (pb[0] - pa[0]) / L, (pb[1] - pa[1]) / L
            for tip, s in ((pa, 1.0), (pb, -1.0)):
                bx, by = tip[0] + s * ux * 0.12 * k, tip[1] + s * uy * 0.12 * k
                nx, ny = -uy * 0.03 * k, ux * 0.03 * k
                lay.add_line(tip, (bx + nx, by + ny), dxfattribs=a)
                lay.add_line(tip, (bx - nx, by - ny), dxfattribs=a)
        mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        vert = d.orient == "v"
        ins = (mid[0] - 0.05, mid[1]) if vert else (mid[0], mid[1] + 0.05)
        t = dict(a, insert=ins, height=th, rotation=90 if vert else 0, halign=1, valign=0, align_point=ins)
        lay.add_text(pn.dim_text(pn.dim_value(d), self.dim_units), dxfattribs=t)

    def add_panel(self, lay, o, a):
        """A panel layout object: its outline, a part's DIN rail centre line, and its label (to scale, inches)."""
        from . import panel as pn
        x0, y0, x1, y1 = pn.box(o)
        lay.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs=a)
        if o.kind == "terminals" and o.qty > 1:                  # the stacked blocks
            for i in range(1, o.qty):
                if pn.axis(o) == "x":
                    x = x0 + (x1 - x0) * i / o.qty
                    lay.add_line((x, y0), (x, y1), dxfattribs=a)
                else:
                    y = y0 + (y1 - y0) * i / o.qty
                    lay.add_line((x0, y), (x1, y), dxfattribs=a)
        if o.kind in ("rail", "duct"):
            p0, p1 = pn.end_points(o)
            da = dict(a)
            if self.linetype("dashed"):
                da["linetype"] = self.linetype("dashed")
            lay.add_line(p0, p1, dxfattribs=da)
        if o.kind == "terminals" or (o.kind == "part" and not o.tag and (o.ident or o.names or o.first != 1)):
            labels = pn.terminal_labels(o)
            n = len(labels)
            for i, t in enumerate(labels):
                if pn.axis(o) == "x":
                    c = (x0 + (x1 - x0) * (i + 0.5) / n, o.cy); cell = (x1 - x0) / n
                else:
                    c = (o.cx, y0 + (y1 - y0) * (i + 0.5) / n); cell = (y1 - y0) / n
                hgt = max(0.04, min(0.2, cell / max(len(t), 1) * 1.4))
                d = dict(a, insert=c, height=hgt, halign=1, valign=2, align_point=c, rotation=90 if pn.axis(o) == "x" else 0)
                lay.add_text(t, dxfattribs=d)
            return
        label = o.tag or (f"{o.block} x{o.qty}" if o.kind == "terminals" else o.block) or ("DIN rail" if o.kind == "rail" else "Wire duct" if o.kind == "duct" else "")
        if label and o.kind != "plate":
            hgt = max(0.05, min(0.25, (y1 - y0) * 0.3, (x1 - x0) / max(len(label), 1) * 1.4))
            d = dict(a, insert=(o.cx, o.cy), height=hgt, halign=1, valign=2)
            d["align_point"] = (o.cx, o.cy)
            lay.add_text(label, dxfattribs=d)

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
        self.dim_units = sheet.dim_units
        self.dim_th = sheet.dim_th
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
