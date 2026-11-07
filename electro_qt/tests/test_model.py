import os, pytest
from electro import model as m, save_project, load_project
from electro.dxfimport import import_dxf

UP = "/mnt/user-data/uploads"


def sample_project():
    p = m.Project("demo")
    p.layers["L1"] = m.Layer("L1", 24, "wire", True, "<incident><L|T><phase>")
    p.layers["PE"] = m.Layer("PE", 3, "wire", False)
    blk = m.BlockDef("cb3ph", description="3P breaker", part_number="X-1", tag_prefix="CB",
                     hyperlink="http://x", increment=1, poles=3,
                     data={"voltage": "480"})
    blk.entities.append(m.Line(0, 0, 0, 1))
    blk.slots += [m.Slot("L1", 0, 1, 0.1, 0.1), m.Slot("T1", 0, 0)]
    p.blocks["cb3ph"] = blk
    s = p.add_sheet(m.Sheet(3, "Power", row_pitch=0.35))
    w1 = m.Line(0, 0, 0, 5, m.Style("L1", width=0.02))
    w1.number = m.WireNumber("override", "3029")
    w2 = m.Line(1, 0, 1, 5, m.Style("L1"))
    s.entities += [w1, w2, m.Rect(0, 0, 2, 1), m.Circle(1, 1, .05, filled=True),
                   m.Arc(1, 1, .5, 10, 90),
                   m.Text(2, 2, "{tag}\n#PN", "CB0314", 0.12),
                   m.BlockRef("cb3ph", 0, 2, 90, True, "CB0314", {"terminal_L1": "A"})]
    s.bundles.append(m.Bundle([w1.id, w2.id], "3ph", 0.35))
    s.gotos.append(m.Goto(5, 5, [("03140", 4), ("03141", 11)]))
    return p


def test_roundtrip(tmp_path):
    p = sample_project()
    f = tmp_path / "a.eqt"
    save_project(p, f)
    q = load_project(f)
    assert q == p


def test_zip_layout(tmp_path):
    import zipfile
    f = tmp_path / "a.eqt"
    save_project(sample_project(), f)
    names = zipfile.ZipFile(f).namelist()
    assert "project.xml" in names and "sheets/03.xml" in names and "library/cb3ph.xml" in names


def test_ids_stable(tmp_path):
    p = sample_project()
    ids = [e.id for e in p.sheets[3].entities]
    f = tmp_path / "a.eqt"; save_project(p, f)
    assert [e.id for e in load_project(f).sheets[3].entities] == ids


def test_validation():
    with pytest.raises(ValueError): m.Sheet(0)
    with pytest.raises(ValueError): m.Sheet(100)
    with pytest.raises(ValueError): m.WireNumber("bogus")
    with pytest.raises(ValueError): m.Sheet(1, zone_count=30)
    p = m.Project(); p.add_sheet(m.Sheet(1))
    with pytest.raises(ValueError): p.add_sheet(m.Sheet(1))


def test_future_schema_rejected(tmp_path):
    p = sample_project(); p.schema_version = 99
    f = tmp_path / "a.eqt"; save_project(p, f)
    with pytest.raises(ValueError): load_project(f)


def test_assets_roundtrip(tmp_path):
    p = sample_project(); p.assets["doc.pdf"] = b"%PDF-1.4 x"
    f = tmp_path / "a.eqt"; save_project(p, f)
    assert load_project(f).assets["doc.pdf"] == b"%PDF-1.4 x"


@pytest.mark.skipif(not os.path.exists(f"{UP}/AC_Example.dxf"), reason="sample missing")
@pytest.mark.parametrize("name,wires,blocks", [
    ("AC_Example", {"L1": 7, "L2": 7, "L3": 6}, {"cb3ph", "no3phcon", "3phmtr", "dis3phpr", "TB"}),
    ("Safety_Example", {"WIRE_DC": 14}, {"LIGHT1", "PBNO", "lg592548pc6124", "TB"}),
])
def test_import_samples_roundtrip(tmp_path, name, wires, blocks):
    p, stats = import_dxf(f"{UP}/{name}.dxf", name)
    sh = p.sheets[1]
    counts = {}
    for e in sh.entities:
        if isinstance(e, m.Line) and e.number is not None:
            counts[e.style.layer] = counts.get(e.style.layer, 0) + 1
    assert counts == wires
    assert blocks <= set(p.blocks)
    assert all(p.layers[l].kind == "wire" for l in wires)
    f = tmp_path / "x.eqt"; save_project(p, f)
    assert load_project(f) == p


def test_array_and_increment():
    from electro import geometry as g
    assert g.increment_number("TB09", 1) == "TB10"
    assert g.increment_number("TB1", 2) == "TB3"
    assert g.increment_number("A1B2", 1) == "A1B3"
    assert g.increment_number("NODIGITS", 1) == "NODIGITS"
    assert g.increment_number("{page}1", 1) == "{page}1"
    t = m.Text(0, 0, "R1", "R1")
    out = g.array_linear([t], 2, 3, 1.0, 0.5, True, 1)
    assert len(out) == 5 and len({e.id for e in out}) == 5
    assert [e.source for e in out] == ["R2", "R3", "R4", "R5", "R6"]
    assert (out[-1].x, out[-1].y) == (2.0, 0.5)
    pt = m.Text(1, 0, "X", "X")
    po = g.array_polar([pt], 4, 360, (0, 0), rotate_items=False)
    assert len(po) == 3


def test_line_grips_and_segment_shift():
    from electro import geometry as g
    # vertical - horizontal - vertical
    a = m.Line(0, 0, 0, 2, m.Style("0"))
    b = m.Line(0, 2, 3, 2, m.Style("0"))
    c = m.Line(3, 2, 3, 0, m.Style("0"))
    lines = [a, b, c]
    nodes = g.line_nodes(lines)
    assert {id(x) for x in g.line_chain([b], nodes)} == {id(a), id(b), id(c)}
    kinds = [(k, key) for ln in lines for k, key, _ in g.line_grips(ln, nodes)]
    assert kinds.count(("mid", 0)) == 3
    assert kinds.count(("end", 1)) + kinds.count(("end", 2)) == 2      # only the two open ends
    st = g.segment_state(b, nodes)
    g.shift_segment(st, 0.5)
    ny = st["n"][1]
    assert abs(abs(st["n"][1]) - 1) < 1e-9
    assert (b.y1, b.y2) == (2 + 0.5 * ny, 2 + 0.5 * ny)
    assert (a.y2, c.y1) == (b.y1, b.y1) and (a.y1, c.y2) == (0, 0)
    g.shift_segment(st, 0)
    assert (b.y1, a.y2) == (2, 2)


def test_text_styles_roundtrip(tmp_path):
    p = m.Project("x")
    p.text_styles["Big"] = m.TextStyle("Big", "Arial", 0.25, 1, "center")
    from electro import save_project, load_project
    p.add_sheet(m.Sheet(1, "S"))
    p.sheets[1].entities.append(m.Text(0, 0, "a", "a", tstyle="Big", align="right"))
    save_project(p, tmp_path / "t.eqt")
    q = load_project(tmp_path / "t.eqt")
    assert q.text_styles["Big"].height == 0.25 and q.text_styles["Big"].color == 1
    assert q.sheets[1].entities[0].tstyle == "Big" and q.sheets[1].entities[0].align == "right"


def test_logo_roundtrip(tmp_path):
    from electro import save_project, load_project
    from electro.templates import tabloid_template
    p = m.Project("x")
    p.add_sheet(tabloid_template(1))
    p.info["logo"] = "logo.png"; p.assets["logo.png"] = b"\x89PNGfake"
    save_project(p, tmp_path / "l.eqt")
    q = load_project(tmp_path / "l.eqt")
    assert q.sheets[1].logo_box == (15.134, 6.55, 1.4, 4.2)
    assert q.info["logo"] == "logo.png" and q.assets["logo.png"] == b"\x89PNGfake"


def test_blocks_make_place_trim_tag():
    from electro import blocks as bk
    from electro.templates import tabloid_template
    p = m.Project("b")
    p.layers["W"] = m.Layer("W", 1, "wire")
    sh = p.add_sheet(tabloid_template(1))
    # a 1-pole contact: two slots 0.7 apart (vertical), a body, a label
    ents = [m.SlotMark(5.0, 5.0, "1"), m.SlotMark(5.0, 5.7, "2"),
            m.Rect(4.9, 5.2, 0.2, 0.3, m.Style("0"))]
    b = bk.make_block("K", ents, (5.0, 5.35), ("description", "tag"), "right", tag_prefix="K", description="Contact")
    assert len(b.slots) == 2 and b.slots[0].y == -0.35 and b.poles == 1
    assert not any(isinstance(e, m.Rect) for e in b.entities) and len(b.entities) == 4 + 1 + 1
    p.blocks["K"] = b
    ref = m.BlockRef("K", 3.0, 5.0)
    pts = [w for _, w in bk.block_slots(b, ref)]
    assert all(abs(a - b_) < 1e-9 for q, w in zip(pts, [(3.0, 4.65), (3.0, 5.35)]) for a, b_ in zip(q, w))
    ref.rotation = 90
    pts = [w for _, w in bk.block_slots(b, ref)]
    assert abs(pts[0][0] - 3.35) < 1e-9 and abs(pts[0][1] - 5.0) < 1e-9
    ref.rotation = 0
    wire = m.Line(3.0, 3.0, 3.0, 7.0, m.Style("W"))
    ops = bk.paste_on_wire([wire], [w for _, w in bk.block_slots(b, ref)])
    assert len(ops) == 1 and [tuple(round(v, 9) for v in pc) for pc in ops[0][1]] == [(3.0, 3.0, 3.0, 4.65), (3.0, 5.35, 3.0, 7.0)]
    # tag: prefix + page + zone (+ letter on collision)
    t1 = bk.assign_tag(p, b, sh, 3.0, 5.0)
    assert t1.startswith("K01") and len(t1) == 5
    ref.tag = t1; sh.entities.append(ref)
    assert bk.assign_tag(p, b, sh, 3.0, 5.0) == t1 + "A"
    ents = bk.resolved_entities(p, sh, b, ref)
    assert any(isinstance(e, m.Text) and e.resolved == t1 for e in ents)
    assert any(isinstance(e, m.Text) and e.resolved == "Contact" for e in ents)


def test_blocks_roundtrip_and_import(tmp_path):
    from electro import save_project, load_project, blocks as bk
    from electro.dxfimport import import_dxf
    p = m.Project("b")
    p.add_sheet(m.Sheet(1, "S"))
    p.blocks["K"] = bk.make_block("K", [m.SlotMark(0, 0, "A"), m.Line(0, 0, 1, 0, m.Style("0"))], (0, 0))
    p.sheets[1].entities += [m.BlockRef("K", 1, 1, 90, True, tag="K0101", props={"part_number": "X"}),
                             m.SlotMark(2, 2, "T1")]
    save_project(p, tmp_path / "b.eqt")
    q = load_project(tmp_path / "b.eqt")
    r = q.sheets[1].entities[0]
    assert (r.block, r.rotation, r.mirror, r.tag, r.props) == ("K", 90.0, True, "K0101", {"part_number": "X"})
    assert q.sheets[1].entities[1].terminal == "T1" and q.blocks["K"].slots[0].terminal == "A"
    import os
    d = "/mnt/user-data/attachments/6d7baa54-2b08-5015-8eae-d8f5fdbb7621/98c619e3-AC_Example.dxf"
    if os.path.exists(d):
        proj, _ = import_dxf(d)
        sh = next(iter(proj.sheets.values()))
        for r in (e for e in sh.entities if isinstance(e, m.BlockRef)):
            bk.resolved_entities(proj, sh, proj.blocks[r.block], r)


def test_update_tags():
    from electro import blocks as bk
    from electro.templates import tabloid_template
    p = m.Project("t"); sh = p.add_sheet(tabloid_template(1))
    p.blocks["K"] = m.BlockDef("K", tag_prefix="K")
    a, b_, c = m.BlockRef("K", 3, 5), m.BlockRef("K", 6, 5), m.BlockRef("K", 6, 5, props={"tag_mode": "manual"}, tag="K0102")
    sh.entities += [b_, a, c]
    assert bk.update_tags(p) == 2
    assert a.tag.startswith("K01") and b_.tag == a.tag + "A" and c.tag == "K0102"


def test_label_above_pair_numbers_and_duplicates():
    from electro import blocks as bk
    from electro.templates import tabloid_template
    b = bk.make_block("C", [m.SlotMark(0, 0, "1"), m.SlotMark(0, 0.7, "2"), m.Line(0, 0.2, 0, 0.5, m.Style("0"))],
                      (0, 0.35), ("description", "part_label", "tag"))
    texts = [e for e in b.entities if isinstance(e, m.Text)]
    assert [t.source for t in texts] == ["{tag}", "{part_label}", "{description}"]
    assert all(t.align == "center" and t.y > 0.35 for t in texts)       # above the top slot (y = 0.35)
    assert texts[0].y < texts[1].y < texts[2].y
    assert bk.label_lines_of(b) == ("description", "part_label", "tag")
    bk.rebuild_label(b, ("tag",), "right")
    assert bk.label_lines_of(b) == ("tag",) and b.label_pos == "right"
    assert bk.pair_numbers(4, 13, 10) == ["13", "14", "23", "24"]
    assert bk.pair_numbers(6, 1, 2) == ["1", "2", "3", "4", "5", "6"]
    p = m.Project("d"); sh = p.add_sheet(tabloid_template(1)); p.blocks["C"] = b
    r1, r2 = m.BlockRef("C", 3, 5, tag="K0101"), m.BlockRef("C", 6, 5, tag="K0101", props={"hide": "tag", "term0": "13"})
    sh.entities += [r1, r2]
    assert list(bk.duplicate_tags(p)) == ["K0101"]
    ents = bk.resolved_entities(p, sh, b, r2)
    assert [t.resolved for t in ents if isinstance(t, m.Text) and t.source == "{tag}"] == [""]
    assert bk.slot_name(r2, 0, b.slots[0]) == "13" and bk.slot_name(r2, 1, b.slots[1]) == "2"


def test_tag_letters_only_for_same_zone_and_links_follow():
    from electro import blocks as bk
    from electro.templates import tabloid_template
    p = m.Project("t"); sh = p.add_sheet(tabloid_template(1))
    p.blocks["K"] = m.BlockDef("K", tag_prefix="K")
    p.blocks["C"] = m.BlockDef("C")                       # contact: no prefix
    coil = m.BlockRef("K", 3, 8)
    contact = m.BlockRef("C", 3, 2)
    sh.entities += [contact, coil]
    bk.update_tags(p)
    t0 = coil.tag
    assert t0.startswith("K01") and len(t0) == 5
    # the contact picks the coil's tag: link it
    contact.tag, contact.props = t0, {"tag_mode": "linked", "tag_link": coil.id}
    bk.update_tags(p)
    assert coil.tag == t0 and contact.tag == t0            # no letter just because a contact holds the tag
    other = m.BlockRef("K", 6, 8)                          # same zone: this one gets the letter
    sh.entities.append(other)
    bk.update_tags(p)
    assert {coil.tag, other.tag} == {t0, t0 + "A"} and contact.tag == coil.tag
    coil.y = 4.0                                           # the coil moves to another zone
    bk.update_tags(p)
    assert coil.tag != t0 and contact.tag == coil.tag
    sh.entities.remove(coil)
    assert [r for _, r in bk.broken_links(p)] == [contact]


def test_library_folders(tmp_path):
    from electro import blocks as bk, save_project, load_project
    p = m.Project("f"); p.add_sheet(m.Sheet(1, "S"))
    p.blocks["A"] = m.BlockDef("A", folder="Contactors/Aux", entities=[m.Line(0, 0, 1, 0, m.Style("0"))])
    p.block_folders = ["Fuses"]
    assert bk.folder_paths(p) == ["Contactors", "Contactors/Aux", "Fuses"]
    c = bk.copy_block(p, "A", "A2", "Fuses")
    assert c.folder == "Fuses" and c.entities[0].id != p.blocks["A"].entities[0].id
    assert bk.unique_block_name(p, "A") == "A (2)"
    bk.rename_folder(p, "Contactors", "Starters")
    assert p.blocks["A"].folder == "Starters/Aux"
    assert bk.delete_folder(p, "Starters/Aux") == 1 and p.blocks["A"].folder == "Starters"
    save_project(p, tmp_path / "f.eqt")
    q = load_project(tmp_path / "f.eqt")
    assert q.blocks["A2"].folder == "Fuses" and "Fuses" in q.block_folders


def test_library_store(tmp_path):
    from electro.libstore import LibraryStore, default_root
    from electro import blocks as bk
    assert default_root().name == "blocks"
    st = LibraryStore(tmp_path / "blocks")
    assert st.blocks == {} and (tmp_path / "blocks").is_dir()
    b = bk.make_block("Contact 3P", [m.SlotMark(0, 0, "1"), m.SlotMark(0, 0.7, "2"),
                                     m.Line(0, 0.2, 0, 0.5, m.Style("0"))], (0, 0.35),
                      ("description", "tag"), folder="Contactors/Aux", description="Aux contact")
    st.save_block(b)
    f = tmp_path / "blocks" / "Contactors" / "Aux" / "Contact 3P.eqblock"
    assert f.exists() and st.folders == ["Contactors", "Contactors/Aux"]
    st2 = LibraryStore(tmp_path / "blocks")                   # fresh load from disk
    c = st2.blocks["Contact 3P"]
    assert c.folder == "Contactors/Aux" and len(c.slots) == 2 and c.description == "Aux contact"
    st2.copy_block("Contact 3P", "Contact copy", "Spares")
    assert (tmp_path / "blocks" / "Spares" / "Contact copy.eqblock").exists()
    c.folder = "Moved"; st2.save_block(c)                     # moving a block moves its file
    assert not f.exists() and (tmp_path / "blocks" / "Moved" / "Contact 3P.eqblock").exists()
    st2.rename_folder("Moved", "Renamed")
    assert st2.blocks["Contact 3P"].folder == "Renamed"
    assert st2.delete_folder("Renamed") == 1 and st2.blocks["Contact 3P"].folder == ""
    (tmp_path / "blocks" / "bad.eqblock").write_text("<nope")
    st3 = LibraryStore(tmp_path / "blocks")
    assert len(st3.errors) == 1 and "Contact 3P" in st3.blocks and (tmp_path / "blocks" / "bad.eqblock").exists()
    st3.delete_block("Contact 3P")
    assert "Contact 3P" not in LibraryStore(tmp_path / "blocks").blocks


def _ac_project():
    from electro.templates import tabloid_template
    p = m.Project("n")
    p.layers["L1"] = m.Layer("L1", 10, "wire", True, "<incident><L|T><phase>", phase="L1")
    p.layers["PE"] = m.Layer("PE", 3, "wire", False, "", phase="PE")
    p.layers["DC"] = m.Layer("DC", 5, "wire", True, "<page><zone><incident>")
    sh = p.add_sheet(tabloid_template(1))
    two = lambda n, inc, rule="": m.BlockDef(n, increment=inc, prefix_rule=rule,
                                             slots=[m.Slot("1", 0, 0), m.Slot("2", 1, 0)])
    p.blocks["CB"], p.blocks["CON"] = two("CB", 1), two("CON", 1)
    p.blocks["MOT"] = m.BlockDef("MOT", prefix_rule="motor", slots=[m.Slot("T1", 0, 0)])
    y = 6.0
    sh.entities += [m.Line(1, y, 2, y, m.Style("L1"), number=m.WireNumber("auto", "")),
                    m.Line(3, y, 4, y, m.Style("L1"), number=m.WireNumber("auto", "")),
                    m.Line(5, y, 7, y, m.Style("L1"), number=m.WireNumber("auto", "")),
                    m.BlockRef("CB", 2, y), m.BlockRef("CON", 4, y), m.BlockRef("MOT", 7, y)]
    return p, sh


def test_numbering_ac_chain_matches_example():
    from electro import numbering as nb
    p, sh = _ac_project()
    sh.entities[0].mark = "1"                                  # Mark wire, start incident 1
    rep = nb.update(p)
    nb.apply(p, rep)
    assert [l.number.value for l in sh.entities[:3]] == ["1L1", "2L1", "3T1"]     # 1L1 2L1 3T1
    assert rep.numbered == 3 and rep.warnings == []
    assert nb.update(p).changes == {}                          # nothing left to change


def test_numbering_override_dc_dots_and_warnings():
    from electro import numbering as nb
    p, sh = _ac_project()
    sh.entities[0].mark = "1"
    sh.entities[1].number = m.WireNumber("override", "9999")   # typed number survives, the walk goes on
    nb.apply(p, nb.update(p))
    assert [l.number.value for l in sh.entities[:3]] == ["1L1", "9999", "3T1"]
    # DC: <page><zone><incident>; a crossing joins only with a solid dot
    a = m.Line(1, 3.0, 5, 3.0, m.Style("DC"), number=m.WireNumber("auto", ""), mark="0")
    b = m.Line(3, 2.0, 3, 4.0, m.Style("DC"), number=m.WireNumber("auto", ""))
    sh.entities += [a, b]
    rep = nb.update(p); nb.apply(p, rep)
    assert a.number.value != b.number.value if b.number.value else True
    assert any("not reached" in w for w in rep.warnings)       # b is a separate net
    sh.entities.append(m.Circle(3, 3.0, 0.04, m.Style("DC"), filled=True))
    rep = nb.update(p); nb.apply(p, rep)
    assert a.number.value == b.number.value and a.number.value.startswith("01") and a.number.value.endswith("0")
    p.lead_zero_suppress = True
    nb.apply(p, nb.update(p))
    assert not a.number.value.startswith("0")
    # PE layer never numbered
    sh.entities.append(m.Line(1, 1, 2, 1, m.Style("PE")))
    assert all(n.layer != "PE" for n in nb.build_nets(p, sh))
    labels = nb.net_labels(p, sh)
    assert any(t == "1L1" for _, _, _, t, _ in labels)


def test_mark_roundtrip(tmp_path):
    from electro import save_project, load_project
    p = m.Project("x"); p.add_sheet(m.Sheet(1, "S"))
    p.sheets[1].entities.append(m.Line(0, 0, 1, 0, m.Style("0"), mark="0"))
    save_project(p, tmp_path / "m.eqt")
    assert load_project(tmp_path / "m.eqt").sheets[1].entities[0].mark == "0"


def test_prefix_rules(tmp_path):
    from electro import numbering as nb, save_project, load_project
    p, sh = _ac_project()
    sh.entities[0].mark = "1"
    p.prefix_rules = [m.PrefixRule("motor", "<L|T>", "T", "L"), m.PrefixRule("xfmr", "<L|T>", "X", "L")]
    p.layers["L1"].scheme = "<incident><L|T><phase>"
    p.blocks["CON"].prefix_rule = "XFMR"                       # case does not matter
    nb.apply(p, nb.update(p))
    assert [l.number.value for l in sh.entities[:3]] == ["1L1", "2X1", "3T1"]
    p.prefix_rules = [m.PrefixRule("motor", "<L|T>", "M", "-")]
    for l in sh.entities[:3]:
        l.number = m.WireNumber("auto", "")
    nb.apply(p, nb.update(p))
    assert [l.number.value for l in sh.entities[:3]] == ["1-1", "2-1", "3M1"]
    save_project(p, tmp_path / "r.eqt")
    q = load_project(tmp_path / "r.eqt")
    assert q.prefix_rules == p.prefix_rules
    assert m.Project("old").prefix_rules[0].name == "motor"


def test_explode_block():
    from electro import blocks as bk
    p = m.Project("e"); sh = p.add_sheet(m.Sheet(1, "S"))
    b = bk.make_block("K", [m.SlotMark(0, 0, "1"), m.SlotMark(0, 0.7, "2"), m.Line(0, 0.2, 0, 0.5, m.Style("0"))],
                      (0, 0), ("description", "tag"), description="Contact")
    p.blocks["K"] = b
    r = m.BlockRef("K", 4, 4, 90, tag="K0101", props={"term0": "13", "hide": "tag"})
    out = bk.explode_block(p, sh, b, r)
    marks = [e for e in out if isinstance(e, m.SlotMark)]
    assert [mk.terminal for mk in marks] == ["13", "2"]
    assert abs(marks[1].x - 3.3) < 1e-9 and abs(marks[1].y - 4.0) < 1e-9        # rotated 90 about (4, 4)
    texts = [e for e in out if isinstance(e, m.Text)]
    assert [t.source for t in texts] == ["Contact"]                              # hidden tag line dropped
    assert not any(isinstance(e, m.BlockRef) for e in out)


# ---------------------------------------------------------------- junctions / hops / trim
def _jproj():
    from electro import model as m
    p = m.Project()
    for n in ("L1", "L2"):
        p.layers[n] = m.Layer(n, 1, "wire", True, "L1")
    return p


def test_hops_and_connect():
    from electro import model as m, junctions as jn
    p = _jproj(); sh = m.Sheet(1)
    sh.entities = [m.Line(0, 1, 4, 1, m.Style(layer="L1")), m.Line(2, 0, 2, 3, m.Style(layer="L2"))]
    h = jn.hops(p, sh)
    assert len(h) == 1 and h[0].vert.x1 == 2
    sh.entities.append(m.Circle(2, 1, 0.04, m.Style(layer="L2"), filled=True))
    assert jn.hops(p, sh) == []
    assert jn.crossing_near(p, sh, (2.01, 1.0), 0.1).connected


def test_junction_dots():
    from electro import model as m, junctions as jn
    a = m.Line(0, 0, 4, 0, m.Style(layer="L1"))
    b = m.Line(2, 0, 2, 3, m.Style(layer="L1"))
    assert jn.junction_dots([a, b]) == [(2, 0)]
    c = m.Line(2, 0, 2, 3, m.Style(layer="L2"))
    assert jn.junction_dots([a, c]) == []


def test_trim_wire_start():
    from electro import model as m, junctions as jn
    bus2 = m.Line(1, -1, 1, 5, m.Style(layer="L2"))
    bus1 = m.Line(0, -1, 0, 5, m.Style(layer="L1"))
    ex = [bus1, bus2]
    assert jn.trim_wire_start([(0, 2), (3, 2)], "L1", ex) == [(0, 2), (3, 2)]    # starts on its bus
    assert jn.trim_wire_start([(0, 3), (3, 3)], "L2", ex) == [(1, 3), (3, 3)]    # trimmed back to L2 bus
    assert jn.trim_wire_start([(0, 3), (3, 3)], "L3", ex) == [(0, 3), (3, 3)]    # no bus on that layer


def test_global_incident_and_schemes_roundtrip(tmp_path):
    from electro import numbering as nb, xmlio
    p, sh = _ac_project()
    p.layers["L1"].scheme = "<g_incident>"                     # no mark needed
    nb.apply(p, nb.update(p))
    assert [l.number.value for l in sh.entities[:3]] == ["1", "2", "3"]
    p.schemes["Mine"] = "<g_incident><phase>"
    f = tmp_path / "a.eqt"; xmlio.save_project(p, str(f))
    assert xmlio.load_project(str(f)).schemes == {"Mine": "<g_incident><phase>"}


def test_phase_incident_example_layout():
    """Bus -> two branches (CB -> contactor -> motor): 1L*, then 2L* 3T* (top), 4L* 5T* (bottom)."""
    from electro import numbering as nb
    p = m.Project("n")
    from electro.templates import tabloid_template
    sh = p.add_sheet(tabloid_template(1))
    for i, n in enumerate(("L1", "L2", "L3")):
        p.layers[n] = m.Layer(n, 10 + i, "wire", True, "<phase_incident><L|T><phase>", phase=n)
    slots = []
    for k in range(3):
        slots += [m.Slot(str(2 * k + 1), 0, -0.35 * k), m.Slot(str(2 * k + 2), 1, -0.35 * k)]
    p.blocks["CB"] = m.BlockDef("CB", increment=1, slots=list(slots))
    p.blocks["CON"] = m.BlockDef("CON", increment=1, slots=list(slots))
    p.blocks["MOT"] = m.BlockDef("MOT", prefix_rule="motor", slots=[m.Slot(f"T{k}", 0, -0.35 * k) for k in range(3)])
    for top, y0 in (("t", 8.0), ("b", 5.0)):
        for k, lay in enumerate(("L1", "L2", "L3")):
            y = y0 - 0.35 * k
            sh.entities += [m.Line(1.0 + 0.1 * k if False else 1.0, y, 3, y, m.Style(lay), number=m.WireNumber("auto", "")),
                            m.Line(4, y, 6, y, m.Style(lay), number=m.WireNumber("auto", "")),
                            m.Line(7, y, 9, y, m.Style(lay), number=m.WireNumber("auto", ""))]
        sh.entities += [m.BlockRef("CB", 3, y0), m.BlockRef("CON", 6, y0), m.BlockRef("MOT", 9, y0)]
    # shared bus on the left: join the two branches' first segments with a vertical wire per phase
    for k, lay in enumerate(("L1", "L2", "L3")):
        sh.entities.append(m.Line(1.0, 8.0 - 0.35 * k, 1.0, 5.0 - 0.35 * k, m.Style(lay), number=m.WireNumber("auto", "")))
    rep = nb.update(p)
    nb.apply(p, rep)
    vals = lambda y: [l.number.value for l in sh.entities if isinstance(l, m.Line) and abs(l.y1 - y) < 1e-6 and abs(l.y2 - y) < 1e-6]
    assert vals(8.0) == ["1L1", "2L1", "3T1"] and vals(7.65) == ["1L2", "2L2", "3T2"] and vals(7.3) == ["1L3", "2L3", "3T3"]
    assert vals(5.0) == ["1L1", "4L1", "5T1"] and vals(4.3) == ["1L3", "4L3", "5T3"]


def test_trim_circle_and_manual_numbers():
    from electro import geometry as g, numbering as nb
    c = m.Circle(0, 0, 1.0, m.Style("0"))
    cut = [m.Line(-2, 0.5, 2, 0.5, m.Style("0"))]              # crosses at 30 and 150 degrees
    arc = g.trim_circle(c, (0, 1.0), cut)                      # click the top: top part removed
    assert arc is not None and abs(arc.start - 150) < 1e-6 and abs(arc.end - 30) < 1e-6 and arc.r == 1.0
    assert g.trim_circle(c, (0, 1.0), []) is None
    p = m.Project("x")
    p.layers["PE"] = m.Layer("PE", 3, "wire", False, "", phase="PE")
    sh = p.add_sheet(m.Sheet(1))
    ln = m.Line(0, 0, 2, 0, m.Style("PE")); sh.entities.append(ln)
    assert nb.build_nets(p, sh) == []                          # PE is not numbered...
    assert len(nb.build_nets(p, sh, include={ln.id})) == 1     # ...unless a number is being set
    ln.number = m.WireNumber("ignore", "PE1")
    assert nb.net_labels(p, sh)[0][3] == "PE1"                 # a typed number on PE shows


def test_arc_tool_geometry_and_arc_trim():
    from electro import geometry as g
    a, side = g.arc_from_ends((0, 0), (2, 0), (1, 0))            # centre on the chord: half circle
    assert a is not None and abs(a.r - 1) < 1e-9 and abs(a.cx - 1) < 1e-9 and abs(a.cy) < 1e-9
    a, _ = g.arc_from_ends((0, 0), (2, 0), (1, -1))              # centre below: arc bulges up, minor
    assert abs(a.r - 2 ** 0.5) < 1e-9 and abs(a.cy + 1) < 1e-9
    mid = ((a.start + ((a.end - a.start) % 360) / 2))
    import math
    assert a.cy + a.r * math.sin(math.radians(mid)) > 0          # the bulge is above the chord
    assert (a.end - a.start) % 360 < 180
    # trimming an arc twice: circle -> arc -> two arcs
    c = m.Circle(0, 0, 1.0, m.Style("0"))
    arc = g.trim_circle(c, (0, 1), [m.Line(-2, 0.5, 2, 0.5, m.Style("0"))])
    pieces = g.trim_arc(arc, (0, -1), [m.Line(0.6, -2, 0.6, 2, m.Style("0")), m.Line(-0.6, -2, -0.6, 2, m.Style("0"))])
    assert len(pieces) == 2 and all(isinstance(x, m.Arc) for x in pieces)
    assert g.trim_arc(arc, (1, 0), []) == []                     # no cutters: the whole arc goes


def test_wires_follow_moved_block_and_zone_from_mark():
    from electro import blocks as bk, numbering as nb
    p = m.Project("f")
    sh = p.add_sheet(m.Sheet(1))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<page><zone><incident>")
    p.blocks["PB"] = m.BlockDef("PB", increment=1, slots=[m.Slot("1", 0, 0), m.Slot("2", 1, 0)])
    left = m.Line(0, 5, 3, 5, m.Style("W")); right = m.Line(4, 5, 4.5, 5, m.Style("W"))
    ref = m.BlockRef("PB", 3, 5)
    sh.entities += [left, right, ref]
    mods, adds, rems = bk.follow_plan(p, sh, [ref], 0.25, 0.0)          # along the wire
    d = {id(l): f for l, f in mods}
    assert d[id(left)]["x2"] == 3.25 and d[id(right)]["x1"] == 4.25 and not adds
    mods, adds, rems = bk.follow_plan(p, sh, [ref], 0.0, -1.0)          # sideways: orthogonal connectors
    assert len(adds) == 2 and all(abs(a.x1 - a.x2) < 1e-9 or abs(a.y1 - a.y2) < 1e-9 for a in adds)
    # zone/page come from the marked wire, not from the left end of the wire after the contact
    sh.entities.append(m.Line(4.5, 5, 4.5, 1, m.Style("W")))
    sh.entities.append(m.Line(4.5, 1, 0.2, 1, m.Style("W")))             # runs back left into another zone
    left.mark = "0"
    rep = nb.update(p)
    zones = {n.value[2:4] for n in [] }
    vals = sorted({w.value for ch in rep.changes.values() for _, w in ch})
    assert len(vals) == 2 and vals[0][:4] == vals[1][:4] and vals[0][4:] == "0" and vals[1][4:] == "1"


def test_reports_wire_list_labels_bom(tmp_path):
    from electro import reports, numbering as nb
    p = m.Project("r")
    sh = p.add_sheet(m.Sheet(1))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<page><zone><incident>")
    p.blocks["PB"] = m.BlockDef("PB", description="Pushbutton", part_number="XB4", manufacturer="Acme", increment=1,
                                data={"Voltage": "24V"}, slots=[m.Slot("1", 0, 0), m.Slot("2", 1, 0)])
    left = m.Line(0, 5, 3, 5, m.Style("W")); right = m.Line(4, 5, 6, 5, m.Style("W"))
    left.mark = "0"
    ref1, ref2 = m.BlockRef("PB", 3, 5, tag="PB1"), m.BlockRef("PB", 3, 2, tag="PB2", props={"part_number": "XB5"})
    sh.entities += [left, right, ref1, ref2]
    nb.apply(p, nb.update(p))
    rows = reports.wire_list(p)
    assert len(rows) == 2
    assert rows[0][4] == "PB1:1" and rows[1][4] == "PB1:2" and rows[0][0] != rows[1][0]
    labels = reports.wire_labels(p)
    assert labels == [[rows[0][0]], [rows[0][0]], [rows[1][0]], [rows[1][0]]]      # two labels per wire
    header, bom = reports.bom(p)
    assert header[-1] == "Voltage" and [r[1] for r in bom] == [1, 1] and {r[2] for r in bom} == {"XB4", "XB5"}
    f = tmp_path / "b.csv"; reports.write_csv(str(f), header, bom)
    assert f.read_text(encoding="utf-8-sig").splitlines()[0].startswith("Item,Qty")


def test_real_block_bounds():
    from electro import geometry as g
    blk = m.BlockDef("B", entities=[m.Rect(-0.2, -0.5, 1.4, 0.7, m.Style("0"))], slots=[m.Slot("1", 0, 0), m.Slot("2", 1, 0)])
    blocks = {"B": blk}
    ref = m.BlockRef("B", 10, 5)
    assert g.bounds([ref]) == (10, 5, 10, 5)                     # no block table: just the origin
    b = g.bounds([ref], blocks)
    assert all(abs(x - y) < 1e-9 for x, y in zip(b, (9.8, 4.5, 11.2, 5.2)))
    ref.rotation = 90
    b = g.bounds([ref], blocks)
    assert all(abs(x - y) < 1e-9 for x, y in zip(b, (9.8, 4.8, 10.5, 6.2)))
    ref.rotation = 0; ref.mirror = True
    b = g.bounds([ref], blocks)
    assert all(abs(x - y) < 1e-9 for x, y in zip(b, (8.8, 4.5, 10.2, 5.2)))


def test_edit_block_roundtrip():
    from electro import blocks as bk
    ents = [m.Line(0, 0, 1, 0, m.Style("0")), m.SlotMark(0, 0, "1"), m.SlotMark(1, 0, "2")]
    old = bk.make_block("PB", ents, (0, 0), ("description", "tag"), "above", description="Push", part_number="X1",
                        increment=1, data={"V": "24"})
    old.slots[1].num_dx = 0.2
    sh = bk.edit_sheet(old)
    assert not any(isinstance(e, m.Text) for e in sh.entities)            # label text is rebuilt, not edited
    marks = [e for e in sh.entities if isinstance(e, m.SlotMark)]
    assert [(round(k.x, 6), round(k.y, 6), k.terminal) for k in marks] == [(6.0, 6.0, "1"), (7.0, 6.0, "2")]
    same = bk.block_from_sheet(old, sh)
    assert [(s.x, s.y, s.terminal) for s in same.slots] == [(0, 0, "1"), (1, 0, "2")] and same.slots[1].num_dx == 0.2
    assert bk.label_lines_of(same) == ("description", "tag") and same.part_number == "X1" and same.data == {"V": "24"}
    marks[1].x = 7.5                                                       # move a slot, add a third, change geometry
    sh.entities.append(m.SlotMark(8.0, 6.0, "3"))
    sh.entities[0].x2 += 0.5
    new = bk.block_from_sheet(old, sh)
    assert [round(s.x, 6) for s in new.slots] == [0, 1.5, 2.0] and new.poles == 1
    assert any(isinstance(e, m.Line) and abs(e.x2 - 1.5) < 1e-9 for e in new.entities)


def test_xref_and_off_page_connector():
    from electro import blocks as bk, numbering as nb
    p = m.Project("x")
    s1, s2 = p.add_sheet(m.Sheet(1)), p.add_sheet(m.Sheet(2))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "N<incident>")
    p.blocks["PB"] = m.BlockDef("PB", increment=1, slots=[m.Slot("1", 0, 0), m.Slot("2", 1, 0)])
    goto = bk.default_connector_block()
    assert bk.label_lines_of(goto) == ("tag", "xref") and goto.connector == 1 and len(goto.slots) == 1
    p.blocks["GOTO"] = goto
    w1 = m.Line(0, 5, 3, 5, m.Style("W")); w1.mark = "1"
    s1.entities += [w1, m.BlockRef("PB", 3, 5, tag="S1"), m.Line(4, 5, 6, 5, m.Style("W")),
                    m.BlockRef("GOTO", 6, 5, tag="A", props={"tag_mode": "manual"})]
    c2 = m.BlockRef("GOTO", 0, 5, tag="A", props={"tag_mode": "manual"})
    s2.entities += [c2, m.Line(0, 5, 2, 5, m.Style("W")), m.BlockRef("PB", 2, 5, tag="S2"), m.Line(3, 5, 5, 5, m.Style("W"))]
    rep = nb.update(p)
    assert not rep.warnings, rep.warnings
    nb.apply(p, rep)
    vals = lambda sh: [l.number.value for l in sh.entities if isinstance(l, m.Line)]
    assert vals(s1) == ["N1", "N2"] and vals(s2) == ["N2", "N3"]          # the count carries over the connector
    assert bk.xref_text(p, c2) == "01/" + bk.zone_text(s1, 6, 5)
    # a typed number on one end wins on the other
    s2.entities[1].number = m.WireNumber("override", "99")
    nb.apply(p, nb.update(p))
    assert vals(s1)[1] == "99"
    # coil <-> contact cross-reference
    coil = m.BlockRef("PB", 1, 8, tag="K1"); contact = m.BlockRef("PB", 1, 2, props={"tag_mode": "linked", "tag_link": coil.id})
    s1.entities += [coil]; s2.entities += [contact]
    assert bk.xref_text(p, coil) == "02/" + bk.zone_text(s2, 1, 2) and bk.xref_text(p, contact) == "01/" + bk.zone_text(s1, 1, 8)


def test_block_brings_its_layers(tmp_path):
    from electro import blocks as bk, xmlio
    src = m.Project("a")
    src.layers["HIDDEN"] = m.Layer("HIDDEN", 3, "graphics", linetype="dashed", lineweight=0.35)
    blk = bk.make_block("B", [m.Line(0, 0, 1, 0, m.Style("HIDDEN")), m.Line(0, 1, 1, 1, m.Style("NOPE"))], (0, 0))
    bk.capture_layers(src, blk)
    assert list(blk.layers) == ["HIDDEN"]                          # NOPE has no definition anywhere
    blk2 = xmlio.block_from_xml(xmlio.block_to_xml(blk))
    assert blk2.layers["HIDDEN"].linetype == "dashed" and blk2.layers["HIDDEN"].lineweight == 0.35
    dst = m.Project("b")
    added = bk.ensure_layers(dst, blk2)
    assert added == ["HIDDEN", "NOPE"]
    assert dst.layers["HIDDEN"].linetype == "dashed" and dst.layers["HIDDEN"].color == 3
    assert dst.layers["NOPE"].color == 7 and dst.layers["NOPE"].linetype == "continuous"   # plain default
    assert bk.ensure_layers(dst, blk2) == []
