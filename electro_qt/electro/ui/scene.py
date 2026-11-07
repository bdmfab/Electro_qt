"""Editor scene: sheet frame, grid, snapping, tools, model<->item sync."""
from __future__ import annotations
import copy
import math
import time
import weakref
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QLineF
from PySide6.QtGui import QColor, QPen, QPolygonF, QFont, QUndoStack, QUndoCommand, QBrush, QPainterPath
from PySide6.QtWidgets import (QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsPathItem, QApplication,
                               QInputDialog)
from .. import model as m
import copy as _copy
from ..geometry import (dist_point_segment, walk, bounds, align_moves, snapshot, restore,
                        rotate_entity, mirror_entity, clone_entity, translate, leaves,
                        array_linear, array_polar, line_nodes, line_chain, line_grips, circle_grip,
                        segment_state, shift_segment)
from .. import blocks as bk
from .. import numbering as nb
from .. import junctions as jn
from ..snap import snap_to_grid
from .. import fields
from ..templates import display_frame
from . import clipboard
from ..snap import snap, SnapSettings
from .items import build_item, THEME, make_pen, aci_color
from .commands import (BlockDefCmd, AddCmd, DeleteCmd, MoveCmd, EditCmd, MoveEachCmd, LayerStateCmd, StateCmd)

KEEP = object()          # "leave unchanged" marker for apply_props(color=...)
DEFAULT_BG = "#1b1d21"
CLICK_DELAY = 0.3          # seconds an object must be held before it can be dragged
SNAP_COLOR = QColor("#ffd400")


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


AC_SCHEME = "<phase_incident><L|T><phase>"       # the "AC sets" scheme
UNNUMBERED_LABELS = {"PE", "GND", "G"}            # ground wires are not numbered
ROTATE_LABELS = [("90\u00b0 counter-clockwise", 90), ("90\u00b0 clockwise", -90), ("180\u00b0", 180)]
ALIGN_LABELS = [("Left", "left"), ("Right", "right"), ("Top", "top"), ("Bottom", "bottom"),
                ("Center (horizontal)", "hcenter"), ("Middle (vertical)", "vcenter")]

# (the sheet frame now comes from the sheet's template: sheet.frame)


class EditorScene(QGraphicsScene):
    status = Signal(str)          # cursor / snap readout
    prompt = Signal(str)          # what the active tool wants next
    block_made = Signal(object)   # a BlockDef was just made (main saves it to the shared library)
    blocks_changed = Signal()     # a block definition was added / removed
    tool_changed = Signal(str)    # tool name (so the toolbar can follow)
    layers_changed = Signal()
    edit_block_requested = Signal(str)     # open a block's geometry in its own tab

    def __init__(self, project: m.Project, sheet: m.Sheet, parent=None):
        super().__init__(parent)
        self.project, self.sheet = project, sheet
        self.apply_goto = None           # set by the main window: place From / To connectors
        self.scene_for_page = None       # set by the main window: page -> that sheet's scene
        self.block_edit = None          # {"name": ...} when this tab is editing a block's geometry
        self.undo = QUndoStack(self)
        self.printing = False            # PDF export: white page, no grid, no editing marks
        self._label_items = []
        self.undo.indexChanged.connect(lambda _i: (self.refresh_wire_labels(), self.update()))
        self.snap_settings = SnapSettings(origin=(sheet.grid_x0, sheet.zone0_y))
        self.apply_grid_divisions(sheet.grid_divisions)
        self.show_grid = True
        self.view_scale = 80.0
        self.current_layer = "0"
        self.cursor = SnapResultLite((0.0, 0.0), "")
        self.raw = (0.0, 0.0)               # unsnapped cursor position
        self.last_tool = None               # for right-click / Enter repeat
        self.resize_target = None           # group being resized (Resize tool)
        self.bg = QColor(DEFAULT_BG)
        self.text_style_name = "Default"
        self.folder_choices = []
        self.pending_block = None
        self.place_block_name, self.place_rot, self.last_slot, self.last_block = None, 0.0, "", None
        self.grip_drag = None
        self._press_time, self._press_on_item = 0.0, False
        self.grip_hover = None
        self.grip_anchor = None
        self.preset_name = "3ph+PE"
        self.fillet_radius = 0.1
        self.chamfer_d1 = 0.1
        self.chamfer_d2 = 0.1
        self._items: dict[str, object] = {}
        self._ref = weakref.ref(self)
        self.tool = None
        self.request_tool("select")
        self.rebuild()

    # ------------------------------------------------------------ appearance
    def set_background(self, color):
        self.bg = QColor(color)
        THEME["light"] = self.bg.lightness() > 140
        self.rebuild()                      # pens depend on the background (white <-> black)
        self.update()

    def current_preset(self):
        pres = self.project.multiline_presets
        return pres.get(self.preset_name) or (next(iter(pres.values())) if pres else None)

    def ensure_preset_layers(self, preset) -> bool:
        """Offer to create any layers a colour standard names that do not exist yet,
        using the standard's colours (PE is created unnumbered)."""
        missing = [i for i, n in enumerate(preset.layers) if n not in self.layers]
        if not missing:
            return True
        from PySide6.QtWidgets import QMessageBox
        names = ", ".join(preset.layers[i] for i in missing)
        r = QMessageBox.question(QApplication.activeWindow(), preset.name,
                                 f"These layers do not exist yet: {names}.\nCreate them with the {preset.name} colors?")
        if r != QMessageBox.StandardButton.Yes:
            return False
        before = self.capture_layer_state()
        for i in missing:
            label = preset.labels[i]
            numbered = label.upper() not in UNNUMBERED_LABELS
            self.layers[preset.layers[i]] = m.Layer(preset.layers[i], preset.colors[i], "wire", numbered,
                                                    AC_SCHEME if numbered else "", phase=label)
        self.undo.push(LayerStateCmd(self, before, self.capture_layer_state()))
        return True

    # ------------------------------------------------------------ grid
    def apply_grid_divisions(self, n: int):
        """n = grid lines between the major (row-centre) lines. 0 = majors only."""
        n = max(0, int(n))
        self.sheet.grid_divisions = n
        self.snap_settings.grid_step = self.sheet.row_pitch / (n + 1)
        self.update()

    # ------------------------------------------------------------ model sync
    @property
    def layers(self):
        return self.project.layers

    @staticmethod
    def _strip_ids(it):
        if hasattr(it, "entity_id"):
            del it.entity_id
        for c in it.childItems():
            EditorScene._strip_ids(c)

    def rebuild(self):
        fields.refresh_project(self.project)         # {job}, {page}, ... in text
        self.clear(); self._items.clear()
        self.setSceneRect(-5, -5, self.sheet.width + 10, self.sheet.height + 10)
        for e in display_frame(self.sheet):          # border, zone markers, title block (title block heavier)
            it = build_item(e, self.layers, self._ref)
            if it is None:
                continue
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            it.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            it.setZValue(-5)
            self._strip_ids(it)                      # border / title block: nothing to hover, pick or delete
            self.addItem(it)
        self._add_logo()
        for e in self.sheet.entities:
            self._add_item(e)
        self._label_items = []
        self.refresh_wire_labels()

    def refresh_wire_labels(self):
        """One number label per numbered wire (drawn, not stored; follows the geometry)."""
        for it in getattr(self, "_label_items", []):
            if it.scene() is self:
                self.removeItem(it)
        self._label_items = []
        self._label_hits = []                       # (item, lines) for clicking a number
        for x, y, rot, text, mode, lines in nb.net_labels_full(self.project, self.sheet):
            t = m.Text(x, y, text, text, 0.09, rot, m.Style("0", color=7 if mode == "auto" else 11), align="center")
            it = build_item(t, self.layers, self._ref)
            if it is None:
                continue
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            it.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            it.setZValue(-3)
            self.addItem(it)
            self._label_items.append(it)
            self._label_hits.append((it, lines))

    def _is_label(self, it):
        return any(it is x for x, _ in getattr(self, "_label_hits", []))

    def label_at(self, pos):
        """Lines of the wire whose number label is under `pos` (scene point), else None."""
        pad = 3.0 / max(self.view_scale, 1e-6)
        for it, lines in getattr(self, "_label_hits", []):
            if it.scene() is self and it.sceneBoundingRect().adjusted(-pad, -pad, pad, pad).contains(pos):
                return lines
        return None

    def logo_box(self):
        sh = self.sheet
        if sh.logo_box:
            return sh.logo_box
        return (15.134, 6.55, 1.4, 4.2) if (sh.width, sh.height) == (17.0, 11.0) else None

    def _add_logo(self):
        from PySide6.QtGui import QPixmap
        from .items import LogoItem
        name, box = self.project.info.get("logo"), self.logo_box()
        data = self.project.assets.get(name) if name else None
        if not data or not box:
            return
        pm = QPixmap()
        if pm.loadFromData(data):
            self.addItem(LogoItem(pm, box))

    def _add_item(self, e, selected=False):
        it = build_item(e, self.layers, self._ref)
        if it is None:
            return
        self.addItem(it)
        self._items[e.id] = it
        if selected:
            it.setSelected(True)

    def sync_add(self, e):
        self._add_item(e)

    def sync_remove(self, eid):
        it = self._items.pop(eid, None)
        if it is not None:
            self.removeItem(it)

    def refresh_xrefs(self):
        """Re-draw the placed parts that show a cross-reference (it depends on other parts)."""
        withx = {n for n, b in self.project.blocks.items()
                 if any(isinstance(t, m.Text) and t.source == "{xref}" for t in b.entities)}
        if not withx:
            return
        for r in leaves(self.sheet.entities):
            if isinstance(r, m.BlockRef) and r.block in withx and r.id in self._items:
                self.sync_refresh(r)

    def sync_refresh(self, e):
        old = self._items.get(e.id)
        sel = old.isSelected() if old is not None else False
        self.sync_remove(e.id)
        self._add_item(e, sel)

    def selected_entities(self):
        ids = {it.entity_id for it in self.selectedItems() if hasattr(it, "entity_id")}
        return [e for e in self.sheet.entities if e.id in ids]

    # ------------------------------------------------------------ layers
    def is_numbered_wire(self, layer_name):
        lay = self.layers.get(layer_name)
        return bool(lay and lay.kind == "wire" and lay.numbered)

    def tag_wire(self, e):
        if isinstance(e, m.Line) and self.is_numbered_wire(e.style.layer) and e.number is None:
            e.number = m.WireNumber("auto", "")

    def capture_layer_state(self):
        ents = {}
        for sh in self.project.sheets.values():
            for e in walk(sh.entities):         # includes everything inside groups
                ents[e.id] = (e, e.style.layer, copy.deepcopy(getattr(e, "number", None)))
        return {"layers": copy.deepcopy(self.project.layers), "ents": ents}

    def restore_layer_state(self, state):
        self.project.layers.clear()
        self.project.layers.update(copy.deepcopy(state["layers"]))
        for e, layer, number in state["ents"].values():
            e.style.layer = layer
            if isinstance(e, m.Line):
                e.number = copy.deepcopy(number)
        if self.current_layer not in self.project.layers:
            self.current_layer = "0"
        self.rebuild()
        self.layers_changed.emit()

    # ------------------------------------------------------------ creation
    def new_style(self, color=None) -> m.Style:
        return m.Style(layer=self.current_layer, color=color)

    def add_entities(self, entities, label="Add"):
        for e in entities:
            self.tag_wire(e)
        self.undo.push(AddCmd(self, entities, label))

    def delete_selected(self):
        sel = self.selected_entities()
        if sel:
            self.undo.push(DeleteCmd(self, sel))

    def pick_line(self, pt, exclude=None):
        """Nearest Line within ~8 px of pt (model coords)."""
        tol = 8.0 / self.view_scale
        best, bd = None, tol
        for e in self.sheet.entities:
            if isinstance(e, m.Line) and e is not exclude:
                d = dist_point_segment(pt, (e.x1, e.y1), (e.x2, e.y2))
                if d <= bd:
                    best, bd = e, d
        return best

    # ------------------------------------------------------------ tools
    def request_tool(self, name):
        from .tools import TOOLS
        self.set_tool(TOOLS[name](self))
        self.tool_changed.emit(name)

    def set_tool(self, tool):
        left_tool = self.tool is not None and self.tool.name != "select"
        if self.tool is not None:
            self.tool.cancel()
        self.tool = tool
        if tool.name not in ("select", "resize", "origin", "base"):
            self.last_tool = tool.name
        if left_tool or tool.name != "select":
            self.clearSelection()          # no stale tool highlights
        for v in self.views():
            v.setDragMode(QGraphicsView.DragMode.RubberBandDrag if tool.name == "select"
                          else QGraphicsView.DragMode.NoDrag)
            v.viewport().setCursor(Qt.CursorShape.ArrowCursor if tool.name == "select"
                                   else Qt.CursorShape.CrossCursor)
        self.prompt.emit(tool.hint())
        self.update()

    def tool_done(self):
        """A tool finished its job: back to Select (right-click / Enter repeats it)."""
        self.request_tool("select")

    def repeat_last(self):
        if self.last_tool:
            self.request_tool(self.last_tool)

    # ------------------------------------------------------------ groups / menu
    def _select_entities(self, entities):
        self.clearSelection()
        for e in entities:
            it = self._items.get(e.id)
            if it is not None:
                it.setSelected(True)

    def group_selected(self):
        sel = self.selected_entities()
        if len(sel) < 2:
            return
        g = m.Group(list(sel))
        self.undo.push(EditCmd(self, "Group", add=[g], remove=sel))
        self._select_entities([g])

    def ungroup_selected(self):
        groups = [e for e in self.selected_entities() if isinstance(e, m.Group)]
        if not groups:
            return
        kids = [c for g in groups for c in g.children]
        self.undo.push(EditCmd(self, "Ungroup", add=kids, remove=groups))
        self._select_entities(kids)

    def align_selected(self, mode):
        items = [(e, bounds([e], self.project.blocks)) for e in self.selected_entities()]
        items = [(e, b) for e, b in items if b]
        moves = [(e, dx, dy) for e, dx, dy in align_moves(items, mode) if abs(dx) > 1e-9 or abs(dy) > 1e-9]
        if moves:
            self.undo.push(MoveEachCmd(self, moves, "Align"))

    # ------------------------------------------------------------ properties / arrays
    def apply_props(self, layer=None, color=KEEP, weight=None, tstyle=None, radius=None):
        """Change layer / colour override / line-weight override (and text font, height,
        justification) of the selection as one undo step. Groups apply to their children."""
        sel = self.selected_entities()
        if not sel:
            return
        before, after = [], []
        for e in leaves(sel):
            b = {"style": e.style}
            st = dict(vars(e.style))
            if layer is not None:
                st["layer"] = layer
            if color is not KEEP:
                st["color"] = color
            if weight is not None:
                st["width"] = weight
            a = {"style": m.Style(**st)}
            if isinstance(e, m.Line):
                b["number"] = e.number
                lay = layer if layer is not None else e.style.layer
                if self.is_numbered_wire(lay):
                    a["number"] = e.number or m.WireNumber("auto", "")
                else:
                    a["number"] = None
            if isinstance(e, m.Text):
                b.update(font=e.font, height=e.height, align=e.align, tstyle=e.tstyle)
                ts = self.project.text_styles.get(tstyle) if tstyle else None
                if ts is not None:      # the style owns font, height, justification and colour
                    st["color"] = ts.color if color is KEEP else color
                    a = {"style": m.Style(**st)}
                    a.update(font=ts.font, height=ts.height, align=ts.align, tstyle=ts.name)
                else:
                    a.update(font=e.font, height=e.height, align=e.align, tstyle=e.tstyle)
            if isinstance(e, m.Circle):
                b["r"] = e.r
                a["r"] = e.r if radius is None else max(0.01, radius)
            before.append((e, b)); after.append((e, a))
        self.undo.push(StateCmd(self, sel, before, after, "Properties"))

    def array_dialog(self):
        sel = self.selected_entities()
        if not sel:
            self.say("Select something to array first")
            return
        from .arraydlg import ArrayDialog
        dlg = ArrayDialog(QApplication.activeWindow(), self.sheet.row_pitch)
        if not dlg.exec():
            return
        v = dlg.values()
        try:
            if v["mode"] == "linear":
                clones = array_linear(sel, v["rows"], v["cols"], v["dx"], v["dy"], v["inc"], v["step"])
            else:
                b = bounds(sel, self.project.blocks)
                ctr = self._grid_pt(((b[0] + b[2]) / 2 + v["cx"], (b[1] + b[3]) / 2 + v["cy"])) \
                    if v["relative"] else (v["cx"], v["cy"])
                clones = array_polar(sel, v["count"], v["angle"], ctr, v["rotate"], v["inc"], v["step"], self.project.blocks)
        except ValueError as ex:
            self.say(str(ex)); return
        if clones:
            self.retag(clones)
            self.add_entities(clones, "Array")
            self.say(f"Array: {len(clones)} new object(s)")

    # ------------------------------------------------------------ clipboard
    def _grid_pt(self, pt):
        ss = self.snap_settings
        return snap_to_grid(pt, ss.grid_step, ss.origin) if ss.grid else pt

    def copy_selected(self):
        sel = self.selected_entities()
        if not sel:
            return False
        b = bounds(sel, self.project.blocks)
        clipboard.CLIP["items"] = [_copy.deepcopy(e) for e in sel]
        first = next((e for e in leaves(sel) if isinstance(e, m.BlockRef)), None)     # a part: its origin
        auto = (first.x, first.y) if first is not None else (self._grid_pt((b[0], b[1])) if b else (0.0, 0.0))
        clipboard.CLIP["base"] = auto
        self.request_tool("base")                         # the user may pick another base point
        self.say(f"Copied {len(sel)} object(s). Click a base point, or Enter to keep the marked one")
        return True

    def cut_selected(self):
        if self.copy_selected():
            self.delete_selected()
            self.request_tool("base")

    def paste(self):
        if not clipboard.CLIP["items"]:
            self.say("Nothing to paste"); return
        self.request_tool("paste")

    def paste_at(self, pt):
        dx, dy = pt[0] - clipboard.CLIP["base"][0], pt[1] - clipboard.CLIP["base"][1]
        clones = [clone_entity(e) for e in clipboard.CLIP["items"]]
        for c in clones:
            translate(c, dx, dy)
        self.retag(clones)
        self.add_entities(clones, "Paste")
        return clones

    # ------------------------------------------------------------ rotate / mirror
    def _transform_selected(self, label, fn):
        """fn(entity, pivot) mutates in place; the whole selection is one undo step.
        The pivot is the centre of the selection, rounded to the grid so grid-aligned
        drawings stay on the grid."""
        sel = self.selected_entities()
        if not sel:
            return
        b = bounds(sel, self.project.blocks)
        pivot = self._grid_pt(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
        before = snapshot(sel)
        try:
            for e in sel:
                fn(e, pivot)
        except ValueError as ex:
            restore(before)
            self.say(str(ex)); return
        self.undo.push(StateCmd(self, sel, before, snapshot(sel), label))

    def rotate_selected(self, deg):
        if self.tool is not None and self.tool.name == "place":      # turning the block being placed
            self.tool.rotate(deg); self.update(); return
        self._transform_selected("Rotate", lambda e, c: rotate_entity(e, c, deg))

    def rotate_custom(self):
        deg, ok = QInputDialog.getDouble(QApplication.activeWindow(), "Rotate", "Angle in degrees (counter-clockwise):",
                                         45.0, -360.0, 360.0, 2)
        if ok and deg:
            self.rotate_selected(deg)

    def mirror_selected(self, axis):
        if self.tool is not None and self.tool.name == "place":
            self.tool.flip(); self.update(); return
        self._transform_selected("Mirror", lambda e, c: mirror_entity(e, axis, c[0] if axis == "v" else c[1]))

    def explode_rects(self):
        rects = [e for e in self.selected_entities() if isinstance(e, m.Rect)]
        if not rects:
            return
        lines = []
        for r in rects:
            pts = [(r.x, r.y), (r.x + r.w, r.y), (r.x + r.w, r.y + r.h), (r.x, r.y + r.h)]
            for i in range(4):
                ln = m.Line(*pts[i], *pts[(i + 1) % 4], m.Style(**vars(r.style)))
                self.tag_wire(ln)
                lines.append(ln)
        self.undo.push(EditCmd(self, "Explode", add=lines, remove=rects))
        self._select_entities(lines)

    def start_resize(self, group):
        self.resize_target = group
        self.request_tool("resize")

    @staticmethod
    def _top(item):
        while item.parentItem() is not None:
            item = item.parentItem()
        return item

    def show_context_menu(self, ev):
        from PySide6.QtWidgets import QMenu
        lab = self.label_at(ev.scenePos())
        if lab is not None:
            self._select_entities(lab)
        hits = [self._top(it) for it in self.items(ev.scenePos()) if hasattr(it, "entity_id") and not self._is_label(it)]
        if lab is None and hits and not hits[0].isSelected():          # right-click on an unselected item selects it
            self.clearSelection(); hits[0].setSelected(True)
        sel = self.selected_entities()
        if not hits and not sel and lab is None:        # blank space, nothing selected
            self.repeat_last(); return
        groups = [e for e in sel if isinstance(e, m.Group)]
        menu, acts = QMenu(), {}
        if len(sel) >= 2:
            acts[menu.addAction("Group")] = self.group_selected
            sub = menu.addMenu("Align")                      # flyout
            for label, mode in ALIGN_LABELS:
                acts[sub.addAction(label)] = lambda md=mode: self.align_selected(md)
            if len(sel) >= 3:
                sub.addSeparator()
                acts[sub.addAction("Distribute horizontally")] = lambda: self.align_selected("dist_h")
                acts[sub.addAction("Distribute vertically")] = lambda: self.align_selected("dist_v")
        if sel:
            sub = menu.addMenu("Rotate")
            for label, deg in ROTATE_LABELS:
                acts[sub.addAction(label)] = lambda d=deg: self.rotate_selected(d)
            acts[sub.addAction("Custom angle...")] = self.rotate_custom
            sub = menu.addMenu("Mirror")
            acts[sub.addAction("Flip left-right")] = lambda: self.mirror_selected("v")
            acts[sub.addAction("Flip top-bottom")] = lambda: self.mirror_selected("h")
        if any(isinstance(e, m.Rect) for e in sel):
            acts[menu.addAction("Explode rectangle into lines")] = self.explode_rects
        if groups:
            acts[menu.addAction("Ungroup")] = self.ungroup_selected
        if len(sel) == 1 and groups:
            acts[menu.addAction("Resize")] = lambda g=groups[0]: self.start_resize(g)
        wires = self._selected_wires()
        if wires:
            acts[menu.addAction("Mark wire (start numbering here)...\tQ")] = self.mark_wire
            if any(w.mark != "" for w in wires):
                acts[menu.addAction("Clear wire mark")] = self.clear_mark
        if self._selected_any_wires():
            acts[menu.addAction("Wire number...")] = self.edit_wire_number
        cx = jn.crossing_near(self.project, self.sheet, (ev.scenePos().x(), ev.scenePos().y()), 8.0 / self.view_scale)
        if cx is not None:
            if cx.connected:
                acts[menu.addAction("Hop (remove connection dot)")] = lambda c=cx: self.set_crossing(c, False)
            else:
                acts[menu.addAction("Connect wires here (dot)")] = lambda c=cx: self.set_crossing(c, True)
        if sel:
            if len(sel) == 1 and isinstance(sel[0], m.BlockRef):
                acts[menu.addAction("Part properties...")] = lambda r=sel[0]: self.edit_part(r)
                acts[menu.addAction("Edit block geometry...")] = lambda r=sel[0]: self.edit_block_requested.emit(r.block)
            if any(isinstance(e, m.BlockRef) for e in sel):
                acts[menu.addAction("Explode block")] = self.explode_blocks
            acts[menu.addAction("Make block...")] = self.make_block_dialog
            acts[menu.addAction("Array...")] = self.array_dialog
        if sel or clipboard.CLIP["items"]:
            menu.addSeparator()
        if sel:
            acts[menu.addAction("Copy")] = self.copy_selected
            acts[menu.addAction("Cut")] = self.cut_selected
        if clipboard.CLIP["items"]:
            acts[menu.addAction("Paste")] = self.paste
        if sel:
            acts[menu.addAction("Delete")] = self.delete_selected
        if self.last_tool:
            menu.addSeparator()
            acts[menu.addAction(f"Repeat {self.last_tool}")] = self.repeat_last
        chosen = menu.exec(ev.screenPos())
        fn = acts.get(chosen)
        if fn:
            fn()

    # ------------------------------------------------------------ text styles
    def current_text_style(self):
        ts = self.project.text_styles
        return ts.get(self.text_style_name) or ts.get("Default") or m.TextStyle("Default")

    def restyle_text(self, names):
        """Copy style values into every Text that uses a style (all sheets).
        Used after the styles dialog, for the styles that changed or were deleted
        (deleted ones fall back to Default); other text keeps its own values."""
        for sh in self.project.sheets.values():
            for e in leaves(sh.entities):
                if isinstance(e, m.Text) and e.tstyle in names:
                    ts = self.project.text_styles.get(e.tstyle) or self.project.text_styles["Default"]
                    e.tstyle, e.font, e.height, e.align = ts.name, ts.font, ts.height, ts.align
                    e.style = m.Style(**{**vars(e.style), "color": ts.color})

    # ------------------------------------------------------------ grips (line ends / mid, circle radius)
    def grips(self):
        """[(kind, key, (x, y), entity)] for the selection. Selecting one line of a
        joined run shows grips on the whole run; only OPEN ends get end grips."""
        sel = self.selected_entities()
        out = []
        seeds = [e for e in sel if isinstance(e, m.Line)]
        if seeds:
            nodes = line_nodes([e for e in self.sheet.entities if isinstance(e, m.Line)])
            for ln in line_chain(seeds, nodes):
                for kind, key, pt in line_grips(ln, nodes):
                    out.append((kind, key, pt, ln))
        for e in sel:
            if isinstance(e, m.Circle):
                kind, key, pt = circle_grip(e)
                out.append((kind, key, pt, e))
        return out

    def _grip_at(self, raw):
        tol = 10.0 / self.view_scale
        best, bd = None, tol
        for g in self.grips():
            d = math.hypot(raw[0] - g[2][0], raw[1] - g[2][1])
            if d <= bd:
                best, bd = g, d
        return best

    def _begin_grip(self, g):
        kind, key, pt, e = g
        if kind == "mid":
            nodes = line_nodes([x for x in self.sheet.entities if isinstance(x, m.Line)])
            st = segment_state(e, nodes)
            before = [(l, {"x1": l.x1, "y1": l.y1, "x2": l.x2, "y2": l.y2}) for l in st["touched"]]
            self.grip_drag = {"kind": kind, "ent": e, "st": st, "before": before, "tops": st["touched"], "mid": pt}
        elif kind == "end":
            other = (e.x2, e.y2) if key == 1 else (e.x1, e.y1)
            self.grip_anchor = other
            self.grip_drag = {"kind": kind, "key": key, "ent": e, "tops": [e],
                              "before": [(e, {"x1": e.x1, "y1": e.y1, "x2": e.x2, "y2": e.y2})]}
        else:
            self.grip_drag = {"kind": kind, "ent": e, "tops": [e], "before": [(e, {"r": e.r})]}

    def _drag_grip(self, raw):
        d = self.grip_drag
        e, kind = d["ent"], d["kind"]
        if kind == "mid":
            ss = self.snap_settings
            g = snap_to_grid(raw, ss.grid_step, ss.origin) if ss.grid else raw
            nx, ny = d["st"]["n"]
            mx, my = d["mid"]
            shift_segment(d["st"], (g[0] - mx) * nx + (g[1] - my) * ny)
        elif kind == "end":
            x, y = self.cursor.point
            fx, fy = (e.x2, e.y2) if d["key"] == 1 else (e.x1, e.y1)
            if math.hypot(x - fx, y - fy) < 0.01:
                return
            if d["key"] == 1:
                e.x1, e.y1 = x, y
            else:
                e.x2, e.y2 = x, y
        else:
            x, y = self.cursor.point
            e.r = max(0.01, math.hypot(x - e.cx, y - e.cy))
        for t in d["tops"]:
            self.sync_refresh(t)

    def _end_grip(self, cancel=False):
        d, self.grip_drag, self.grip_anchor = self.grip_drag, None, None
        if d is None:
            return
        after = [(l, {k: getattr(l, k) for k in v}) for l, v in d["before"]]
        if cancel or after == d["before"]:
            restore(d["before"])
            for t in d["tops"]:
                self.sync_refresh(t)
            return
        self.undo.push(StateCmd(self, d["tops"], d["before"], after,
                                {"mid": "Move segment", "end": "Move end", "radius": "Resize circle"}[d["kind"]]))

    def _paint_grips(self, p, vs):
        h = 5.0 / vs
        colors = {"end": "#4d9dff", "mid": "#7ad07a", "radius": "#ff9f43"}
        for kind, key, (x, y), e in self.grips():
            active = (self.grip_drag is not None and self.grip_drag["ent"] is e and self.grip_drag["kind"] == kind) \
                or self.grip_hover == (kind, key, id(e))
            p.setPen(QPen(QColor("#0b1a2b"), 0))
            p.setBrush(QColor("#ffd400") if active else QColor(colors[kind]))
            p.drawRect(QRectF(x - h, y - h, 2 * h, 2 * h))
        d = self.grip_drag
        if d is not None and d["kind"] == "radius":
            self.draw_label(p, self.cursor.point, f"R {d['ent'].r:.3f}", vs)

    # ------------------------------------------------------------ blocks
    def slot_points(self):
        """World position of every wire# slot of the placed blocks (wire end snaps)."""
        pts = []
        for r in self.sheet.entities:
            if isinstance(r, m.BlockRef):
                blk = self.project.blocks.get(r.block)
                if blk is not None:
                    pts += [w for _, w in bk.block_slots(blk, r)]
        return pts

    def retag(self, entities):
        taken = []
        for r in leaves(entities):
            if isinstance(r, m.BlockRef):
                blk = self.project.blocks.get(r.block)
                if blk is not None:
                    r.props.pop("tag_mode", None)
                    r.tag = bk.assign_tag(self.project, blk, self.sheet, r.x, r.y, extra_taken=taken)
                    taken.append(r.tag)

    def make_block_dialog(self):
        sel = self.selected_entities()
        if not sel:
            self.say("Select the part's drawing (and its wire# slots) first"); return
        from PySide6.QtWidgets import QMessageBox
        from .blockdlg import BlockDialog
        marks = [e for e in leaves(sel) if isinstance(e, m.SlotMark)]
        dlg = BlockDialog(QApplication.activeWindow(), poles=max(1, len(marks) // 2),
                          folders=self.folder_choices, rules=self.project.prefix_rules,
                          slot_names=[mk.terminal for mk in marks])
        if not dlg.exec():
            return
        v = dlg.values()
        if not v["name"] or v["name"] in self.project.blocks:
            QMessageBox.warning(QApplication.activeWindow(), "Make block",
                                "Give the block a name that is not already in the library.")
            return
        origin = v.pop("origin", "center")
        if origin == "pick":                       # ask for the point, then finish
            self.pending_block = (v, sel)
            self.request_tool("origin")
            return
        if origin.startswith("slot:") and marks:
            mk = marks[min(int(origin[5:]), len(marks) - 1)]
            base = (mk.x, mk.y)
        else:
            b0 = bounds(sel)
            base = self._grid_pt(((b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2))
        self.finish_make_block(v, sel, base)

    def finish_make_block(self, v, sel, base):
        labels, pos = v.pop("labels"), v.pop("label_pos")
        name = v.pop("name")
        blk = bk.make_block(name, sel, base, labels, pos, **v)
        bk.capture_layers(self.project, blk)
        ref = m.BlockRef(name, base[0], base[1], style=m.Style("0"))
        self.undo.beginMacro("Make block")
        self.undo.push(BlockDefCmd(self, blk))
        ref.tag = bk.assign_tag(self.project, blk, self.sheet, base[0], base[1])
        self.undo.push(EditCmd(self, "Make block", add=[ref], remove=sel))
        self.undo.endMacro()
        self.block_made.emit(blk)
        self._select_entities([ref])
        self.say(f"Block '{name}' saved to the library ({len(blk.slots)} slot(s))")

    def explode_blocks(self):
        """Turn the selected placed parts back into plain drawing objects (and slot marks)."""
        refs = [e for e in self.selected_entities() if isinstance(e, m.BlockRef)]
        add = []
        for r in refs:
            blk = self.project.blocks.get(r.block)
            if blk is not None:
                add += bk.explode_block(self.project, self.sheet, blk, r)
        if not add:
            return
        self.undo.push(EditCmd(self, "Explode block", add=add, remove=refs))
        self._select_entities(add)
        self.say("Exploded. Edit it, then Make block to save it again")

    def place_block(self, name, pt, rot=0.0, mirror=False, tag=None):
        """Drop a block; wires that run through its slots are trimmed to them. `tag` names an
        off-page connector without asking."""
        blk = self.project.blocks[name]
        if bk.ensure_layers(self.project, blk):          # the block brings its layers (dashed ...) along
            self.layers_changed.emit()
        ref = m.BlockRef(name, pt[0], pt[1], rot, mirror, style=m.Style("0"))
        ref.tag = bk.assign_tag(self.project, blk, self.sheet, pt[0], pt[1])
        if blk.connector and tag is not None:
            ref.tag = tag
            ref.props["tag_mode"] = "manual"
        elif blk.connector:                     # off-page connector: its name joins it to the other sheet
            text, ok = QInputDialog.getText(QApplication.activeWindow(), "Off-page connector",
                                            "Connector name (use the same name on the other sheet):",
                                            text=getattr(self, "last_conn", ""))
            ref.tag = text.strip() if ok else ""
            ref.props["tag_mode"] = "manual"
            self.last_conn = ref.tag
        points = [w for _, w in bk.block_slots(blk, ref)]
        wires = [l for l in self.sheet.entities if isinstance(l, m.Line)
                 and self.layers.get(l.style.layer) is not None and self.layers[l.style.layer].kind == "wire"]
        mods, adds, rems = [], [ref], []
        for ln, pieces in bk.trim_ops(self.project, wires, [ref]):
            if not pieces:
                rems.append(ln); continue
            fields_ = dict(zip(("x1", "y1", "x2", "y2"), pieces[0]))
            manual = ln.number is not None and ln.number.mode != "auto"
            if manual and len(pieces) == 2:
                # a typed number stays with the longer piece (the rest of the wire); the new piece is automatic
                ln_len = [math.hypot(c[2] - c[0], c[3] - c[1]) for c in pieces]
                if ln_len[1] >= ln_len[0]:
                    fields_["number"] = m.WireNumber("auto", "")
            for pc in pieces[1:]:
                n = clone_entity(ln)
                n.x1, n.y1, n.x2, n.y2 = pc
                if manual and "number" in fields_:
                    n.number = m.WireNumber(ln.number.mode, ln.number.value)
                adds.append(n)
            mods.append((ln, fields_))
        self.undo.push(EditCmd(self, "Place block", modify=mods, add=adds, remove=rems))
        self.last_block = name
        return ref

    def edit_part(self, ref):
        """Description / part number / tag / label lines / terminal names of one placed part."""
        blk = self.project.blocks.get(ref.block)
        if blk is None:
            return
        from .partdlg import PartDialog
        dlg = PartDialog(QApplication.activeWindow(), self.project, blk, ref)
        if dlg.exec():
            tag, props = dlg.result()
            if tag != ref.tag or props != ref.props:
                self.undo.push(EditCmd(self, "Part properties", modify=[(ref, {"tag": tag, "props": props})]))

    # ------------------------------------------------------------ wire numbers
    def _selected_wires(self):
        return [e for e in self.selected_entities()
                if isinstance(e, m.Line) and nb._numbered_layer(self.project, e.style.layer)]

    def _selected_any_wires(self):
        return [e for e in self.selected_entities()
                if isinstance(e, m.Line) and nb._wire_layer(self.project, e.style.layer)]

    def mark_wire(self):
        wires = self._selected_wires()
        if not wires:
            return
        start, ok = QInputDialog.getInt(QApplication.activeWindow(), "Mark wire",
                                        "Numbering starts on this wire.\nStart incident (the first digit of its number):",
                                        nb.default_start(self.project, wires[0].style.layer), 0, 99)
        if ok:
            mods = [(w, {"mark": str(start)}) for w in wires[:1]]
            self.undo.push(EditCmd(self, "Mark wire", modify=mods))
            self.say("Marked. Use Update wire numbers (F5) to number from here")

    def clear_mark(self):
        mods = [(w, {"mark": ""}) for w in self._selected_wires() if w.mark != ""]
        if mods:
            self.undo.push(EditCmd(self, "Clear wire mark", modify=mods))

    def edit_wire_number(self):
        wires = self._selected_any_wires()
        if not wires:
            return
        from .numdlg import WireNumberDialog
        cur = wires[0].number or m.WireNumber("auto", "")
        mine = {w.id for w in wires}
        others = []
        for pg, net, val in nb.numbered_nets(self.project):
            if not ({l.id for l in net.lines} & mine):
                others.append((f"{val}   (sheet {pg:02d}, zone {bk.zone_text(self.project.sheets[pg], *net.anchor)})",
                               net.lines[0].id))
        dlg = WireNumberDialog(QApplication.activeWindow(), cur.mode, cur.value, others)
        if not dlg.exec():
            return
        mode, value, link = dlg.values()
        if mode == "goto":
            plan = nb.goto_plan(self.project, mine, link)
            if plan is None:
                return
            name, frm, to, val = plan
            if self.apply_goto:
                self.apply_goto([(name, frm, to)], numbers={id(to[1]): val})
            return
        ids = {id(w) for w in wires}
        mods = []
        for net in nb.build_nets(self.project, self.sheet, include={w.id for w in wires}):
            if any(id(l) in ids for l in net.lines):
                mods += [(l, {"number": m.WireNumber(mode, value)}) for l in net.lines]
        if mods:
            self.undo.push(EditCmd(self, "Wire number", modify=mods))

    def set_crossing(self, c, connect):
        if connect:
            dot = m.Circle(c.pt[0], c.pt[1], jn.DOT_R, m.Style(layer=c.vert.style.layer), filled=True)
            self.undo.push(AddCmd(self, [dot], "Connect crossing"))
        elif c.dot is not None:
            self.undo.push(DeleteCmd(self, [c.dot]))

    def _paint_hops(self, p, vs):
        """Hops and automatic T-junction dots - graphical only, computed on every repaint."""
        lines = jn.wire_lines(self.project, self.sheet)
        if not lines:
            return
        for c in jn.hops(self.project, self.sheet):
            v, h, (x, y) = c.vert, c.horiz, c.pt
            r = jn.HOP_R
            ux, uy = v.x2 - v.x1, v.y2 - v.y1
            L = math.hypot(ux, uy); ux, uy = ux / L, uy / L
            nx, ny = uy, -ux                                           # bulge toward +x
            if nx < 0 or (abs(nx) < 1e-9 and ny < 0):
                nx, ny = -nx, -ny
            vp = make_pen(v, self.layers); hp = make_pen(h, self.layers)
            bgpen = QPen(self.bg, vp.widthF() + 3); bgpen.setCosmetic(True)
            # erase the straight vertical stretch, put back the horizontal wire, draw the arc
            p.setPen(bgpen)
            p.drawLine(QLineF(x - ux * r, y - uy * r, x + ux * r, y + uy * r))
            hx, hy = h.x2 - h.x1, h.y2 - h.y1
            HL = math.hypot(hx, hy); hx, hy = hx / HL, hy / HL
            p.setPen(hp)
            p.drawLine(QLineF(x - hx * r * 1.6, y - hy * r * 1.6, x + hx * r * 1.6, y + hy * r * 1.6))
            p.setPen(vp)
            pts = []
            for i in range(17):
                a = math.pi * i / 16
                k = math.cos(a) * r; bulge = math.sin(a) * r
                pts.append((x - ux * k + nx * bulge, y - uy * k + ny * bulge))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(QLineF(a[0], a[1], b[0], b[1]))
        p.setPen(Qt.PenStyle.NoPen)
        for pt in jn.junction_dots(lines):
            lay = next((ln for ln in lines if nb._on_segment(pt, ln)), None)
            col = self.layers.get(lay.style.layer).color if lay and self.layers.get(lay.style.layer) else 7
            p.setBrush(aci_color(col))
            p.drawEllipse(QPointF(pt[0], pt[1]), jn.DOT_R, jn.DOT_R)

    def _paint_marks(self, p, vs):
        h = 5.0 / vs
        p.setPen(QPen(QColor("#ff8a1f"), 0)); p.setBrush(QColor("#ff8a1f"))
        for e in self.sheet.entities:
            if isinstance(e, m.Line) and e.mark != "":
                x, y = (e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2
                p.drawPolygon(QPolygonF([QPointF(x - h, y), QPointF(x, y + h), QPointF(x + h, y), QPointF(x, y - h)]))

    def set_tag(self, ref, tag):
        props = dict(ref.props)
        props["tag_mode"] = "manual"
        props.pop("tag_link", None)
        self.undo.push(EditCmd(self, "Edit tag", modify=[(ref, {"tag": tag, "props": props})]))

    def snap_at(self, pos: QPointF):
        tol = 10.0 / self.view_scale
        anchor = self.grip_anchor if self.grip_drag is not None else (self.tool.anchor if self.tool else None)
        r = snap((pos.x(), pos.y()), self.sheet.entities, self.snap_settings, tol, anchor, self.slot_points())
        return SnapResultLite(r.point, r.kind)

    def say(self, text):
        self.prompt.emit(text)

    # ------------------------------------------------------------ mouse/keys
    def mouseMoveEvent(self, ev):
        self.raw = (ev.scenePos().x(), ev.scenePos().y())
        self.cursor = self.snap_at(ev.scenePos())
        x, y = self.cursor.point
        self.status.emit(f"X {x:.3f}   Y {y:.3f}   {self.cursor.kind}")
        self._update_hover(ev.scenePos())
        if self.tool.name == "select":
            if self.grip_drag is not None:
                self._drag_grip(self.raw)
                ev.accept()
            else:
                g = self._grip_at(self.raw) if ev.buttons() == Qt.MouseButton.NoButton else None
                self.grip_hover = (g[0], g[1], id(g[3])) if g else None
                if (ev.buttons() & Qt.MouseButton.LeftButton and self._press_on_item
                        and time.monotonic() - self._press_time < CLICK_DELAY):
                    ev.accept()                    # still a click: hold for 300 ms to drag
                    return
                super().mouseMoveEvent(ev)
        else:
            self.tool.move(self.cursor.point)
        self.update()

    HOVER_TOOLS = ("select", "trim", "fillet", "chamfer")

    def _update_hover(self, pos):
        """Remember the object under the cursor so it can be shown in magenta (easy picking)."""
        self.hover_item = None
        if self.tool is None or self.tool.name not in self.HOVER_TOOLS or self.grip_drag is not None:
            return
        tol = 6.0 / max(self.view_scale, 1e-6)
        for it in self.items(QRectF(pos.x() - tol, pos.y() - tol, 2 * tol, 2 * tol),
                             Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder):
            if hasattr(it, "entity_id") and it.parentItem() is None and not self._is_label(it):
                self.hover_item = it
                return

    def _paint_block_origin(self, p, vs):
        ox, oy = bk.EDIT_ORIGIN
        r = 12.0 / vs
        p.setPen(QPen(QColor(255, 0, 255), 0)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(ox - r, oy), QPointF(ox + r, oy)); p.drawLine(QPointF(ox, oy - r), QPointF(ox, oy + r))
        p.drawEllipse(QPointF(ox, oy), r / 2, r / 2)

    def _paint_hover(self, p, vs):
        it = getattr(self, "hover_item", None)
        try:
            if it is None or it.scene() is not self:
                return
        except RuntimeError:                     # the item was deleted since the last mouse move
            self.hover_item = None
            return
        mag = QColor(255, 0, 255)
        pen = QPen(mag, 2.5); pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        def paint(item):
            if isinstance(item, QGraphicsPathItem):
                p.setPen(pen)
                p.setBrush(QBrush(mag) if item.brush().style() != Qt.BrushStyle.NoBrush else Qt.BrushStyle.NoBrush)
                p.drawPath(item.mapToScene(item.path()))
                return True
            kids = [c for c in item.childItems()]
            ok = False
            for c in kids:
                ok = paint(c) or ok
            return ok

        if not paint(it):
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(it.sceneBoundingRect())

    def mousePressEvent(self, ev):
        self.raw = (ev.scenePos().x(), ev.scenePos().y())
        if self.tool.name == "select":
            if ev.button() == Qt.MouseButton.RightButton:
                self.show_context_menu(ev)
                return
            if ev.button() == Qt.MouseButton.LeftButton:
                g = self._grip_at(self.raw)
                if g is not None:
                    self._begin_grip(g)
                    ev.accept(); return
                # a click on an object must not nudge it: movement is ignored for
                # CLICK_DELAY seconds after pressing on one (blank-space drags still box-select)
                lab = self.label_at(ev.scenePos())
                if lab is not None and not any(hasattr(it, "entity_id") and not self._is_label(it)
                                               for it in self.items(ev.scenePos())):
                    self._select_entities(lab)
                    ev.accept(); return
                self._press_time = time.monotonic()
                self._press_on_item = any(hasattr(it, "entity_id") and not self._is_label(it) for it in self.items(ev.scenePos()))
            super().mousePressEvent(ev)
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self.cursor = self.snap_at(ev.scenePos())
            self.tool.press(self.cursor.point)
        elif ev.button() == Qt.MouseButton.RightButton:
            self.tool.finish()
            if self.tool.name != "select":
                self.tool_done()
        if self.tool is not None:
            self.prompt.emit(self.tool.hint())
        self.update()

    def mouseReleaseEvent(self, ev):
        if self.grip_drag is not None:
            self._end_grip()
            ev.accept(); self.update(); return
        super().mouseReleaseEvent(ev)
        if self.tool.name != "select":
            if ev.button() == Qt.MouseButton.LeftButton:
                self.tool.release(self.cursor.point)
            return
        moved = [(it, it.pos()) for it in self.selectedItems()
                 if hasattr(it, "entity_id") and (it.pos().x() or it.pos().y())]
        if moved:
            dx, dy = moved[0][1].x(), moved[0][1].y()
            ents = self.selected_entities()
            for it, _ in moved:
                it.setPos(0, 0)
            refs = [e for e in leaves(ents) if isinstance(e, m.BlockRef)]
            moved_ids = {x.id for x in leaves(ents)}
            mods, adds, rems = bk.follow_plan(self.project, self.sheet, refs, dx, dy, moved_ids) if refs else ([], [], [])
            self.undo.beginMacro("Move")
            self.undo.push(MoveCmd(self, ents, dx, dy))
            if mods or adds or rems:
                self.undo.push(EditCmd(self, "Wires follow", modify=mods, add=adds, remove=rems))
            self._trim_wires_at(refs, {id(x) for x, _ in mods} | {id(x) for x in adds})
            self.undo.endMacro()

    def _trim_wires_at(self, refs, skip):
        """After a move: wires that now run through a block's slots are trimmed to them."""
        wires = [l for l in self.sheet.entities if isinstance(l, m.Line) and id(l) not in skip
                 and self.layers.get(l.style.layer) is not None and self.layers[l.style.layer].kind == "wire"]
        mods, adds, rems = [], [], []
        for ln, pieces in bk.trim_ops(self.project, wires, refs):
            if not pieces:
                rems.append(ln); continue
            mods.append((ln, dict(zip(("x1", "y1", "x2", "y2"), pieces[0]))))
            for pc in pieces[1:]:
                n = clone_entity(ln)
                n.x1, n.y1, n.x2, n.y2 = pc
                adds.append(n)
        if mods or adds or rems:
            self.undo.push(EditCmd(self, "Trim wires", modify=mods, add=adds, remove=rems))

    def mouseDoubleClickEvent(self, ev):
        if self.tool.name == "select":
            lab = self.label_at(ev.scenePos())
            if lab is not None:
                self._select_entities(lab)
                self.edit_wire_number()
                return
            for it in self.items(ev.scenePos()):
                e = next((x for x in self.sheet.entities if x.id == getattr(it, "entity_id", None)), None)
                if isinstance(e, m.Text):
                    self.edit_text(e)
                    return
                if isinstance(e, m.BlockRef):
                    self.edit_part(e)
                    return
                if isinstance(e, m.SlotMark):
                    name, ok = QInputDialog.getText(QApplication.activeWindow(), "Wire# slot", "Terminal name:", text=e.terminal)
                    if ok:
                        self.undo.push(EditCmd(self, "Rename slot", modify=[(e, {"terminal": name.strip()})]))
                    return
        super().mouseDoubleClickEvent(ev)

    def edit_text(self, e: m.Text):
        from .textdlg import RichTextDialog
        dlg = RichTextDialog(QApplication.activeWindow(), e.source, getattr(e, "rich", False), "Edit text", e.align)
        if not dlg.exec():
            return
        txt, rich = dlg.result_markup()
        if txt == e.source and rich == e.rich and dlg.align == e.align:
            return
        align = dlg.align

        class Edit(QUndoCommand):
            def __init__(s, scene, ent, new, nrich, nalign):
                super().__init__("Edit text")
                s.sc, s.e, s.new, s.nrich, s.old, s.orich = scene, ent, new, nrich, ent.source, ent.rich
                s.nal, s.oal = nalign, ent.align

            def _set(s, v, r, al):
                s.e.source, s.e.rich, s.e.align = v, r, al
                s.e.resolved = fields.resolve(v, fields.context(s.sc.project, s.sc.sheet))
                s.sc.sync_refresh(s.e)

            def redo(s): s._set(s.new, s.nrich, s.nal)
            def undo(s): s._set(s.old, s.orich, s.oal)
        self.undo.push(Edit(self, e, txt, rich, align))

    def keyPressEvent(self, ev):
        k = ev.key()
        enter = k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
        if k == Qt.Key.Key_Escape:
            if self.grip_drag is not None:
                self._end_grip(cancel=True)
            elif self.tool.name == "select":
                self.clearSelection()
            else:
                self.tool.cancel(); self.tool_done()
            ev.accept(); return
        if self.tool.name != "select" and self.tool.key(ev):
            self.prompt.emit(self.tool.hint()); self.update(); ev.accept(); return
        if k == Qt.Key.Key_Q and self.tool.name == "select" and not ev.modifiers():
            if not self._selected_wires():               # no wire selected: take the one under the cursor
                it = getattr(self, "hover_item", None)
                try:
                    if it is not None and it.scene() is self:
                        self.clearSelection(); it.setSelected(True)
                except RuntimeError:
                    pass
            if self._selected_wires():
                self.mark_wire()
            else:
                self.say("Q: select a numbered wire (or hover over it) to mark it")
            ev.accept(); return
        if enter:
            if self.tool.name == "select":
                self.repeat_last()                 # Space/Enter = repeat last command
            else:
                self.tool.finish(); self.tool_done()
            ev.accept(); return
        super().keyPressEvent(ev)

    # ------------------------------------------------------------ drawing
    def drawBackground(self, p, rect):
        p.fillRect(rect, self.bg)
        if self.printing:
            return
        fg = QColor("#000000") if THEME["light"] else QColor("#ffffff")
        GRID_MINOR, GRID_MAJOR = _mix(self.bg, fg, 0.07), _mix(self.bg, fg, 0.15)
        s = self.view_scale
        if self.show_grid:
            step = self.snap_settings.grid_step
            major = self.sheet.row_pitch
            ox, oy = self.snap_settings.origin
            if step < major - 1e-9 and step * s >= 6:
                self._grid(p, rect, step, ox, oy, GRID_MINOR)
            if major * s >= 5:
                self._grid(p, rect, major, ox, oy, GRID_MAJOR)

    def _grid(self, p, rect, step, ox, oy, color):
        p.setPen(QPen(color, 0))
        lines = []
        x = ox + math.floor((rect.left() - ox) / step) * step
        while x <= rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom())); x += step
        y = oy + math.floor((rect.top() - oy) / step) * step
        while y <= rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y)); y += step
        p.drawLines(lines)

    def drawForeground(self, p, rect):
        vs = self.view_scale
        if self.printing:
            self._paint_hops(p, vs)
            return
        if self.tool is not None:
            self._paint_hops(p, vs)
            self._paint_hover(p, vs)
            if self.block_edit:
                self._paint_block_origin(p, vs)
            self.tool.paint(p, vs)
            self._paint_marks(p, vs)
            if self.tool.name == "select":
                self._paint_grips(p, vs)
            if self.tool.name not in ("select", "resize"):
                self._snap_marker(p, vs)

    def _snap_marker(self, p, vs):
        (x, y), kind = self.cursor.point, self.cursor.kind
        h = 6 / vs
        marker = QColor("#c77700") if THEME["light"] else SNAP_COLOR
        p.setPen(QPen(marker, 0)); p.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "end":
            p.drawRect(QRectF(x - h, y - h, 2 * h, 2 * h))
        elif kind == "mid":
            p.drawPolygon(QPolygonF([QPointF(x - h, y - h), QPointF(x + h, y - h), QPointF(x, y + h)]))
        elif kind == "center":
            p.drawEllipse(QPointF(x, y), h, h)
        elif kind == "quad":
            p.drawPolygon(QPolygonF([QPointF(x - h, y), QPointF(x, y + h), QPointF(x + h, y), QPointF(x, y - h)]))
        else:
            c = h * 0.6
            p.setPen(QPen(QColor("#8a8f98"), 0))
            p.drawLine(QLineF(x - c, y, x + c, y)); p.drawLine(QLineF(x, y - c, x, y + c))

    def draw_label(self, p, pt, text, vs):
        p.save()
        p.setPen(QPen(QColor("#c77700") if THEME["light"] else SNAP_COLOR, 0))
        f = QFont("Sans Serif"); f.setPixelSize(12); p.setFont(f)
        p.translate(pt[0], pt[1]); p.scale(1 / vs, -1 / vs)
        p.drawText(QPointF(12, -12), text)
        p.restore()


class SnapResultLite:
    def __init__(self, point, kind):
        self.point, self.kind = point, kind
