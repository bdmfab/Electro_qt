"""Headless smoke test; skipped when PySide6 is not installed."""
import os
import pytest
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
from electro import model as m
from electro.ui.main import MainWindow
from electro.ui.tools import LineTool

app = QApplication.instance() or QApplication([])


def test_line_tool_undo_redo():
    w = MainWindow(); sc = w.scene_
    sc.project.layers["AC"] = m.Layer("AC", 1, "wire", True, "<incident><L|T><phase>")
    sc.current_layer = "AC"
    t = LineTool(sc); sc.set_tool(t)
    t.press((1.0, 1.0)); t.move((3.0, 1.2)); t.cur = (3.0, 1.0); t.press((3.0, 1.0))
    ln = sc.sheet.entities[0]
    assert (ln.x2, ln.y2) == (3.0, 1.0) and ln.number is not None   # AC wire layer is numbered
    sc.undo.undo(); assert sc.sheet.entities == []
    sc.undo.redo(); assert len(sc.sheet.entities) == 1


def test_typed_length():
    w = MainWindow(); sc = w.scene_
    t = LineTool(sc); sc.set_tool(t)
    t.press((0.0, 0.0)); t.move((5.0, 0.0)); t.typed = "2.5"; t.commit_typed(2.5)
    assert sc.sheet.entities[0].x2 == 2.5


def test_rect_returns_to_select_and_right_click_repeat_state():
    from electro.ui.tools import RectTool
    w = MainWindow(); sc = w.scene_
    sc.request_tool("rect")
    t = sc.tool; t.press((1.0, 1.0)); t.press((2.0, 2.0))
    assert sc.tool.name == "select" and sc.last_tool == "rect"
    sc.repeat_last(); assert sc.tool.name == "rect"


def test_trim_and_fillet_through_scene():
    w = MainWindow(); sc = w.scene_
    a, b = m.Line(0, 0, 10, 0), m.Line(5, -2, 5, 2)
    sc.add_entities([a, b])
    sc.request_tool("trim"); sc.raw = (8.0, 0.0); sc.tool.press((8.0, 0.0))
    assert (a.x1, a.x2) == (0, 5) and sc.tool.name == "select"
    sc.undo.undo(); assert (a.x1, a.x2) == (0, 10)
    l1, l2 = m.Line(0, 0, 5, 0), m.Line(0, 0, 0, 5)
    sc.add_entities([l1, l2])
    sc.fillet_radius = 1.0
    sc.request_tool("fillet")
    sc.raw = (3.0, 0.0); sc.tool.press((3.0, 0.0))
    sc.raw = (0.0, 3.0); sc.tool.press((0.0, 3.0))
    assert any(isinstance(e, m.Arc) for e in sc.sheet.entities)


def test_grid_divisions_step():
    w = MainWindow(); sc = w.scene_
    assert abs(sc.snap_settings.grid_step - 0.175) < 1e-9
    sc.apply_grid_divisions(0); assert abs(sc.snap_settings.grid_step - 0.35) < 1e-9


def test_tabs_and_title_block():
    w = MainWindow()
    assert w.tabs.count() == 1 and w.project.sheets[1].frame
    w.on_add_sheet.__func__  # exists
    from electro.templates import sheet_from_template
    p = w.project
    s = sheet_from_template(next(iter(p.templates.values())), 2, "Sheet 2")
    p.add_sheet(s); w._add_tab(s); w._refresh_all()
    assert w.tabs.count() == 2


def test_copy_paste_rotate_mirror():
    w = MainWindow(); sc = w.scene_
    sc.undo.push(__import__("electro.ui.commands", fromlist=["AddCmd"]).AddCmd(
        sc, [m.Line(m.new_id(), m.Style("0"), 1, 1, 3, 1)], "t"))
    for i in sc.items():
        if hasattr(i, "entity_id") and i.parentItem() is None:
            i.setSelected(True)
    sc.rotate_selected(90)
    ln = sc.sheet.entities[0]
    assert abs(ln.x1 - ln.x2) < 1e-9


def test_place_block_trims_wire():
    from electro import blocks as bk
    w = MainWindow(); sc = w.scene_
    sc.project.layers["W"] = m.Layer("W", 1, "wire")
    sc.project.blocks["K"] = bk.make_block("K", [m.SlotMark(0, 0, "1"), m.SlotMark(0, 0.7, "2"),
                                                 m.Line(0, 0.2, 0, 0.5, m.Style("0"))], (0, 0.35), tag_prefix="K")
    sc.sheet.entities.append(m.Line(3, 3, 3, 7, m.Style("W")))
    sc.rebuild()
    ref = sc.place_block("K", (3.0, 5.0))
    lines = [e for e in sc.sheet.entities if isinstance(e, m.Line)]
    assert len(lines) == 2 and ref.tag.startswith("K01")
    sc.undo.undo()
    assert len([e for e in sc.sheet.entities if isinstance(e, m.Line)]) == 1
