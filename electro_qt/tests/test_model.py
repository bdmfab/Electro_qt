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
    with pytest.raises(ValueError): m.Sheet(100)
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
    assert [(round(k.x, 6), round(k.y, 6), k.terminal) for k in marks] == [(5.95, 5.95, "1"), (6.95, 5.95, "2")]
    same = bk.block_from_sheet(old, sh)
    assert [(s.x, s.y, s.terminal) for s in same.slots] == [(0, 0, "1"), (1, 0, "2")] and same.slots[1].num_dx == 0.2
    assert bk.label_lines_of(same) == ("description", "tag") and same.part_number == "X1" and same.data == {"V": "24"}
    marks[1].x = bk.EDIT_ORIGIN[0] + 1.5                                                       # move a slot, add a third, change geometry
    sh.entities.append(m.SlotMark(bk.EDIT_ORIGIN[0] + 2.0, bk.EDIT_ORIGIN[1], "3"))
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
    goto = bk.default_connector_block("from")
    assert bk.label_lines_of(goto) == ("xref",) and goto.label_pos == "right" and goto.connector == 1
    assert len(goto.slots) == 1 and (goto.slots[0].x, goto.slots[0].y) == (0, 0)
    to = bk.default_connector_block("to")
    assert bk.label_lines_of(to) == () and len(to.slots) == 1 and to.name != goto.name
    t = [e for e in goto.entities if isinstance(e, m.Text)][0]
    assert t.x > 0.5 and abs(t.y) < 0.1 and t.align == "left"                  # beside the arrow, to its right
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


def test_single_slot_connector_trims_wire():
    from electro import blocks as bk
    p = m.Project("t")
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<incident>")
    p.blocks["F"] = bk.default_connector_block("from")       # body to the right of the slot
    p.blocks["T"] = bk.default_connector_block("to")         # slot at the tip, body to the left
    wire = m.Line(0, 5, 10, 5, m.Style("W"))
    ops = bk.trim_ops(p, [wire], [m.BlockRef("F", 6, 5)])
    assert len(ops) == 1 and ops[0][1] == [(0, 5, 6, 5)]      # keeps the wire's side, drops the part under the symbol
    ops = bk.trim_ops(p, [wire], [m.BlockRef("T", 6, 5)])
    assert ops[0][1] == [(6, 5, 10, 5)]                       # "To" is already turned 180: body on the left
    ops = bk.trim_ops(p, [wire], [m.BlockRef("F", 6, 5, rotation=180)])
    assert ops[0][1] == [(6, 5, 10, 5)]                       # rotated: body points left
    assert bk.trim_ops(p, [wire], [m.BlockRef("F", 10, 5)]) == []   # wire already ends on the slot
    assert bk.trim_ops(p, [wire], [m.BlockRef("F", 6, 5, rotation=90)]) == []   # body square to the wire


def test_goto_connectors():
    from electro import numbering as nb
    from electro import blocks as bk
    p = m.Project("g")
    sheets = [p.add_sheet(m.Sheet(i)) for i in (1, 2, 3, 4, 5)]
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    for blk in (bk.default_connector_block("from"), bk.default_connector_block("to")):
        p.blocks[blk.name] = blk
    for sh in sheets:
        ln = m.Line(1, 5, 3, 5, m.Style("W")); ln.number = m.WireNumber("override", "02041")
        sh.entities.append(ln)
    rep = nb.update(p)
    assert [v for v, _ in rep.duplicates] == ["02041"] and len(rep.duplicates[0][1]) == 5
    plan = nb.goto_duplicates(p, rep.duplicates)
    assert [n for n, _, _ in plan] == ["02041-1", "02041-2"]                     # pairs; the odd wire is left
    name, a, b = plan[0]
    put, bad = nb.goto_connectors(p, a, b, name)
    assert not bad
    (pg1, k1, pt1, r1, n1), (pg2, k2, pt2, r2, n2) = put
    assert (pg1, k1, pt1, r1) == (1, "From", (3, 5), 0.0)                        # both ends free: From on the right end
    assert (pg2, k2, pt2, r2) == (2, "To", (1, 5), 0.0)                          # To on the left end
    assert n1 == n2 == "02041-1"
    # place the connectors: the wires are now one group, no longer duplicates, numbers unchanged
    for pg, kind, pt, rot, nm in put:
        r = m.BlockRef(kind, pt[0], pt[1], rot); r.tag = nm
        p.sheets[pg].entities.append(r)
    assert nb.next_connector_name(p, "02041") == "02041-2"
    for pg, kind, pt, rot, nm in nb.goto_connectors(p, plan[1][1], plan[1][2], plan[1][0])[0]:
        r = m.BlockRef(kind, pt[0], pt[1], rot); r.tag = nm
        p.sheets[pg].entities.append(r)
    r2 = nb.update(p)
    assert r2.duplicates == []                                                  # two sets + one plain wire
    assert all(l.number.value == "02041" for sh in sheets for l in sh.entities if isinstance(l, m.Line))
    # a wire with both ends on parts has no free end
    q = m.Project("h"); sh = q.add_sheet(m.Sheet(1)); q.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    q.blocks["From"] = bk.default_connector_block("from")
    sh.entities += [m.Line(1, 5, 3, 5, m.Style("W")), m.BlockRef("From", 1, 5), m.BlockRef("From", 3, 5)]
    net = nb.build_nets(q, sh)[0]
    assert nb.free_ends(q, 1, net) == []


def test_richtext_parse_roundtrip():
    from electro import richtext as rt
    mk = "Hello <b>bold <i>both</i></b> <size=1.5><color=1>big red</color></size>\n2 &lt; 3 &amp; <u>x</u>"
    lines = rt.parse(mk)
    assert len(lines) == 2
    assert [r.text for r in lines[0]] == ["Hello ", "bold ", "both", " ", "big red"]
    assert lines[0][1].bold and not lines[0][1].italic and lines[0][2].italic and lines[0][2].bold
    assert lines[0][4].size == 1.5 and lines[0][4].color == 1
    assert rt.plain(mk) == "Hello bold both big red\n2 < 3 & x"
    assert rt.parse(rt.dumps(lines)) == lines


def test_richtext_fields_and_save(tmp_path):
    from electro import fields, richtext as rt
    t = m.Text(0, 0, "A <b>B</b>", "A <b>B</b>", 0.12, 0.0, m.Style(), rich=True)
    from electro.geometry import text_extent
    x0, y0, x1, y1 = text_extent(t)
    assert x1 - x0 > 0
    p = m.Project(); sh = m.Sheet(1); p.add_sheet(sh); sh.entities.append(t)
    f = str(tmp_path / "r.eqt")
    from electro import xmlio
    xmlio.save_project(p, f)
    q = xmlio.load_project(f)
    t2 = q.sheet(1).entities[0] if hasattr(q, "sheet") else list(q.sheets.values())[0].entities[0]
    assert t2.rich is True and t2.source == "A <b>B</b>"


def test_goto_one_from_many_to():
    from electro import numbering as nb, blocks as bk
    p = m.Project("g")
    sh = [p.add_sheet(m.Sheet(i)) for i in (1, 2, 3)]
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    src = m.Line(1, 5, 3, 5, m.Style("W")); src.number = m.WireNumber("override", "55")
    t1 = m.Line(1, 5, 3, 5, m.Style("W")); t2 = m.Line(1, 5, 3, 5, m.Style("W"))
    for s_, l in zip(sh, (src, t1, t2)):
        s_.entities.append(l)
    name, frm, to, val = nb.goto_plan(p, {t1.id}, src.id)          # selected wire = To, picked = From
    assert (name, val) == ("55-1", "55") and frm[0] == 1 and to[0] == 2
    put, bad = nb.goto_connectors(p, frm, to, name)
    assert [k for _, k, *_ in put] == ["From", "To"]
    for pg, kind, pt, rot, nm in put:
        r = m.BlockRef(kind, pt[0], pt[1], rot); r.tag = nm; p.sheets[pg].entities.append(r)
    name2, frm2, to2, _ = nb.goto_plan(p, {t2.id}, src.id)         # the same From goes to a second To
    assert name2 == "55-1" and frm2 is None and to2[0] == 3
    put2, _ = nb.goto_connectors(p, frm2, to2, name2)
    assert [k for _, k, *_ in put2] == ["To"]


def test_dxf_export_with_stub():
    from unittest.mock import MagicMock
    from electro import dxfexport as dx, blocks as bk
    assert dx.safe_name('a/b:c') == "a_b_c" and dx.lineweight(0.5) == 50 and dx.lineweight(0) == -3
    assert dx.mtext_markup("a{b}\nc", False) == "a\\{b\\}\\Pc"
    mk = dx.mtext_markup("x <b>y</b> <size=2>z</size> <u>u</u>", True)
    assert "\\fArial|b1|i0;" in mk and "\\H2x;" in mk and "\\Lu\\l" in mk
    p = m.Project("d"); sh = p.add_sheet(m.Sheet(1))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    blk = bk.make_block("K1 coil", [m.Line(0, 0, 1, 0, m.Style("0")), m.Line(0, 0, 0, -1, m.Style("0")),
                                    m.SlotMark(0, 0, "A1")], (0, 0), ("tag", "description"), "right",
                        description="Relay")
    p.blocks[blk.name] = blk
    r = m.BlockRef("K1 coil", 4, 5, 90, True); r.tag = "K1"
    sh.entities += [m.Line(0, 5, 4, 5, m.Style("W")), r, m.Circle(1, 1, 0.04, m.Style("0"), filled=True),
                    m.Text(1, 1, "hi", "hi", 0.1, 0.0, m.Style("0"), rich=False),
                    m.Text(2, 2, "<b>big</b>", "<b>big</b>", 0.1, 0.0, m.Style("0"), rich=True, align="center")]
    attrs = dx.ref_attributes(p, sh, blk, r)
    tags = [a[0] for a in attrs]
    assert {"TAG", "DESCRIPTION", "PART_NUMBER", "MANUFACTURER", "XREF", "TERM1"} <= set(tags)
    assert dict((a[0], a[1]) for a in attrs)["TAG"] == "K1" and dict((a[0], a[1]) for a in attrs)["DESCRIPTION"] == "Relay"
    assert [a[5] for a in attrs if a[0] == "TAG"] == [True]                         # a label: visible
    ez = MagicMock()
    ex = dx.Exporter(p, ez)
    ex.add_sheet(sh)
    msp = ez.new.return_value.modelspace.return_value
    assert msp.add_line.called and msp.add_blockref.called and msp.add_mtext.called and msp.add_hatch.called
    args = msp.add_blockref.call_args
    assert args[0][0] == "K1 coil" and args[1]["dxfattribs"]["xscale"] == -1.0 and args[1]["dxfattribs"]["rotation"] == 90
    assert ez.new.return_value.blocks.new.call_args[1]["name"] == "K1 coil"


def test_export_names_and_dxf_files(tmp_path):
    from unittest.mock import MagicMock
    from electro import exportnames as en, dxfexport as dx
    p = m.Project("x"); p.info["job"] = "J/123: Press"
    s1 = p.add_sheet(m.Sheet(1, title="Power  Main")); s2 = p.add_sheet(m.Sheet(2))
    assert en.sheet_stem(s1) == "01 Power Main" and en.sheet_stem(s2) == "02"
    assert en.job_stem(p) == "J_123_ Press"
    p.info["job"] = ""
    assert en.job_stem(p, "/a/b/Plant.eqt") == "Plant" and en.job_stem(p) == "job"
    assert en.export_folder("/a/b/Plant.eqt", "pdf").replace("\\", "/") == "/a/b/pdf"
    paths = dx.export_project(p, str(tmp_path / "dxf"), ez=MagicMock())
    assert [x.replace("\\", "/").split("/")[-1] for x in paths] == ["01 Power Main.dxf", "02.dxf"]
    assert (tmp_path / "dxf").is_dir()


def test_dxf_layer_names_case_insensitive():
    from unittest.mock import MagicMock
    from electro import dxfexport as dx
    p = m.Project("c"); p.layers["Dashed"] = m.Layer("Dashed", 3); p.layers["DASHED"] = m.Layer("DASHED", 3)
    ez = MagicMock()
    ex = dx.Exporter(p, ez)
    assert ex.add_layer("dashed") == "Dashed"
    assert [c[0][0] for c in ez.new.return_value.layers.add.call_args_list] == ["Dashed"]


def test_title_block_double_weight():
    from electro import templates as t
    sh = t.tabloid_template()
    fr = t.display_frame(sh)
    heavy = [e for e in fr if isinstance(e, (m.Line, m.Arc)) and e.style.width == t.TITLE_BLOCK_MM]
    light = [e for e in fr if isinstance(e, (m.Line, m.Arc)) and e.style.width == 0]
    assert heavy and light                                  # title block heavy, border / zone ruler unchanged
    border = [e for e in heavy if isinstance(e, m.Line) and max(e.x1, e.x2) < 15.0]
    assert len(border) == 8                                 # four sides + four chamfers
    hexes = [e for e in light if isinstance(e, m.Line) and e.x1 < 0.5]
    assert hexes and all(e.style.width == 0 for e in hexes)  # zone markers stay light
    assert all(e.style.width == 0 for e in sh.frame)        # stored frame untouched


def test_rule_check():
    from electro import rules, blocks as bk
    p = m.Project("r")
    s1 = p.add_sheet(m.Sheet(1)); s2 = p.add_sheet(m.Sheet(2))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<page><zone><incident>")
    pb = bk.make_block("PB", [m.Line(0, 0, 1, 0, m.Style("0")), m.SlotMark(0, 0, "1"), m.SlotMark(1, 0, "2")],
                       (0, 0), ("tag",), "above", tag_prefix="S")
    p.blocks["PB"] = pb
    c = bk.default_connector_block("from"); p.blocks[c.name] = c
    w = m.Line(0, 5, 1, 5, m.Style("W")); w.mark = "1"
    a = m.BlockRef("PB", 1, 5, tag="S1")                       # slot 1 on the wire, slot 2 loose
    b = m.BlockRef("PB", 6, 6, tag="S1")                       # same tag, nothing connected
    d = m.BlockRef("PB", 8, 8, tag="")                         # no tag
    k = m.BlockRef("PB", 9, 9, tag="K1", props={"tag_mode": "linked", "tag_link": "gone"})
    f = m.BlockRef("From", 3, 3, tag="X-1")                    # connector with no partner
    s1.entities += [w, a, b, d, k, f]
    s2.entities += [m.Line(0, 5, 2, 5, m.Style("W"))]          # a wire no marked wire reaches
    cats = [i.category for i in rules.check(p)]
    for c_ in ("Duplicate tag", "Missing tag", "Unconnected slot", "Wire not reached", "Broken tag link",
               "Connector without partner"):
        assert c_ in cats, (c_, cats)
    assert cats.count("Duplicate tag") == 2
    # a coil and its linked contact share a tag on purpose
    q = m.Project("q"); sh = q.add_sheet(m.Sheet(1)); q.blocks["PB"] = pb
    coil = m.BlockRef("PB", 1, 1, tag="K1"); cont = m.BlockRef("PB", 3, 3, tag="K1", props={"tag_mode": "linked", "tag_link": coil.id})
    sh.entities += [coil, cont]
    assert "Duplicate tag" not in [i.category for i in rules.check(q)]
    assert rules.as_rows(rules.check(q))[0][0] in rules.CATEGORIES


def test_bom_skips_connectors_and_flags_blank_part_numbers():
    from electro import reports, blocks as bk
    p = m.Project("b"); sh = p.add_sheet(m.Sheet(1))
    c = bk.default_connector_block("from"); p.blocks[c.name] = c
    a = bk.make_block("Relay", [m.Line(0, 0, 1, 0, m.Style("0"))], (0, 0), (), "above", part_number="")
    b = bk.make_block("Lamp", [m.Line(0, 0, 1, 0, m.Style("0"))], (0, 0), (), "above", part_number="L-1")
    p.blocks["Relay"], p.blocks["Lamp"] = a, b
    sh.entities += [m.BlockRef("From", 0, 0, tag="X-1"), m.BlockRef("Relay", 1, 1, tag="K1"),
                    m.BlockRef("Relay", 2, 2, tag="K2"), m.BlockRef("Lamp", 3, 3, tag="H1")]
    _, rows = reports.bom(p)
    assert [r[5] for r in rows].count("From") == 0 and sum(r[1] for r in rows) == 3
    assert reports.bom_missing_part_numbers(rows) == [("Relay", 2, "K1, K2")]


def test_auto_layers_named_dashed_and_gray():
    from electro import blocks as bk
    d = bk.default_layer("Dashed"); g = bk.default_layer("Light Grey"); n = bk.default_layer("Power")
    assert d.linetype == "dashed" and d.color == 7
    assert g.color == 8 and g.linetype == "continuous"
    assert n.linetype == "continuous" and n.color == 7


def test_cover_sheet(tmp_path):
    from electro import templates as t, fields, exportnames as en, xmlio
    cv = t.cover_sheet()
    assert cv.cover and cv.page == 0 and cv.title_lines == ["", "", "", ""]
    # border stretched over the old title block area; no title block, no zone markers
    xs = [v for e in cv.frame for v in (e.x1, e.x2)]
    assert max(xs) == 16.584 and min(xs) == 0.084 and len(cv.frame) == 8
    txt = cv.entities[0]
    assert txt.source == "COVER SHEET" and txt.align == "center" and abs(txt.x - 8.334) < 1e-9
    assert abs(txt.y + txt.height / 2 - 5.55) < 1e-9                            # centred on the sheet
    assert abs(txt.height - 0.48) < 1e-9
    # heavier border everywhere (no title block to tell it apart)
    assert all(e.style.width == t.TITLE_BLOCK_MM for e in t.display_frame(cv))
    p = m.Project("c")
    p.add_sheet(t.sheet_from_template(t.tabloid_template(1), 1, "Power"))
    p.add_sheet(cv)
    assert fields.context(p, p.sheets[1])["pages"] == "01"                      # the cover is not counted
    assert en.sheet_stem(cv) == "Cover Sheet" and en.sheet_stem(p.sheets[1]) == "01 Power"
    f = str(tmp_path / "c.eqt")
    xmlio.save_project(p, f)
    q = xmlio.load_project(f)
    assert q.sheets[0].cover and not q.sheets[1].cover and sorted(q.sheets) == [0, 1]


def test_renumber_sheets_and_sheet_type():
    from electro import templates as t
    p = m.Project("n")
    cv = t.cover_sheet(); p.add_sheet(cv)
    for pg in (1, 2, 3, 4):
        p.add_sheet(t.sheet_from_template(t.tabloid_template(1), pg, f"S{pg}"))
    s3 = p.sheets[3]; mark = m.Line(1, 1, 2, 2, m.Style("0")); s3.entities.append(mark)
    del p.sheets[2]                                              # delete sheet 2: 3 -> 2, 4 -> 3
    assert p.renumber_sheets() == {3: 2, 4: 3}
    assert sorted(p.sheets) == [0, 1, 2, 3] and p.sheets[2] is s3 and s3.page == 2 and mark in p.sheets[2].entities
    assert p.sheets[0].cover and p.sheets[0].page == 0
    assert p.renumber_sheets() == {}                             # already tidy
    # 1 column <-> 2 columns keeps what is drawn
    assert t.columns_of(s3) == 1 and s3.col_split_x is None
    assert t.set_columns(s3, 2) and s3.zone_count == 50 and s3.col_split_x is not None and t.columns_of(s3) == 2
    assert t.zone_of(s3, 12.0, 9.45) == 25                       # right half = zones 25-49
    assert mark in s3.entities
    assert t.set_columns(s3, 1) and s3.zone_count == 25 and s3.col_split_x is None
    assert t.zone_of(s3, 12.0, 9.45) == 0
    assert not t.set_columns(cv, 2)                              # the cover has no zones


def _dxf(entities, blocks="", header="  9\n$INSUNITS\n 70\n4\n", layers=(("0", 7, "CONTINUOUS"), ("HID", 3, "DASHED"))):
    lay = "".join(f"  0\nLAYER\n  2\n{n}\n 70\n0\n 62\n{c}\n  6\n{lt}\n" for n, c, lt in layers)
    return (f"  0\nSECTION\n  2\nHEADER\n{header}  0\nENDSEC\n  0\nSECTION\n  2\nTABLES\n  0\nTABLE\n  2\nLAYER\n{lay}"
            f"  0\nENDTAB\n  0\nENDSEC\n  0\nSECTION\n  2\nBLOCKS\n{blocks}  0\nENDSEC\n"
            f"  0\nSECTION\n  2\nENTITIES\n{entities}  0\nENDSEC\n  0\nEOF\n")


def test_dxf_geometry_import(tmp_path):
    import math
    from electro import dxfgeom as dg
    blocks = ("  0\nBLOCK\n  2\nSYM\n 10\n0\n 20\n0\n  0\nLINE\n  8\n0\n 10\n0\n 20\n0\n 11\n25.4\n 21\n0\n"
              "  0\nCIRCLE\n  8\n0\n 10\n0\n 20\n0\n 40\n12.7\n  0\nATTDEF\n  8\n0\n 10\n25.4\n 20\n0\n  1\nWIRE#\n 40\n2\n"
              "  0\nENDBLK\n")
    ents = ("  0\nLINE\n  8\nHID\n 10\n0\n 20\n0\n 11\n254\n 21\n0\n"
            "  0\nARC\n  8\n0\n 10\n0\n 20\n0\n 40\n25.4\n 50\n0\n 51\n90\n"
            "  0\nLWPOLYLINE\n  8\n0\n 70\n0\n 90\n2\n 10\n0\n 20\n0\n 42\n1\n 10\n25.4\n 20\n0\n"
            "  0\nINSERT\n  8\n0\n  2\nSYM\n 10\n254\n 20\n254\n 50\n90\n"
            "  0\nINSERT\n  8\n0\n  2\nSYM\n 10\n0\n 20\n0\n 41\n2\n 42\n2\n"
            "  0\nTEXT\n  8\n0\n 10\n0\n 20\n0\n 40\n2.54\n  1\nHELLO\n 72\n1\n 11\n50.8\n 21\n0\n 73\n0\n"
            "  0\nSPLINE\n  8\n0\n")
    f = tmp_path / "t.dxf"; f.write_text(_dxf(ents, blocks))
    assert dg.file_units(str(f)) == "Millimeters"
    res = dg.import_geometry(str(f), dg.UNITS["Millimeters"], existing_blocks={"Other"}, existing_layers={"0"})
    L = [e for e in res.entities if isinstance(e, m.Line)]
    assert abs(L[0].x2 - 10.0) < 1e-9 and L[0].style.layer == "HID" and L[0].style.linetype == "dashed"
    A = [e for e in res.entities if isinstance(e, m.Arc)]
    assert abs(A[0].r - 1.0) < 1e-9 and A[0].end == 90.0
    half = [a for a in A if abs(a.r - 0.5) < 1e-6]                              # bulge 1 = half circle, radius = chord / 2
    assert len(half) == 1 and abs(half[0].cx - 0.5) < 1e-6 and abs(((half[0].end - half[0].start) % 360) - 180) < 1e-6
    refs = [e for e in res.entities if isinstance(e, m.BlockRef)]
    assert len(refs) == 1 and refs[0].block == "SYM" and refs[0].rotation == 90.0 and abs(refs[0].x - 10.0) < 1e-9
    assert "SYM" in res.blocks and len(res.blocks["SYM"].slots) == 1 and abs(res.blocks["SYM"].slots[0].x - 1.0) < 1e-9
    circles = [e for e in res.entities if isinstance(e, m.Circle)]                # the scaled insert was exploded: r 0.5 * 2
    assert len(circles) == 1 and abs(circles[0].r - 1.0) < 1e-9
    t = [e for e in res.entities if isinstance(e, m.Text)][0]
    assert t.source == "HELLO" and t.align == "center" and abs(t.x - 2.0) < 1e-9
    assert res.stats["skipped SPLINE"] == 1
    assert set(res.layers) == {"HID"} and res.layers["HID"].linetype == "dashed" and res.layers["HID"].color == 3
    # a name that is taken is renamed, refs follow
    r2 = dg.import_geometry(str(f), 1.0, existing_blocks={"SYM"})
    assert "SYM_dxf" in r2.blocks and [e.block for e in r2.entities if isinstance(e, m.BlockRef)] == ["SYM_dxf"]
    sh = dg.scratch_sheet(res, "DXF: t")
    from electro.geometry import bounds
    b = bounds(sh.entities, res.blocks)
    assert abs(b[0] - 1.0) < 1e-6 and abs(b[1] - 1.0) < 1e-6 and sh.width >= 12.0


def test_dxf_old_polyline_and_binary_refused(tmp_path):
    from electro import dxfgeom as dg
    pl = ("  0\nPOLYLINE\n  8\n0\n 70\n1\n  0\nVERTEX\n 10\n0\n 20\n0\n  0\nVERTEX\n 10\n2\n 20\n0\n"
          "  0\nVERTEX\n 10\n2\n 20\n2\n  0\nSEQEND\n")
    f = tmp_path / "p.dxf"; f.write_text(_dxf(pl))
    res = dg.import_geometry(str(f), 1.0)
    assert len(res.entities) == 3 and all(isinstance(e, m.Line) for e in res.entities)      # closed triangle
    b = tmp_path / "b.dxf"; b.write_bytes(b"AutoCAD Binary DXF\r\n\x1a\x00rest")
    with pytest.raises(ValueError):
        dg.import_geometry(str(b), 1.0)


def test_goto_uses_the_free_end_whichever_side():
    from electro import numbering as nb, blocks as bk
    p = m.Project("e"); sh = p.add_sheet(m.Sheet(1)); sh2 = p.add_sheet(m.Sheet(2))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    pb = bk.make_block("PB", [m.Line(0, 0, 1, 0, m.Style("0")), m.SlotMark(0, 0, "1")], (0, 0), (), "above")
    p.blocks["PB"] = pb
    sh.entities += [m.Line(0, 5, 3, 5, m.Style("W")), m.BlockRef("PB", 3, 5)]       # a part sits on the RIGHT end
    sh2.entities += [m.Line(0, 5, 3, 5, m.Style("W"))]
    na = nb.build_nets(p, sh)[0]; nbn = nb.build_nets(p, sh2)[0]
    put, bad = nb.goto_connectors(p, (1, na), (2, nbn), "7-1")
    (_, k1, pt1, r1, _), (_, k2, pt2, r2, _) = put
    assert pt1 == (0, 5) and r1 == 180.0                 # the part holds the right end, so the From takes the left end
    assert pt2 == (0, 5)


def test_move_sheet():
    from electro import templates as t
    p = m.Project("mv")
    cv = t.cover_sheet(); p.add_sheet(cv)
    shs = {pg: p.add_sheet(t.sheet_from_template(t.tabloid_template(1), pg, f"S{pg}")) for pg in (1, 2, 3, 4)}
    assert p.move_sheet(2, 3) == {2: 3, 3: 2}                        # 2 -> 3, the old 3 becomes 2
    assert shs[2].page == 3 and shs[3].page == 2 and p.sheets[3] is shs[2] and sorted(p.sheets) == [0, 1, 2, 3, 4]
    assert p.move_sheet(4, 1) == {4: 1, 1: 2, 2: 3, 3: 4}            # to the front: everything else shifts
    assert p.sheets[1] is shs[4] and p.sheets[0].cover
    assert p.move_sheet(1, 1) == {}
    with pytest.raises(ValueError):
        p.move_sheet(0, 2)                                           # the cover is not moved


def test_goto_names_follow_wire_numbers():
    from electro import numbering as nb, blocks as bk
    p = m.Project("r")
    s1, s2 = p.add_sheet(m.Sheet(1)), p.add_sheet(m.Sheet(2))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    w1 = m.Line(0, 5, 3, 5, m.Style("W")); w1.number = m.WireNumber("auto", "09")
    w2 = m.Line(0, 5, 3, 5, m.Style("W")); w2.number = m.WireNumber("auto", "09")
    f = m.BlockRef("From", 3, 5, tag="07-1"); t_ = m.BlockRef("To", 0, 5, tag="07-1")
    s1.entities += [w1, f]; s2.entities += [w2, t_]
    assert nb.goto_renames(p) == [("07-1", "09-1")]                  # the wires are 09 now: the set follows
    w1.number = m.WireNumber("auto", "07"); w2.number = m.WireNumber("auto", "07")
    assert nb.goto_renames(p) == []                                  # numbers match the name: nothing to do
    w1.number = m.WireNumber("auto", "09"); w2.number = m.WireNumber("auto", "09")
    s2.entities.append(m.BlockRef("To", 9, 9, tag="09-1"))           # 09-1 is already taken somewhere
    assert nb.goto_renames(p) == [("07-1", "09-2")]


def test_block_label_corners_and_part_offset():
    from electro import blocks as bk
    box = [m.Line(0, 0, 4, 0, m.Style("0")), m.Line(4, 0, 4, 3, m.Style("0")), m.Line(4, 3, 0, 3, m.Style("0")),
           m.Line(0, 3, 0, 0, m.Style("0"))]
    p = m.Project("l"); sh = p.add_sheet(m.Sheet(1))
    for pos, ax, ay_top in (("topleft", "left", True), ("topright", "right", True),
                            ("bottomleft", "left", False), ("bottomright", "right", False)):
        b = bk.make_block("PLC", box, (0, 0), ("description", "tag"), pos, tag_prefix="A")
        txts = [e for e in b.entities if isinstance(e, m.Text)]
        assert all(t.align == ax for t in txts)
        xs = {round(t.x, 3) for t in txts}
        assert xs == ({0.1} if ax == "left" else {3.9})
        ys = [t.y for t in txts]
        assert (max(ys) > 2.5) if ay_top else (max(ys) < 1.0)         # inside the corner, not mid-page
    p.blocks["PLC"] = b
    r = m.BlockRef("PLC", 2, 2, tag="A1")
    home = bk.label_anchor(p, sh, b, r)
    r.props["label_dx"], r.props["label_dy"] = "1.5", "-0.25"
    moved = bk.label_anchor(p, sh, b, r)
    assert abs(moved[0] - home[0] - 1.5) < 1e-9 and abs(moved[1] - home[1] + 0.25) < 1e-9


def test_update_reports_override_wires():
    from electro import numbering as nb
    p = m.Project("o"); sh = p.add_sheet(m.Sheet(1))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    ln = m.Line(1, 5, 3, 5, m.Style("W")); ln.number = m.WireNumber("override", "00099")
    sh.entities.append(ln)
    rep = nb.update(p)
    assert len(rep.overrides) == 1


def test_from_wire_is_the_number_source():
    from electro import numbering as nb, blocks as bk
    p = m.Project("s")
    s1 = p.add_sheet(m.Sheet(1)); s3 = p.add_sheet(m.Sheet(3))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<page><zone><incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    l1 = m.Line(1, 5, 3, 5, m.Style("W")); l1.mark = "1"
    l3 = m.Line(1, 5, 3, 5, m.Style("W")); l3.mark = "1"
    s1.entities += [l1, m.BlockRef("To", 1, 5, 0)]
    s3.entities += [l3, m.BlockRef("From", 3, 5, 0)]
    for r in (s1.entities[-1], s3.entities[-1]):
        r.tag = "X-1"
    rep = nb.update(p)
    v3 = [num.value for l, num in rep.changes.get(3, [])]
    v1 = [num.value for l, num in rep.changes.get(1, [])]
    assert v3 and v1 and v1[0] == v3[0] and v3[0].startswith("03")


def test_to_wire_uses_no_global_count():
    from electro import numbering as nb, blocks as bk
    p = m.Project("c")
    s1 = p.add_sheet(m.Sheet(1)); s3 = p.add_sheet(m.Sheet(3))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    la = m.Line(1, 5, 3, 5, m.Style("W")); la.mark = "1"      # sheet 1: the To wire
    lb = m.Line(1, 3, 3, 3, m.Style("W")); lb.mark = "1"      # sheet 1: an ordinary wire
    lc = m.Line(1, 5, 3, 5, m.Style("W")); lc.mark = "1"      # sheet 3: the From wire
    ra = m.BlockRef("To", 1, 5, 0); ra.tag = "X-1"; rc = m.BlockRef("From", 3, 5, 0); rc.tag = "X-1"
    s1.entities += [la, lb, ra]; s3.entities += [lc, rc]
    rep = nb.update(p)
    v = {l.id: n.value for pg in rep.changes for l, n in rep.changes[pg]}
    assert v[la.id] == v[lc.id] and v[lb.id] != v[la.id]
    nums = sorted(v.values())
    assert len(set(nums)) == 2 and int(nums[1]) - int(nums[0]) == 1      # no gap left by the To wire


def test_exclude_from_bom_and_rotated_label():
    from electro import reports, blocks as bk, xmlio
    p = m.Project("x"); sh = p.add_sheet(m.Sheet(1))
    b = bk.make_block("PB", [m.Line(0, 0, 1, 0, m.Style("0")), m.SlotMark(0, 0, "1")], (0, 0), ("xref",), "right",
                      part_number="A1")
    p.blocks["PB"] = b
    sh.entities.append(m.BlockRef("PB", 2, 2))
    assert len(reports.bom(p)[1]) == 1
    sh.entities[-1].props["exclude_bom"] = "1"                 # per placed part (Part properties)
    assert reports.bom(p)[1] == []
    del sh.entities[-1].props["exclude_bom"]
    b.exclude_bom = 1
    assert reports.bom(p)[1] == []
    assert xmlio.block_from_xml(xmlio.block_to_xml(b)).exclude_bom == 1
    b.exclude_bom = 0
    t0 = [t for t in bk.block_entities(b, m.BlockRef("PB", 0, 0, 0)) if isinstance(t, m.Text)][0]
    t1 = [t for t in bk.block_entities(b, m.BlockRef("PB", 0, 0, 180)) if isinstance(t, m.Text)][0]
    assert t0.align == "left" and t1.align == "right" and t1.x < t0.x


def test_goto_reuses_existing_connector():
    from electro import numbering as nb, blocks as bk
    p = m.Project("r"); s1 = p.add_sheet(m.Sheet(1)); s3 = p.add_sheet(m.Sheet(3))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<g_incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    la = m.Line(1, 5, 3, 5, m.Style("W")); lb = m.Line(1, 5, 3, 5, m.Style("W"))
    fr = m.BlockRef("From", 3, 5, 0); fr.tag = "GND"                     # the wire already has a From
    s3.entities += [la, fr]; s1.entities += [lb]
    na = nb.build_nets(p, s3)[0]; nbn = nb.build_nets(p, s1)[0]
    put, bad = nb.goto_connectors(p, (3, na), (1, nbn), "GND-2")
    assert [(pg, k, n) for pg, k, _, _, n in put] == [(1, "To", "GND")]    # no second From; the To joins GND


def test_unnumbered_wire_takes_number_from_its_to():
    from electro import numbering as nb, blocks as bk
    p = m.Project("t"); s1 = p.add_sheet(m.Sheet(1))
    p.layers["W"] = m.Layer("W", 5, "wire", True, "<page><zone><incident>")
    for k in ("from", "to"):
        b = bk.default_connector_block(k); p.blocks[b.name] = b
    ln = m.Line(1, 5, 3, 5, m.Style("W"))                     # not marked, nothing reaches it
    to = m.BlockRef("To", 1, 5, 0); to.tag = "03000-1"
    s1.entities += [ln, to]
    rep = nb.update(p)
    assert [n.value for _, n in rep.changes[1]] == ["03000"] and not rep.unreached


# ------------------------------------------------------------------ panel layout
def _panel_project():
    from electro import blocks as bk
    p = m.Project("pl")
    sch = p.add_sheet(m.Sheet(1))
    b = bk.make_block("MCB", [m.Line(0, 0, 1, 0, m.Style("0"))], (0, 0), ("tag",), "right")
    b.fp_w, b.fp_h, b.fp_d, b.mount, b.rail_cl = 0.7, 3.5, 2.8, "rail", 0.0
    p.blocks["MCB"] = b
    for t in ("QF1", "QF2"):
        r = m.BlockRef("MCB", 1, 1); r.tag = t
        sch.entities.append(r)
    pan = m.Sheet(2, "Panel", row_pitch=1.0, grid_divisions=3, width=28, height=34, zone0_y=2.0)
    pan.panel = True
    p.add_sheet(pan)
    return p, pan


def test_panel_geometry_and_rotation():
    from electro import panel as pn, geometry as g
    d = m.PanelObj("duct", 5, 5, 4, 1.5, depth=3)
    assert pn.box(d) == (3, 4.25, 7, 5.75) and pn.axis(d) == "x"
    g.rotate_entity(d, (5, 5), 90)
    assert pn.axis(d) == "y" and pn.box(d) == (4.25, 3, 5.75, 7)
    g.translate(d, 1, 1)
    assert (d.cx, d.cy) == (6, 6)
    p0, p1 = pn.end_points(d)
    assert p0 == (6, 4) and p1 == (6, 8)


def test_panel_set_end_keeps_other_end():
    from electro import panel as pn
    r = m.PanelObj("rail", 5, 5, 1, 1.378)               # inserted 1 in long: 4.5 .. 5.5
    pn.set_end(r, 1, (9, 5))
    assert pn.end_points(r) == ((4.5, 5), (9, 5)) and abs(r.w - 4.5) < 1e-9
    pn.set_end(r, 0, (12, 5))                              # dragged past the other end: the ends swap, no flip-over
    assert pn.end_points(r) == ((9, 5), (12, 5))


def test_panel_rail_snap_and_alignment():
    from electro import panel as pn, blocks as bk
    p, pan = _panel_project()
    rail = m.PanelObj("rail", 10, 10, 8, 1.378)
    other = m.PanelObj("part", 8, 10, 0.7, 3.5, mount="rail", block="MCB", tag="QF1")
    part = pn.footprint_part(p.blocks["MCB"], "QF2")
    cx, cy, rot, r = pn.rail_snap([rail, other], part, 9.2, 11.0)
    assert r is rail and rot == 0 and abs(cy - 10) < 1e-9 and 6 <= cx <= 14
    part.cl = 0.5                                          # rail line 0.5 above the part's centre
    cx, cy, rot, r = pn.rail_snap([rail], part, 9.2, 11.0)
    assert abs(cy - 9.5) < 1e-9
    sx, sy, guides = pn.snap_box([other], 8.7 + 0.02, 10.04, 0.7, 3.5, 0.1)   # right beside it: edges line up
    assert abs(sx - 8.7) < 1e-9 and abs(sy - 10) < 1e-9 and guides
    v, g = pn.snap_line([other], 0, 8.0 + 0.7 / 2 + 0.25 + 0.04, 0.1, gap=0.25)  # a 0.25 gap from its right side
    assert abs(v - (8.35 + 0.25)) < 1e-9


def test_panel_unplaced_parts_and_checks(tmp_path):
    from electro import panel as pn, xmlio
    p, pan = _panel_project()
    assert pn.unplaced_parts(p) == [("QF1", "MCB"), ("QF2", "MCB")]
    plate = m.PanelObj("plate", 14, 17, 24, 30)
    rail = m.PanelObj("rail", 14, 17, 10, 1.378)
    a = pn.footprint_part(p.blocks["MCB"], "QF1", 10.0, 17.0)
    b = pn.footprint_part(p.blocks["MCB"], "QF2", 10.3, 17.0)               # overlaps QF1
    pan.entities += [plate, rail, a, b]
    assert pn.unplaced_parts(p) == []
    probs = pn.problems(pan)
    assert any("QF1 overlaps QF2" in s for s in probs)
    b.cx = 11.0
    assert pn.problems(pan) == []
    b.cx = 27.0                                                              # off the rail and off the plate
    probs = pn.problems(pan)
    assert any("off the back plate" in s for s in probs) and any("not on a DIN rail" in s for s in probs)
    p.blocks["MCB"].exclude_bom = 1
    assert pn.needed_parts(p) == []
    p.blocks["MCB"].exclude_bom = 0
    path = tmp_path / "p.eqt"
    xmlio.save_project(p, str(path))
    q = xmlio.load_project(str(path))
    qs = q.sheets[2]
    assert qs.panel and [o.kind for o in qs.entities] == ["plate", "rail", "part", "part"]
    assert qs.entities[2].tag == "QF1" and qs.entities[2].mount == "rail" and qs.entities[2].depth == 2.8
    assert (q.blocks["MCB"].fp_w, q.blocks["MCB"].fp_h, q.blocks["MCB"].mount) == (0.7, 3.5, "rail")


def test_panel_dxf_export_outline():
    from unittest import mock
    from electro import dxfexport
    o = m.PanelObj("duct", 5, 5, 4, 1.5, depth=3)
    ex = dxfexport.Exporter.__new__(dxfexport.Exporter)
    ex.attribs = lambda st: {"layer": "Panel duct"}
    ex.linetype = lambda n: "DASHED"
    lay = mock.MagicMock()
    ex.add_entity(lay, o)
    lay.add_lwpolyline.assert_called_once()
    assert lay.add_lwpolyline.call_args[0][0][0] == (3, 4.25)
    lay.add_line.assert_called_once(); lay.add_text.assert_called_once()


def test_terminal_stack_bom_ungroup_and_dims():
    from electro import panel as pn, reports, geometry as g, xmlio, blocks as bk
    p, pan = _panel_project()
    tb = bk.make_block("TB", [m.Line(0, 0, 0.2, 0, m.Style("0"))], (0, 0), (), "right", part_number="T-1")
    tb.fp_w, tb.fp_h, tb.fp_d, tb.mount = 0.2, 1.9, 1.5, "rail"
    p.blocks["TB"] = tb
    stack = pn.footprint_terminals(tb, 5, 10.0, 10.0)
    assert stack.kind == "terminals" and stack.qty == 5 and abs(stack.w - 1.0) < 1e-9
    pan.entities.append(stack)
    rows = reports.bom(p)[1]
    tbrow = [r for r in rows if r[5] == "TB"][0]
    assert tbrow[1] == 5 and tbrow[2] == "T-1"                    # on the layout only, in the BOM, qty 5
    stack.xbom = True
    assert not [r for r in reports.bom(p)[1] if r[5] == "TB"]     # the option to exclude
    stack.xbom = False
    kids = pn.ungroup(stack)
    assert len(kids) == 5 and all(k.kind == "part" and abs(k.w - 0.2) < 1e-9 and not k.tag for k in kids)
    assert abs(kids[0].cx - 9.6) < 1e-9 and abs(kids[4].cx - 10.4) < 1e-9
    stack.rot = 90                                                 # a turned stack ungroups along the turned axis
    k2 = pn.ungroup(stack)
    assert abs(k2[0].cy - 9.6) < 1e-9 and abs(k2[4].cy - 10.4) < 1e-9 and abs(k2[0].cx - 10.0) < 1e-9
    pan.entities.remove(stack); pan.entities += kids
    assert [r for r in reports.bom(p)[1] if r[5] == "TB"][0][1] == 5
    d = m.Dim(2, 2, 7, 4, "h", 5.5)
    assert pn.dim_value(d) == 5 and pn.dim_auto_orient((0, 0), (1, 3)) == "v"
    assert pn.dim_text(5, "in") == '5.0"' and pn.dim_text(1, "mm") == "25" and pn.dim_text(12.54, "in") == '12.5"'
    pan.entities.append(d)
    g.rotate_entity(d, (0, 0), 90)
    assert d.orient == "v" and pn.dim_value(d) == 5
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "d.eqt")
    pan.dim_units = "mm"
    xmlio.save_project(p, path)
    q = xmlio.load_project(path)
    qd = [e for e in q.sheets[2].entities if isinstance(e, m.Dim)][0]
    assert qd.orient == "v" and q.sheets[2].dim_units == "mm"
    assert not q.blocks["TB"].exclude_bom and q.blocks["TB"].mount == "rail"


def test_terminal_labels_and_ungroup():
    from electro import panel as pn, xmlio
    o = m.PanelObj("terminals", 5, 5, 1.0, 1.9, qty=4, block="TB", ident="TB1")
    assert pn.terminal_labels(o) == ["TB1.1", "TB1.2", "TB1.3", "TB1.4"]
    pn.set_terminal_labels(o, "TB2", 3, ["TB2.3", "L+", "TB2.5", "TB2.6"])     # one custom label
    assert o.ident == "TB2" and o.first == 3 and o.names == "|L+||"
    assert pn.terminal_labels(o) == ["TB2.3", "L+", "TB2.5", "TB2.6"]
    kids = pn.ungroup(o)
    assert [pn.terminal_labels(k)[0] for k in kids] == ["TB2.3", "L+", "TB2.5", "TB2.6"]
    p = m.Project("t"); sh = m.Sheet(1, "Panel"); sh.panel = True; sh.entities.append(o); p.add_sheet(sh)
    assert pn.next_ident(p) == "TB1" if False else pn.next_ident(p, "TB") == "TB1"
    o.ident = "TB1"
    assert pn.next_ident(p) == "TB2"
    import tempfile, os
    f = os.path.join(tempfile.mkdtemp(), "t.eqt"); save_project(p, f)
    q = load_project(f)
    o2 = [e for e in q.sheets[1].entities if isinstance(e, m.PanelObj)][0]
    assert (o2.ident, o2.first, o2.names) == ("TB1", 3, "|L+||")


def test_dim_text_height_roundtrip_and_dxf(tmp_path):
    from electro import dxfexport
    p = m.Project("t"); sh = m.Sheet(1, "Panel"); sh.panel = True; sh.dim_th = 0.2
    d = m.Dim(0, 0, 4, 0, "h", 1.0, th=0.3); sh.entities.append(d); p.add_sheet(sh)
    f = str(tmp_path / "t.eqt"); save_project(p, f)
    q = load_project(f)
    assert abs(q.sheets[1].dim_th - 0.2) < 1e-9
    assert abs([e for e in q.sheets[1].entities if isinstance(e, m.Dim)][0].th - 0.3) < 1e-9


def test_profiles_file(tmp_path, monkeypatch):
    from electro import profiles as pf, panel as pn
    folder = str(tmp_path)
    assert pf.save("", "", "x", 1, 1, 1, folder=folder) is None                  # nothing to key it by
    path = pf.save("Siemens", "3RT2015", "https://x.test/a%20b", 0.9, 3.1, 3.5, "rail", 0.25, folder=folder)
    assert os.path.basename(path) == ".electro_profiles.ini"
    txt = open(path).read()
    assert "[3RT2015]" in txt and "part_number = 3RT2015" in txt and "hyperlink = https://x.test/a%20b" in txt
    profs = pf.load(folder)
    name, pr = pf.find(profs, "siemens", " 3rt2015 ")
    assert name == "3RT2015" and pr["width"] == 0.9 and pr["rail_cl"] == 0.25
    assert pf.find(profs, "", "", "https://x.test/a%20b")[0] == name              # by hyperlink
    assert pf.find(profs, "ABB", "zzz")[0] is None
    pf.save("Siemens", "3RT2015", "", 1.0, 3.0, 3.0, "plate", folder=folder)      # overwrite, same section
    assert len(pf.load(folder)) == 1 and pf.load(folder)[name]["mounting"] == "plate"
    with open(path, "a") as f:                                                     # a hand-written mm profile
        f.write("\n[ABB mm]\nmanufacturer = ABB\npart_number = A9\nwidth = 25.4\nheight = 50.8\ndepth = 0\nunits = mm\n")
    assert abs(pf.load(folder)["ABB mm"]["height"] - 2.0) < 1e-9
    # layout uses the profile for a generic block
    pf.set_folder(folder)
    p = m.Project("t")
    blk = m.BlockDef("breaker", tag_prefix="CB", mount="rail"); p.blocks["breaker"] = blk
    s = p.add_sheet(m.Sheet(1, "One"))
    s.entities.append(m.BlockRef("breaker", 1, 1, 0, True, "CB1", {"manufacturer": "ABB", "part_number": "A9"}))
    eff = pn.effective_block(p, blk, "CB1")
    assert abs(eff.fp_w - 1.0) < 1e-9 and abs(eff.fp_h - 2.0) < 1e-9 and eff.mount == "rail"
    assert pn.footprint_part(eff, "CB1") is not None and pn.footprint_part(blk, "CB1") is None
    pf.set_folder("")


def test_locked_rail_is_pinned():
    from electro import panel as pn
    EditorScene = type('E', (), {'is_pinned': staticmethod(pn.pinned)})
    r = m.PanelObj("rail", 1, 1, 5, 1.378, locked=True)
    assert EditorScene.is_pinned(r)
    r.locked = False
    assert not EditorScene.is_pinned(r)
    assert EditorScene.is_pinned(m.PanelObj("part", 1, 1, 1, 1, locked=True))      # any layout object can be locked
    assert not EditorScene.is_pinned(m.PanelObj("part", 1, 1, 1, 1))


def test_profile_per_placed_part_and_type(tmp_path):
    from electro import profiles as pf, panel as pn
    pf.set_folder(str(tmp_path))
    pf.save("A", "K1", "", 1.0, 3.0, 3.0, block="contactor")
    pf.save("B", "K2", "", 2.0, 4.0, 3.0, block="contactor")
    p = m.Project("t")
    blk = m.BlockDef("contactor", tag_prefix="KM", mount="rail"); p.blocks["contactor"] = blk
    field = m.BlockDef("limit", tag_prefix="LS"); p.blocks["limit"] = field        # Not on back plate
    s = p.add_sheet(m.Sheet(1, "One"))
    s.entities += [m.BlockRef("contactor", 1, 1, 0, True, "KM1", {"profile": "K1"}),
                   m.BlockRef("contactor", 2, 1, 0, True, "KM2", {"profile": "K2"}),
                   m.BlockRef("contactor", 3, 1, 0, True, "KM3", {"manufacturer": "B", "part_number": "K2"}),
                   m.BlockRef("limit", 4, 1, 0, True, "LS1", {})]
    assert [pn.effective_block(p, blk, t).fp_w for t in ("KM1", "KM2", "KM3")] == [1.0, 2.0, 2.0]
    assert pn.needed_parts(p) == [("KM1", "contactor"), ("KM2", "contactor"), ("KM3", "contactor")]   # LS1 is off the plate
    assert pn.effective_block(p, field, "LS1").mount == ""
    path, name = pf.save("A", "K1", "", 1.5, 3.0, 3.0, section="K1", return_name=True)
    assert name == "K1" and pn.effective_block(p, blk, "KM1").fp_w == 1.5
    pf.set_folder("")


def test_profiles_belong_to_a_block(tmp_path):
    from electro import profiles as pf
    f = str(tmp_path)
    pf.save("Automation Direct", "FU-DN", "", 0.39, 3.23, 2.0, block="Fuse", folder=f)
    pf.save("Phoenix", "1234", "", 0.5, 3.0, 2.0, block="Fuse", folder=f)
    pf.save("Banner", "PN", "", 1.4, 4.1, 2.9, block="2p Breaker", folder=f)
    profs = pf.load(f)
    assert sorted(pf.for_block(profs, "Fuse")) == ["1234", "FU-DN"]
    assert sorted(pf.for_block(profs, "2p Breaker")) == ["PN"]
    assert pf.find(profs, "", "PN", block="Fuse")[0] is None                    # another block's profile is not offered
    assert pf.find(profs, "", "FU-DN", block="Fuse")[0] == "FU-DN"
    assert pf.find(profs, "", "", "x", block="Fuse")[0] is None
    # same part number under another block gets its own section
    pf.save("Automation Direct", "FU-DN", "", 0.4, 3.0, 2.0, block="Fuse2", folder=f)
    assert "FU-DN (2)" in pf.load(f) and pf.load(f)["FU-DN (2)"]["block"] == "Fuse2"
    # old profiles without a block are given to the block whose parts use them
    p = m.Project("t"); s = p.add_sheet(m.Sheet(1, "One"))
    s.entities.append(m.BlockRef("Fuse", 1, 1, 0, True, "FU1", {"profile": "1234"}))
    import configparser
    cp = configparser.ConfigParser(); cp.read(f + "/.electro_profiles.ini"); del cp["1234"]["block"]
    cp.write(open(f + "/.electro_profiles.ini", "w"))
    assert pf.load(f)["1234"]["block"] == ""
    pf.claim_legacy(p, f)
    assert pf.load(f)["1234"]["block"] == "Fuse"


def test_profiles_adopted_into_library(tmp_path):
    from electro import profiles as pf
    proj, lib = tmp_path / "proj", tmp_path / "lib"
    proj.mkdir(); lib.mkdir()
    pf.save("A", "K1", "", 1, 1, 1, block="B", folder=str(proj))
    pf.set_folder(str(lib))
    assert pf.load() == {} and pf.adopt(str(proj)) is True
    assert "K1" in pf.load() and pf.adopt(str(proj)) is False
    pf.save("A", "K2", "", 1, 1, 1, block="B")                 # new profiles go to the library
    assert "K2" in pf.load(str(lib)) and "K2" not in pf.load(str(proj))
    pf.set_folder("")


def test_exclude_bom_roundtrip_and_old_false(tmp_path):
    from electro import xmlio
    p = m.Project("t"); b = m.BlockDef("x", exclude_bom=False); b.exclude_bom = True; p.blocks["x"] = b
    p.blocks["y"] = m.BlockDef("y", exclude_bom=False)
    p.add_sheet(m.Sheet(1, "One"))
    f = str(tmp_path / "t.eqt"); save_project(p, f)
    q = load_project(f)
    assert q.blocks["x"].exclude_bom and not q.blocks["y"].exclude_bom
    import zipfile, re
    z = zipfile.ZipFile(f)
    names = [n for n in z.namelist() if n.startswith("library/")]
    assert all(re.search(r'exclude_bom="[01]"', z.read(n).decode()) for n in names)
    # a file written by 0.20.3-0.20.7 holds "False" / "True"
    g = str(tmp_path / "old.eqt")
    with zipfile.ZipFile(f) as zi, zipfile.ZipFile(g, "w") as zo:
        for n in zi.namelist():
            d = zi.read(n)
            if n.startswith("library/"):
                d = d.replace(b'exclude_bom="1"', b'exclude_bom="True"').replace(b'exclude_bom="0"', b'exclude_bom="False"')
            zo.writestr(n, d)
    r = load_project(g)
    assert r.blocks["x"].exclude_bom and not r.blocks["y"].exclude_bom


def test_zone_comes_from_the_marked_wire():
    from electro import numbering as nb
    p = m.Project("t")
    p.layers["DC"] = m.Layer("DC", kind="wire", numbered=True, scheme="<page><zone><incident>")
    sh = p.add_sheet(m.Sheet(1, "One"))
    a = m.Line(7.0, 4.9, 13.0, 4.9, m.Style(layer="DC")); a.mark = "1"           # marked, zone 13
    b = m.Line(13.0, 4.9, 13.0, 3.85, m.Style(layer="DC"))
    c = m.Line(6.0, 3.85, 13.0, 3.85, m.Style(layer="DC"))                        # left-most end is at zone 16
    sh.entities += [a, b, c]
    rep = nb.update(p)
    assert {wn.value for lst in rep.changes.values() for _, wn in lst} == {"01131"}


def test_panel_sheets_stay_last():
    p = m.Project("t")
    p.add_sheet(m.Sheet(1, "A")); p.add_sheet(m.Sheet(2, "B"))
    pl = m.Sheet(3, "Panel"); pl.panel = True; p.add_sheet(pl)
    n = m.Sheet(99, "New")
    assert p.add_sheet_before_panels(n) == 3
    assert [(pg, s.panel) for pg, s in sorted(p.sheets.items())] == [(1, False), (2, False), (3, False), (4, True)]
    assert p.sheets[4] is pl and pl.page == 4 and n.page == 3
    p.move_sheet(1, 4)                                  # moving past the layout cannot put it behind it
    assert p.sheets[max(p.sheets)].panel
    p2 = m.Project("t2"); pl2 = m.Sheet(1, "P"); pl2.panel = True; p2.add_sheet(pl2)
    assert p2.add_sheet_before_panels(m.Sheet(5, "X")) == 1 and pl2.page == 2


def test_panel_pdf_page_template():
    from electro import templates
    pl = m.Sheet(3, "Layout", width=28, height=28); pl.panel = True
    s = templates.panel_pdf_sheet(pl)
    assert (s.width, s.height, s.page) == (17.0, 11.0, 3) and not s.panel
    assert s.frame and s.title_lines[0] == "Layout"
    assert not any(isinstance(e, m.Text) and e.source == "00" for e in s.frame)      # no zone numbers


def test_dot_numbers_list_and_counts():
    from electro import dots
    p = m.Project("t")
    p.layers["DC"] = m.Layer("DC", kind="wire", numbered=True, scheme="<page><zone><incident>")
    s1 = p.add_sheet(m.Sheet(1, "One")); s2 = p.add_sheet(m.Sheet(2, "Two"))
    def wire(x1, y1, x2, y2, val):
        ln = m.Line(x1, y1, x2, y2, m.Style(layer="DC")); ln.number = m.WireNumber("auto", val); return ln
    s1.entities += [wire(1, 1, 3, 1, "01131"), wire(1, 2, 3, 2, "01131"), wire(1, 3, 3, 3, "01160")]
    s1.entities += [m.Circle(3, 1, 0.04, m.Style(layer="DC"), filled=True), m.Circle(3, 2, 0.04, m.Style(layer="DC"), filled=True),
                    m.Circle(3, 3, 0.04, m.Style(layer="DC"), filled=True), m.Circle(9, 9, 0.04, m.Style(layer="DC"), filled=True)]
    s2.entities += [wire(1, 1, 3, 1, "01131"), m.Circle(1, 1, 0.04, m.Style(layer="DC"), filled=True),
                    m.Circle(2, 1, 0.04, m.Style(layer="DC"), filled=False)]          # an open circle is not a dot
    d = dots.dot_numbers(p)
    assert list(d) == ["01131", "01160"] and len(d["01131"]) == 3 and len(d["01160"]) == 1


def test_pdf_append(tmp_path):
    import pytest
    from electro import pdfmerge
    if not pdfmerge.available():
        pytest.skip("pypdf not installed")
    from pypdf import PdfWriter, PdfReader
    def pdf(n):
        w = PdfWriter()
        for _ in range(n):
            w.add_blank_page(100, 100)
        import io; b = io.BytesIO(); w.write(b); return b.getvalue()
    f = tmp_path / "a.pdf"; f.write_bytes(pdf(2))
    assert pdfmerge.append_pdfs(str(f), [pdf(3), b"not a pdf"]) == [1]
    assert len(PdfReader(str(f)).pages) == 5


def test_reference_pdfs_roundtrip(tmp_path):
    p = m.Project("t"); p.add_sheet(m.Sheet(1, "One"))
    p.assets["ref/manual.pdf"] = b"%PDF-1.4 fake"
    f = str(tmp_path / "t.eqt"); save_project(p, f)
    assert load_project(f).assets["ref/manual.pdf"] == b"%PDF-1.4 fake"


def test_dot_numbers_include_junction_dots():
    from electro import dots
    p = m.Project("t")
    p.layers["DC"] = m.Layer("DC", kind="wire", numbered=True, scheme="<page><zone><incident>")
    sh = p.add_sheet(m.Sheet(1, "One"))
    def wire(x1, y1, x2, y2):
        ln = m.Line(x1, y1, x2, y2, m.Style(layer="DC")); ln.number = m.WireNumber("auto", "01130"); return ln
    sh.entities += [wire(1, 1, 1, 5), wire(1, 2, 3, 2), wire(1, 4, 3, 4)]         # two taps on a bus: two automatic dots
    assert len(dots.dot_numbers(p)["01130"]) == 2


def test_used_counts_track_labelled_terminals():
    from electro import dots
    p = m.Project("t")
    sh = p.add_sheet(m.Sheet(2, "Panel")); sh.panel = True
    o = m.PanelObj("terminals", 0, 0, 6, 1, qty=6, names="01131|01131|01131|01131|01131|01131")
    sh.entities.append(o)
    assert dots.used_counts(p)["01131"] == 6
    assert "01131" not in dots.used_counts(p, skip=o)


def test_bare_prefix_tag_is_automatic_after_update():
    from electro import blocks as bk
    p = m.Project("t")
    sh = p.add_sheet(m.Sheet(1, "One"))
    blk = m.BlockDef("Dist_DC"); blk.tag_prefix = "PS"; p.blocks["Dist_DC"] = blk
    r = m.BlockRef("Dist_DC", 1.0, 5.6, 0.0, False, style=m.Style("0"))
    r.tag = "PS"
    sh.entities.append(r)
    bk.update_tags(p)
    assert r.tag.startswith("PS") and r.tag != "PS"


def test_update_tags_renames_panel_parts():
    from electro import blocks as bk
    p = m.Project("t")
    sh = p.add_sheet(m.Sheet(1, "One"))
    blk = m.BlockDef("Dist_DC"); blk.tag_prefix = "PS"; p.blocks["Dist_DC"] = blk
    r = m.BlockRef("Dist_DC", 1.0, 5.6, 0.0, False, style=m.Style("0")); r.tag = "PS"
    sh.entities.append(r)
    pl = p.add_sheet(m.Sheet(2, "Panel")); pl.panel = True
    o = m.PanelObj("part", 0, 0, 1, 1, block="Dist_DC", tag="PS"); pl.entities.append(o)
    bk.update_tags(p)
    assert r.tag != "PS" and o.tag == r.tag


def _dim_fixture():
    from electro import panel as pn
    sh = m.Sheet(2, "Panel"); sh.panel = True
    a = m.PanelObj("part", 2.0, 5.0, 2.0, 2.0)       # x 1..3
    b = m.PanelObj("part", 8.0, 5.0, 2.0, 2.0)       # x 7..9
    c = m.PanelObj("part", 12.0, 5.0, 2.0, 2.0)      # x 11..13
    d = m.Dim(3.0, 5.0, 7.0, 5.0, "h", 7.0)          # a right edge -> b left edge, 4"
    e = m.Dim(9.0, 5.0, 11.0, 5.0, "h", 7.0)         # b right edge -> c left edge, 2"
    sh.entities += [a, b, c, d, e]
    pn.attach_all(sh.entities)
    return pn, sh, a, b, c, d, e


def test_dimension_attaches_to_edges_and_follows():
    pn, sh, a, b, c, d, e = _dim_fixture()
    assert d.a1.endswith(":x1") and d.a2.endswith(":x0")
    b.cx += 1.0
    pn.sync_dims(sh.entities)
    assert abs(pn.dim_value(d) - 5.0) < 1e-9 and abs(d.x2 - 8.0) < 1e-9


def test_dimension_value_moves_both_unlocked_symmetrically():
    pn, sh, a, b, c, d, e = _dim_fixture()
    shifts, _ = pn.plan_dim_value(sh.entities, d, 6.0)         # +2": a -1, b +1 ...
    assert shifts[a.id][0] == -1.0 and shifts[b.id][0] == 1.0
    assert shifts[c.id][0] == 1.0                              # ... c follows b (dimension b-c kept)
    for o, mod in pn.shift_mods(sh.entities, shifts):
        for k, v in mod.items():
            setattr(o, k, v)
    pn.sync_dims(sh.entities)
    assert abs(pn.dim_value(d) - 6.0) < 1e-9 and abs(pn.dim_value(e) - 2.0) < 1e-9


def test_dimension_value_one_locked_and_both_locked():
    pn, sh, a, b, c, d, e = _dim_fixture()
    a.locked = True
    shifts, _ = pn.plan_dim_value(sh.entities, d, 6.0)
    assert a.id not in shifts and shifts[b.id][0] == 2.0
    b.locked = True
    shifts, why = pn.plan_dim_value(sh.entities, d, 6.0)
    assert shifts is None and "locked" in why


def test_drag_follows_unless_locked():
    pn, sh, a, b, c, d, e = _dim_fixture()
    shifts = {a.id: [-1.5, 0.0]}
    pn.propagate(sh.entities, shifts)
    assert shifts[b.id][0] == -1.5 and shifts[c.id][0] == -1.5
    b.locked = True
    shifts = {a.id: [-1.5, 0.0]}
    pn.propagate(sh.entities, shifts)
    assert b.id not in shifts and c.id not in shifts           # stops at the locked part; the dimension changes


def test_dim_attachment_roundtrip(tmp_path):
    from electro import xmlio
    pn, sh, a, b, c, d, e = _dim_fixture()
    p = m.Project("t"); p.add_sheet(sh)
    f = str(tmp_path / "x.eqt")
    xmlio.save_project(p, f)
    q = xmlio.load_project(f)
    dd = [x for x in q.sheets[2].entities if isinstance(x, m.Dim)]
    assert dd[0].a1 == d.a1 and dd[0].a2 == d.a2


def _hdr_project():
    from electro import blocks as bk
    p = m.Project("t")
    sh = p.add_sheet(m.Sheet(4, "P"))
    ents = [m.Line(0, 0, 1, 0, m.Style("0")), m.Line(1, 0, 1, 1, m.Style("0")), m.SlotMark(0, 0, "1")]
    blk = bk.make_block("LS", ents, (0, 0), ("description", "part_label", "tag"), "above", tag_prefix="LS")
    p.blocks["LS"] = blk
    p.header_styles["Big"] = m.HeaderStyle(
        "Big", "<color=3><size=1.5>{DESC}</size></color>\n<color=4>{PART}</color>\n<size=0.8>{LOC}</size>", 0.1,
        "Ubuntu", "auto", 1.2)
    ref = m.BlockRef("LS", 3.0, 3.0, 0.0, False, style=m.Style("0")); ref.tag = "LS0415"
    ref.props["description"] = "X HOME"
    sh.entities.append(ref)
    return p, sh, blk, ref


def test_header_style_compacts_and_styles():
    from electro import blocks as bk, richtext
    p, sh, blk, ref = _hdr_project()
    bk.rebuild_label(blk, ("description", "part_label", "tag"), "above", "Big")
    assert blk.header == "Big" and bk.label_lines_of(blk) == ("description", "part_label", "tag")
    t = [e for e in bk.resolved_entities(p, sh, blk, ref) if isinstance(e, m.Text)][0]
    assert t.rich and t.font == "Ubuntu" and abs(t.height - 0.1) < 1e-9
    assert richtext.plain(t.resolved) == "X HOME\nLS0415"             # no part number: that line is gone
    assert "<color=3><size=1.5>X HOME</size></color>" in t.resolved
    base = [e for e in bk.block_entities(blk, ref) if isinstance(e, m.Text)][0].y
    assert t.y > base                                                  # grows upward from the bottom line
    ref.props["hide"] = "tag"
    t = [e for e in bk.resolved_entities(p, sh, blk, ref) if isinstance(e, m.Text)][0]
    assert richtext.plain(t.resolved) == "X HOME"


def test_header_roundtrip_and_font_tag(tmp_path):
    from electro import xmlio, blocks as bk, richtext
    p, sh, blk, ref = _hdr_project()
    bk.rebuild_label(blk, ("description", "tag"), "right", "Big")
    f = str(tmp_path / "h.eqt")
    xmlio.save_project(p, f)
    q = xmlio.load_project(f)
    assert q.blocks["LS"].header == "Big" and q.blocks["LS"].header_lines == "description,tag"
    assert q.header_styles["Big"].template == p.header_styles["Big"].template and q.header_styles["Big"].spacing == 1.2
    runs = richtext.parse("<font=Ubuntu Mono>ab</font>c")
    assert runs[0][0].font == "Ubuntu Mono" and runs[0][1].font == "" and richtext.dumps(runs) == "<font=Ubuntu Mono>ab</font>c"
    assert bk.block_from_sheet(q.blocks["LS"], bk.edit_sheet(q.blocks["LS"])).header == "Big"


def test_header_gap_moves_text_toward_part(tmp_path):
    from electro import blocks as bk, xmlio
    p, sh, blk, ref = _hdr_project()
    bk.rebuild_label(blk, ("description", "tag"), "above", "Big")
    y0 = [e for e in bk.resolved_entities(p, sh, blk, ref) if isinstance(e, m.Text)][0].y
    p.header_styles["Big"].gap = 0.03
    y1 = [e for e in bk.resolved_entities(p, sh, blk, ref) if isinstance(e, m.Text)][0].y
    assert abs((y0 - y1) - 0.07) < 1e-9
    f = str(tmp_path / "g.eqt"); xmlio.save_project(p, f)
    assert abs(xmlio.load_project(f).header_styles["Big"].gap - 0.03) < 1e-9


def test_header_gap_can_be_negative():
    from electro import blocks as bk
    p, sh, blk, ref = _hdr_project()
    bk.rebuild_label(blk, ("description", "tag"), "above", "Big")
    y0 = [e for e in bk.resolved_entities(p, sh, blk, ref) if isinstance(e, m.Text)][0].y
    p.header_styles["Big"].gap = -0.05
    y1 = [e for e in bk.resolved_entities(p, sh, blk, ref) if isinstance(e, m.Text)][0].y
    assert abs((y0 - y1) - 0.15) < 1e-9
