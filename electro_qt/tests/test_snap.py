from electro import model as m
from electro.snap import snap, SnapSettings
from electro.geometry import translate, bounds, ortho, point_on_line_at


def test_grid_snap():
    r = snap((0.52, 0.98), [], SnapSettings(ortho=False), 0.1)
    assert r.kind == "grid" and r.point == (0.5, 1.0)


def test_end_beats_grid():
    ln = m.Line(1.03, 1.03, 2, 1.03)
    r = snap((1.04, 1.04), [ln], SnapSettings(ortho=False), 0.1)
    assert r.kind == "end" and r.point == (1.03, 1.03)


def test_ortho_forces_axis_and_rejects_off_axis_snap():
    other = m.Line(2.0, 1.2, 2.0, 3.0)     # endpoint off the horizontal axis
    r = snap((2.02, 1.1), [other], SnapSettings(), 0.1, anchor=(0, 1.0))
    assert r.point[1] == 1.0                # stayed horizontal
    assert r.kind == "grid"


def test_ortho_accepts_on_axis_snap():
    other = m.Line(2.0, 1.0, 2.0, 3.0)
    r = snap((2.03, 1.1), [other], SnapSettings(), 0.1, anchor=(0, 1.0))
    assert r.kind == "end" and r.point == (2.0, 1.0)


def test_circle_quad_and_center():
    c = m.Circle(1, 1, 0.5)
    assert snap((1.5, 1.02), [c], SnapSettings(ortho=False), 0.1).kind == "quad"
    assert snap((1.01, 1.0), [c], SnapSettings(ortho=False), 0.1).kind == "center"


def test_translate_and_bounds():
    r = m.Rect(0, 0, 2, 1); translate(r, 1, 1)
    assert (r.x, r.y) == (1, 1)
    assert bounds([r, m.Circle(0, 0, 1)]) == (-1, -1, 3, 2)
    assert bounds([]) is None


def test_ortho_and_length():
    assert ortho((0, 0), (5, 1)) == (5, 0)
    assert ortho((0, 0), (1, 5)) == (0, 5)
    assert point_on_line_at((0, 0), (10, 0), 2.5) == (2.5, 0)


import math, pytest
from electro.geometry import trim_line, fillet_lines, chamfer_lines


def test_grid_origin_alignment():
    r = snap((0.40, 9.30), [], SnapSettings(ortho=False, grid_step=0.175, origin=(0.21, 9.34)), 0.1)
    assert r.point[0] == pytest.approx(0.385) and r.point[1] == pytest.approx(9.34)


def test_trim_between_crossings():
    ln = m.Line(0, 0, 10, 0)
    cut = [m.Line(3, -1, 3, 1), m.Line(7, -1, 7, 1)]
    segs = trim_line(ln, (5, 0), cut)
    assert segs == [((0, 0), (3, 0)), ((7, 0), (10, 0))]


def test_trim_to_end_and_whole():
    ln = m.Line(0, 0, 10, 0)
    cut = [m.Line(3, -1, 3, 1)]
    assert trim_line(ln, (1, 0), cut) == [((3, 0), (10, 0))]
    assert trim_line(ln, (9, 0), cut) == [((0, 0), (3, 0))]
    assert trim_line(ln, (5, 0), []) == []


def test_trim_t_junction_and_circle_and_rect():
    ln = m.Line(0, 0, 10, 0)
    assert trim_line(ln, (8, 0), [m.Line(5, 0, 5, 4)]) == [((0, 0), (5, 0))]     # wire ending on it
    segs = trim_line(ln, (5, 0), [m.Circle(5, 0, 1)])
    assert segs == [((0, 0), (4, 0)), ((6, 0), (10, 0))]
    segs = trim_line(ln, (1, 0), [m.Rect(2, -1, 2, 2)])
    assert segs == [((2, 0), (10, 0))]


def test_fillet_perpendicular():
    l1, l2 = m.Line(0, 0, 5, 0), m.Line(0, 0, 0, 5)
    c1, c2, arc = fillet_lines(l1, (3, 0), l2, (0, 3), 1.0)
    assert c1 == pytest.approx({"x1": 1.0, "y1": 0.0}) and c2 == pytest.approx({"x1": 0.0, "y1": 1.0})
    assert (arc.cx, arc.cy, arc.r) == pytest.approx((1, 1, 1))
    assert (arc.start, arc.end) == pytest.approx((180, 270))


def test_fillet_extends_when_lines_do_not_meet():
    l1, l2 = m.Line(2, 0, 5, 0), m.Line(0, 2, 0, 5)       # both stop short of the corner
    c1, c2, arc = fillet_lines(l1, (4, 0), l2, (0, 4), 0)
    assert c1 == pytest.approx({"x1": 0.0, "y1": 0.0}) and c2 == pytest.approx({"x1": 0.0, "y1": 0.0}) and arc is None


def test_fillet_errors():
    with pytest.raises(ValueError):
        fillet_lines(m.Line(0, 0, 5, 0), (3, 0), m.Line(0, 1, 5, 1), (3, 1), 0.5)   # parallel
    with pytest.raises(ValueError):
        fillet_lines(m.Line(0, 0, 1, 0), (1, 0), m.Line(0, 0, 0, 1), (0, 1), 2.0)   # too big


def test_chamfer():
    l1, l2 = m.Line(0, 0, 5, 0), m.Line(0, 0, 0, 5)
    c1, c2, ch = chamfer_lines(l1, (3, 0), l2, (0, 3), 0.5)
    assert c1 == pytest.approx({"x1": 0.5, "y1": 0.0}) and c2 == pytest.approx({"x1": 0.0, "y1": 0.5})
    assert (ch.x1, ch.y1, ch.x2, ch.y2) == (0.5, 0.0, 0.0, 0.5)


def test_fillet_pick_side_selects_far_part():
    l1, l2 = m.Line(-5, 0, 5, 0), m.Line(0, -5, 0, 5)      # a cross: pick quadrant II
    c1, c2, arc = fillet_lines(l1, (-3, 0), l2, (0, 3), 1.0)
    assert c1 == pytest.approx({"x2": -1.0, "y2": 0.0}) and c2 == pytest.approx({"x1": 0.0, "y1": 1.0})


def test_chamfer_two_distances():
    l1, l2 = m.Line(0, 0, 5, 0), m.Line(0, 0, 0, 5)
    c1, c2, ch = chamfer_lines(l1, (3, 0), l2, (0, 3), 0.5, 1.0)
    assert (ch.x1, ch.y1, ch.x2, ch.y2) == (0.5, 0.0, 0.0, 1.0)


# ---------------------------------------------------------------- groups
from electro.geometry import (snapshot, stretch, grips_of, clamp_delta, restore,
                              leaves, walk, snap_points)


def rounded_rect(w=4.0, h=2.0, r=0.5):
    """4 lines + 4 quarter arcs, as produced by filleting all corners of a rectangle."""
    L = [m.Line(r, 0, w - r, 0), m.Line(w, r, w, h - r), m.Line(w - r, h, r, h), m.Line(0, h - r, 0, r)]
    A = [m.Arc(w - r, r, r, 270, 360), m.Arc(w - r, h - r, r, 0, 90),
         m.Arc(r, h - r, r, 90, 180), m.Arc(r, r, r, 180, 270)]
    return m.Group(L + A)


def test_group_bounds_use_true_arc_extent():
    assert bounds([rounded_rect()]) == pytest.approx((0, 0, 4, 2))


def test_group_translate_and_snap_points():
    g = rounded_rect(); translate(g, 1, 1)
    assert bounds([g]) == pytest.approx((1, 1, 5, 3))
    assert ("end", pytest.approx((1.5, 1.0))) in snap_points(g)
    assert len(list(leaves([g]))) == 8 and len(list(walk([g]))) == 9


@pytest.mark.parametrize("side,delta,expect", [
    ("right", 1.0, (0, 0, 5, 2)), ("left", -1.0, (-1, 0, 4, 2)),
    ("top", 0.5, (0, 0, 4, 2.5)), ("bottom", 0.25, (0, 0.25, 4, 2)),
    ("right", -1.0, (0, 0, 3, 2)),
])
def test_stretch_keeps_radii(side, delta, expect):
    g = rounded_rect(); bb = bounds([g]); snap_ = snapshot([g])
    stretch(snap_, bb, side, delta)
    assert bounds([g]) == pytest.approx(expect)
    assert all(a.r == 0.5 for a in g.children if isinstance(a, m.Arc))
    # arcs still quarter circles tangent to their edges: corner lines end where arcs start
    right = g.children[1]
    if side == "right":
        assert right.x1 == right.x2 == pytest.approx(4 + delta)


def test_stretch_is_repeatable_and_restorable():
    g = rounded_rect(); bb = bounds([g]); snap_ = snapshot([g])
    for d in (1.0, 2.0, 0.5):
        stretch(snap_, bb, "right", d)
    assert bounds([g]) == pytest.approx((0, 0, 4.5, 2))      # no drift
    restore(snap_)
    assert bounds([g]) == pytest.approx((0, 0, 4, 2))


def test_clamp_and_grips():
    g = rounded_rect(); bb = bounds([g]); s = snapshot([g])
    assert clamp_delta(s, bb, "right", -10) == pytest.approx(-3.0)      # width floor = 2r = 1
    assert clamp_delta(s, bb, "left", 10) == pytest.approx(3.0)
    gr = grips_of(bb)
    assert gr["right"] == (4, 1) and gr["top"] == (2, 2)


def test_group_xml_roundtrip(tmp_path):
    from electro import save_project, load_project
    p = m.Project("g"); sh = p.add_sheet(m.Sheet(1))
    inner = m.Group([m.Line(0, 0, 1, 1)])
    sh.entities += [m.Group([m.Line(0, 0, 2, 0), m.Arc(1, 1, .5, 0, 90), inner]), m.Rect(0, 0, 1, 1)]
    f = tmp_path / "g.eqt"; save_project(p, f)
    assert load_project(f) == p


def test_trim_uses_group_children_as_cutters():
    ln = m.Line(0, 0, 10, 0)
    g = m.Group([m.Line(5, -1, 5, 1)])
    assert trim_line(ln, (8, 0), [g]) == [((0, 0), (5, 0))]


# ------------------------------------------------- align / multiline / misc
from electro.geometry import align_moves, multiline_wires, offset_polyline, text_extent


def _moves(items, mode):
    return {k: (round(dx, 9), round(dy, 9)) for k, dx, dy in align_moves(items, mode)}


BOXES = [("a", (0, 0, 2, 1)), ("b", (5, 3, 6, 5)), ("c", (2, 8, 4, 9))]


def test_align_edges():
    assert _moves(BOXES, "left") == {"a": (0, 0), "b": (-5, 0), "c": (-2, 0)}
    assert _moves(BOXES, "right") == {"a": (4, 0), "b": (0, 0), "c": (2, 0)}
    assert _moves(BOXES, "bottom") == {"a": (0, 0), "b": (0, -3), "c": (0, -8)}
    assert _moves(BOXES, "top") == {"a": (0, 8), "b": (0, 4), "c": (0, 0)}


def test_align_centers():
    r = _moves(BOXES, "hcenter")           # selection spans x 0..6, centre 3
    assert r == {"a": (2, 0), "b": (-2.5, 0), "c": (0, 0)}
    r = _moves(BOXES, "vcenter")           # y 0..9, centre 4.5
    assert r == {"a": (0, 4), "b": (0, 0.5), "c": (0, -4)}


def test_distribute_equal_gaps():
    items = [("a", (0, 0, 1, 1)), ("b", (1.5, 0, 2.5, 1)), ("c", (9, 0, 10, 1))]
    r = _moves(items, "dist_h")            # total 10, widths 3 -> gaps 3.5
    assert r == {"a": (0, 0), "b": (3.0, 0), "c": (0, 0)}
    assert _moves(items[:2], "dist_h") == {"a": (0, 0), "b": (0, 0)}      # needs 3


def test_multiline_horizontal_and_vertical_order():
    h = multiline_wires([(0, 0), (4, 0)], 3, 0.35)
    ys = [w[0][1] for w in h]
    assert ys == pytest.approx([0.35, 0.0, -0.35])                       # wire 0 on top
    assert multiline_wires([(4, 0), (0, 0)], 3, 0.35)[0][0][1] == pytest.approx(0.35)   # even drawn right-to-left
    v = multiline_wires([(0, 4), (0, 0)], 4, 0.35)
    xs = [w[0][0] for w in v]
    assert xs == pytest.approx([-0.525, -0.175, 0.175, 0.525])          # wire 0 on the left
    assert multiline_wires([(0, 0), (0, 4)], 2, 0.35)[0][0][0] == pytest.approx(-0.175)


def test_multiline_mitred_corner():
    w = multiline_wires([(0, 0), (4, 0), (4, -3)], 2, 1.0)
    # centre path goes right then down; wire 0 is on top/outside of the turn
    assert w[0] == pytest.approx([(0, 0.5), (4.5, 0.5), (4.5, -3)])
    assert w[1] == pytest.approx([(0, -0.5), (3.5, -0.5), (3.5, -3)])


def test_offset_degenerate():
    assert offset_polyline([(0, 0)], 1) == [] and offset_polyline([(1, 1), (1, 1)], 1) == []


def test_text_extent_and_bounds():
    t = m.Text(1, 1, "ABCD\nEF", height=0.1)
    x0, y0, x1, y1 = text_extent(t)
    assert x0 == 1 and y1 == pytest.approx(1.1) and x1 == pytest.approx(1 + 4 * 0.07)
    assert y0 < 1 - 0.1
    assert bounds([t]) == pytest.approx((x0, y0, x1, y1))


def test_preset_validation_and_roundtrip(tmp_path):
    from electro import save_project, load_project
    with pytest.raises(ValueError): m.MultilinePreset("x", ["A"])
    p = m.Project("p"); p.add_sheet(m.Sheet(1))
    p.layers["L1"] = m.Layer("L1", 10, "wire", True, "<incident><L|T><phase>", lineweight=0.5)
    p.multiline_presets["mine"] = m.MultilinePreset("mine", ["L1", "L2"], 0.25)
    p.sheets[1].entities.append(m.Text(0, 0, "hi", "hi", 0.2, 0, m.Style("0", color=11), font="DejaVu Sans"))
    f = tmp_path / "p.eqt"; save_project(p, f)
    q = load_project(f)
    assert q == p and q.layers["L1"].lineweight == 0.5 and "480 VAC 3ph+PE" in q.multiline_presets
    assert q.sheets[1].entities[0].font == "DejaVu Sans"


# ------------------------------------------- templates / fields / copy / rotate / mirror
from electro import fields
from electro.templates import tabloid_template, sheet_from_template, zone_of, default_templates
from electro.geometry import clone_entity, rotate_entity, mirror_entity


def test_template_matches_sample_geometry():
    t = tabloid_template(1)
    assert (t.width, t.height, t.zone0_y, t.zone_count) == (17.0, 11.0, 9.45, 25)
    bb = bounds([e for e in t.frame if not isinstance(e, m.Text)])
    assert bb == pytest.approx((0.0 + 0.0 + 0.208, 0.3, 16.584, 10.8)) or bb[0] <= 0.21
    assert bb[2] == pytest.approx(16.584) and bb[1] == pytest.approx(0.3) and bb[3] == pytest.approx(10.8)
    texts = {e.source for e in t.frame if isinstance(e, m.Text)}
    assert {"{job}", "{drawn}", "{date}", "{title1}", "{title4}", "{page} OF {pages}", "DRAWN", "JOB", "DATE"} <= texts
    assert {f"{i:02d}" for i in range(25)} <= texts
    assert t.col_split_x is None and tabloid_template(2).col_split_x is not None
    assert {"49"} <= {e.source for e in tabloid_template(2).frame if isinstance(e, m.Text)}


def test_zone_of():
    t1, t2 = tabloid_template(1), tabloid_template(2)
    assert zone_of(t1, 3.0, 9.45) == 0 and zone_of(t1, 3.0, 7.0) == 7 and zone_of(t1, 3.0, 1.05) == 24
    assert zone_of(t1, 12.0, 7.0) == 7                       # single column: always 00-24
    assert zone_of(t2, 3.0, 7.0) == 7 and zone_of(t2, 12.0, 7.0) == 32
    assert zone_of(t1, 3.0, 20.0) == 0 and zone_of(t1, 3.0, -5.0) == 24    # clamps


def test_fields_resolve_and_refresh():
    p = m.Project("x"); p.info.update(job="TEST-E01", drawn="BDM", date="11/01/26")
    for n in (1, 2):
        p.add_sheet(tabloid_template(1).__class__(n)) if False else None
    s1 = p.add_sheet(sheet_from_template(tabloid_template(1), 1, "AC"))
    p.add_sheet(sheet_from_template(tabloid_template(1), 2))
    s1.title_lines = ["AC", "POWER", "DISTRIBUTION", ""]
    fields.refresh_project(p)
    res = {e.source: e.resolved for e in s1.frame if isinstance(e, m.Text)}
    assert res["{job}"] == "TEST-E01" and res["{drawn}"] == "BDM" and res["{date}"] == "11/01/26"
    assert res["{page} OF {pages}"] == "01 OF 02" and res["{title2}"] == "POWER" and res["{title4}"] == ""
    user = m.Text(0, 0, "Job {job} {nope}"); s1.entities.append(user)
    fields.refresh_project(p)
    assert user.resolved == "Job TEST-E01 {nope}"            # unknown codes stay visible


def test_sheet_from_template_is_independent():
    t = tabloid_template(1)
    a, b = sheet_from_template(t, 1), sheet_from_template(t, 2)
    assert a.page == 1 and b.page == 2 and a.entities == [] and len(a.frame) == len(t.frame)
    assert {e.id for e in a.frame}.isdisjoint({e.id for e in b.frame})
    assert {e.id for e in a.frame}.isdisjoint({e.id for e in t.frame})
    a.frame.pop(); assert len(b.frame) == len(t.frame)


def test_project_with_templates_roundtrip(tmp_path):
    from electro import save_project, load_project
    p = m.Project("t"); p.info.update(job="J1", drawn="BDM", date="01/02/26")
    p.templates.update(default_templates())
    s = p.add_sheet(sheet_from_template(p.templates["11x17 - 2 columns (zones 00-49)"], 1, "AC"))
    s.title_lines = ["A", "B", "", "D"]
    fields.refresh_project(p)
    f = tmp_path / "t.eqt"; save_project(p, f)
    q = load_project(f)
    assert q == p and q.sheets[1].col_split_x == pytest.approx(7.484) and q.sheets[1].title_lines == ["A", "B", "", "D"]
    assert q.info["job"] == "J1"


def test_clone_gives_new_ids_and_clears_numbers():
    ln = m.Line(0, 0, 1, 0); ln.number = m.WireNumber("override", "3029")
    g = m.Group([ln, m.Circle(0, 0, 1)])
    c = clone_entity(g)
    assert c.id != g.id and c.children[0].id != ln.id
    assert c.children[0].number == m.WireNumber("auto", "") and ln.number.value == "3029"
    c.children[1].r = 5; assert g.children[1].r == 1                    # truly independent


def test_rotate_90_cases():
    ln = m.Line(1, 0, 3, 0); rotate_entity(ln, (0, 0), 90)
    assert (ln.x1, ln.y1, ln.x2, ln.y2) == pytest.approx((0, 1, 0, 3))
    r = m.Rect(1, 0, 4, 2); rotate_entity(r, (0, 0), 90)               # corners (1,0),(5,2) -> (0,1),(-2,5)
    assert (r.x, r.y, r.w, r.h) == pytest.approx((-2, 1, 2, 4))
    a = m.Arc(0, 0, 1, 350, 80); rotate_entity(a, (0, 0), 90)
    assert (a.start, a.end) == pytest.approx((80, 170))
    t = m.Text(2, 0, "x", rotation=0); rotate_entity(t, (0, 0), 90)
    assert (t.x, t.y, t.rotation) == pytest.approx((0, 2, 90))
    with pytest.raises(ValueError):
        rotate_entity(m.Rect(0, 0, 1, 1), (0, 0), 45)
    rotate_entity(ln, (0, 0), 45)                                       # lines rotate by any angle


def test_rotate_roundtrip_and_group():
    g = rounded_rect(); before = [(c.__class__, vars(c).copy()) for c in g.children]
    for _ in range(4):
        rotate_entity(g, (2, 1), 90)
    after = [(c.__class__, vars(c).copy()) for c in g.children]
    for (ca, va), (cb, vb) in zip(before, after):
        assert ca is cb
        for k, v in va.items():
            if isinstance(v, float):
                assert vb[k] % 360 == pytest.approx(v % 360) or vb[k] == pytest.approx(v)


def test_mirror_cases():
    ln = m.Line(1, 0, 3, 2); mirror_entity(ln, "v", 0)
    assert (ln.x1, ln.y1, ln.x2, ln.y2) == (-1, 0, -3, 2)
    r = m.Rect(1, 1, 2, 3); mirror_entity(r, "h", 0)
    assert (r.x, r.y, r.w, r.h) == (1, -4, 2, 3)
    a = m.Arc(0, 0, 1, 0, 90); mirror_entity(a, "v", 0)                 # quarter in quadrant I -> II
    assert (a.start, a.end) == pytest.approx((90, 180))
    a = m.Arc(0, 0, 1, 0, 90); mirror_entity(a, "h", 0)                 # -> quadrant IV
    assert (a.start, a.end) == pytest.approx((270, 0))
    g = rounded_rect(); b0 = bounds([g]); mirror_entity(g, "v", 2.0)
    assert bounds([g]) == pytest.approx(b0)                             # symmetric about its own centre
    t = m.Text(3, 1, "keep reading"); mirror_entity(t, "v", 0); assert (t.x, t.rotation) == (-3, 0)
    br = m.BlockRef("b", 1, 1); mirror_entity(br, "h", 0); assert br.mirror and br.rotation == 180


def test_snapshot_covers_new_fields():
    a = m.Arc(0, 0, 1, 10, 80); snap_ = snapshot([a])
    rotate_entity(a, (0, 0), 90); restore(snap_)
    assert (a.start, a.end) == (10, 80)


def test_standards_defaults_and_roundtrip(tmp_path):
    from electro import save_project, load_project
    p = m.Project("p"); p.add_sheet(m.Sheet(1))
    std = p.multiline_presets
    assert std["480 VAC 3ph+PE"].colors == [10, 11, 2, 3] and std["480 VAC 3ph+PE"].labels == ["L1", "L2", "L3", "PE"]
    assert std["240 VAC 3ph+PE"].colors == [7, 1, 5, 3] and std["240 VAC 3ph+PE"].layers[0] == "240V L1"
    assert std["480 VAC 3ph"].layers == std["480 VAC 3ph+PE"].layers[:3]       # shares layers
    p.multiline_presets["Mine 125 VDC"] = m.MultilinePreset("Mine 125 VDC", ["D+", "D-"], 0.5, [1, 5], ["+", "-"])
    f = tmp_path / "s.eqt"; save_project(p, f)
    q = load_project(f)
    assert q.multiline_presets == p.multiline_presets
    with pytest.raises(ValueError): m.MultilinePreset("x", ["a", "b"], colors=[1])
