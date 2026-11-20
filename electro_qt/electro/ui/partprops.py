"""Part properties: one dialog for making a block, editing a library block and editing a placed part.

The Type decides which fields show:
  On back plate      everything, incl. profile + to-scale footprint
  Not on back plate  everything except profile / footprint (still in the BOM)
  Off-page connector name, folder, tag prefix, tag, cross-reference
  Exclude from BOM   name, folder, wire numbering, description, tag (not in the BOM, not on the layout)

Type, name, folder, tag prefix, poles, increment, letter rule, label position belong to the block (all copies).
Description, tag, manufacturer, part number, hyperlink, profile and footprint belong to each placed part.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                               QDialogButtonBox, QLabel, QDoubleSpinBox, QWidget, QTableWidget, QTableWidgetItem,
                               QPushButton, QHeaderView, QScrollArea, QFormLayout)
from PySide6.QtCore import Qt
from .. import blocks as bk
from .. import panel as pn
from .. import profiles as pf
from .partdlg import TagPickerDialog

TYPES = (("On back plate", "plate"), ("Not on back plate", "off"), ("Off-page connector", "conn"),
         ("Exclude from BOM", "xbom"))
ALL = {"name", "type", "folder", "prefix", "poles", "inc", "rule", "desc", "tag", "xref", "profile", "mfr", "part",
       "link", "fp", "pos", "hdr", "origin", "terms"}
SHOW = {"plate": ALL,
        "off": ALL - {"profile", "fp"},
        "conn": {"name", "type", "folder", "prefix", "tag", "xref", "pos", "hdr", "origin", "terms"},
        "xbom": {"name", "type", "folder", "prefix", "poles", "inc", "rule", "desc", "tag", "pos", "hdr", "origin", "terms"}}
LINES = (("description", "desc"), ("part_label", "part"), ("tag", "tag"), ("xref", "xref"))


def type_of(b):
    if b is None:
        return "plate"
    if b.connector:
        return "conn"
    if b.exclude_bom:
        return "xbom"
    return "plate" if b.mount else "off"


class PartPropertiesDialog(QDialog):
    def __init__(self, parent, project=None, block=None, ref=None, poles=1, folders=(), folder="", rules=(),
                 slot_names=None):
        """block=None: making a block.  block only: a library / project block's data.  block + ref: a placed part."""
        super().__init__(parent)
        self.project, self.block, self.ref = project, block, ref
        self.make = block is None
        self.part_mode = ref is not None
        self.geometry_requested = False
        self.setWindowTitle("Part properties" + (f" - {block.name}" if block else " - new block"))
        b = block
        p = ref.props if ref else {}
        allc = " (all copies)" if self.part_mode else ""
        eff = pn.effective_block(project, b, ref.tag, ref=ref) if self.part_mode else b
        self.rows = {}
        outer = QVBoxLayout(self)
        body = QWidget(); self.col = QVBoxLayout(body); self.col.setContentsMargins(0, 0, 0, 0)

        # ---- block
        self.name = QLineEdit(b.name if b else ""); self.name.setEnabled(self.make)
        self._row("name", "Name", self.name)
        self.type = QComboBox()
        for lab, key in TYPES:
            self.type.addItem(lab, key)
        self.type.setCurrentIndex(max(0, self.type.findData(type_of(b))))
        self.type.setToolTip("What the part is. Applies to every copy of the block; the fields below follow it.")
        self._row("type", "Type" + allc, self.type)
        self.folder = QComboBox(); self.folder.addItem("(top level)", "")
        for f in folders:
            self.folder.addItem(f, f)
        self.folder.setCurrentIndex(max(0, self.folder.findData(b.folder if b else folder)))
        self._row("folder", "Folder" + allc, self.folder)
        self.prefix = QLineEdit(b.tag_prefix if b else "")
        self.prefix.setToolTip("Device tag = prefix + page + zone, e.g. K + 03 + 14 = K0314")
        self._row("prefix", "Tag prefix" + allc, self.prefix)
        self.poles = QSpinBox(); self.poles.setRange(1, 12); self.poles.setValue(b.poles if b else poles)
        self._row("poles", "Poles" + allc, self.poles)
        self.inc = QComboBox(); self.inc.addItem("None", 0); self.inc.addItem("+1", 1)
        self.inc.setCurrentIndex(1 if (b and b.increment == 1) else 0)
        self._row("inc", "Wire number increment" + allc, self.inc)
        self.rule = QComboBox(); self.rule.addItem("(none)", "")
        names = [r.name for r in rules]
        if b and b.prefix_rule and b.prefix_rule not in names:
            names.append(b.prefix_rule)
        for n in names:
            self.rule.addItem(n, n)
        self.rule.setCurrentIndex(max(0, self.rule.findData(b.prefix_rule if b else "")))
        self.rule.setToolTip("A letter rule defined under Sheet > Letter rules...")
        self._row("rule", "Letter rule" + allc, self.rule)

        # ---- label lines: each checkbox sits next to its field
        have = set(bk.label_lines_of(b)) if b else {"description", "part_label", "tag"}
        hidden = set(p.get("hide", "").split(","))
        self.show = {}
        for key, _ in LINES:
            cb = QCheckBox("show"); cb.setChecked(key in have and key not in hidden)
            cb.setToolTip("Show this line in the part's label"
                          + (" (turning on a line the block does not show yet adds it to every copy)" if self.part_mode else ""))
            self.show[key] = cb

        self.desc = QLineEdit(p.get("description", b.description) if b else "")
        self._row("desc", "Description", self.desc, self.show["description"])
        self.tag = QLineEdit(ref.tag if ref else "")
        self.link_tag = ref.props.get("tag_link") if (ref and ref.props.get("tag_mode") == "linked") else None
        self.tag.textEdited.connect(lambda _t: setattr(self, "link_tag", None))
        if self.part_mode:
            pick = QPushButton("Pick...")
            pick.setToolTip("Take the tag of another placed block (e.g. the coil). The tag then follows that block when tags are updated.")
            pick.clicked.connect(self._pick)
            self._row("tag", "Tag", self.tag, pick, self.show["tag"])
        else:
            self._row("tag", "Tag", QLabel("(assigned when placed)"), self.show["tag"])
        self._row("xref", "Cross-reference", QLabel(""), self.show["xref"])

        # ---- the part: profile, manufacturer, part number, hyperlink
        mf0 = p.get("manufacturer", b.manufacturer) if b else ""
        pn0 = p.get("part_number", b.part_number) if b else ""
        hl0 = p.get("hyperlink", b.hyperlink) if b else ""
        if project is not None:
            pf.claim_legacy(project)                          # profiles from before they were tied to a block
        self.profs = pf.load()
        self.bname = b.name if b else ""
        self.mine = pf.for_block(self.profs, self.bname)      # only this block's profiles are offered
        self.profile = QComboBox()
        self.profile.setToolTip("Profiles of this block (" + pf.FILE + "). Pick one, or paste a part number below.")
        self.profile.addItem("(new profile)", "")
        for name in sorted(self.mine):
            self.profile.addItem(name, name)
        cur = p.get("profile", "")
        if cur not in self.mine:
            cur = pf.find(self.mine, mf0, pn0, hl0)[0] or ""
        self.profile.setCurrentIndex(max(0, self.profile.findData(cur)))
        self._busy = False
        self.profile.currentIndexChanged.connect(self._profile_picked)    # any change: mouse, keyboard, wheel
        self._row("profile", "Profile", self.profile)
        self.mfr = QLineEdit(mf0)
        self._row("mfr", "Manufacturer", self.mfr)
        self.part = QLineEdit(pn0)
        self._row("part", "Part number", self.part, self.show["part_label"])
        self.link = QLineEdit(hl0)
        self.link.setPlaceholderText("Paste the product page / datasheet link")
        self._row("link", "Hyperlink", self.link)
        self._last = (self.mfr.text(), self.part.text(), self.link.text())

        # ---- footprint (to scale)
        self.fpbox = QWidget(); fl = QVBoxLayout(self.fpbox); fl.setContentsMargins(0, 0, 0, 0)
        self.fp_unit = QComboBox(); self.fp_unit.addItem("inches", 1.0); self.fp_unit.addItem("mm", 25.4)
        self.fp_unit.setToolTip("The footprint is stored in inches; this only changes how it is typed")
        self._fp_last = 1.0
        fl.addLayout(self._line("Footprint units", self.fp_unit))
        self.fp = {}
        for key, lab, val in (("fp_w", "Width (along the rail / plate)", eff.fp_w if eff else 0.0),
                              ("fp_h", "Height (across)", eff.fp_h if eff else 0.0),
                              ("fp_d", "Depth (off the plate)", eff.fp_d if eff else 0.0)):
            sp = QDoubleSpinBox(); sp.setDecimals(3); sp.setRange(0, 5000); sp.setValue(val)
            self.fp[key] = sp; fl.addLayout(self._line(lab, sp))
        self.mount = QComboBox()
        for lab, key in (("DIN rail", "rail"), ("Back plate (screws)", "plate")):
            self.mount.addItem(lab, key)
        self.mount.setCurrentIndex(max(0, self.mount.findData((eff.mount if eff else "") or "rail")))
        fl.addLayout(self._line("Mounting", self.mount))
        self.cl = QDoubleSpinBox(); self.cl.setDecimals(3); self.cl.setRange(-5000, 5000)
        self.cl.setValue(eff.rail_cl if eff else 0.0)
        self.cl.setToolTip("DIN rail centre line, measured from the footprint's centre toward its top (0 = centred)")
        fl.addLayout(self._line("Rail centre line offset", self.cl))
        self.note = QLabel("")
        self.note.setWordWrap(True)
        fl.addWidget(self.note)
        self.fp_unit.currentIndexChanged.connect(self._fp_units)
        self.rows["fp"] = self.fpbox; self.col.addWidget(self.fpbox)
        for w in (self.mfr, self.part, self.link):          # paste a manufacturer / part number / link: the profile fills in
            w.editingFinished.connect(self._lookup)

        # ---- label position, origin
        self.pos = QComboBox()
        self.pos.addItem("Above the part", "above"); self.pos.addItem("Right of the part", "right")
        for lab, key in (("Inside, top left", "topleft"), ("Inside, top right", "topright"),
                         ("Inside, bottom left", "bottomleft"), ("Inside, bottom right", "bottomright")):
            self.pos.addItem(lab, key)
        self.pos.addItem("Inside the part (small)", "center")
        self.pos.setCurrentIndex(max(0, self.pos.findData(b.label_pos)) if b else 0)
        self._row("pos", "Label position" + allc, self.pos)
        self.hdr = QComboBox()
        self.hdr.addItem("None (separate lines)", "")
        for hn in (project.header_styles if project is not None else ()):
            self.hdr.addItem(hn, hn)
        self.hdr.setCurrentIndex(max(0, self.hdr.findData(b.header)) if b else 0)
        self.hdr.setToolTip("How the label text looks: one styled header (Edit > Header styles...), "
                            "or separate plain lines")
        self._row("hdr", "Header style" + allc, self.hdr)
        self.origin = None
        if slot_names is not None and self.make:
            self.origin = QComboBox()
            for i, n in enumerate(slot_names):
                self.origin.addItem(f"Slot {i + 1}" + (f" ({n})" if n else ""), f"slot:{i}")
            self.origin.addItem("Center of the selection", "center")
            self.origin.addItem("Pick a point on the drawing...", "pick")
            self.origin.setToolTip("The point that sits on the cursor when the block is placed")
            self._row("origin", "Origin point", self.origin)

        # ---- terminals of a placed part
        self.table = QTableWidget(0, 2)
        if self.part_mode and b.slots:
            self.table.setRowCount(len(b.slots))
            self.table.setHorizontalHeaderLabels(["Slot", "Terminal"])
            for i, s in enumerate(b.slots):
                it = QTableWidgetItem(f"{i + 1}  ({s.x:+.2f}, {s.y:+.2f})")
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, 0, it)
                self.table.setItem(i, 1, QTableWidgetItem(bk.slot_name(ref, i, s)))
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.setMinimumHeight(120)
            pair = QPushButton("Pair numbering...")
            pair.setToolTip("Fill the terminals as pairs (13/14, 23/24 ...). You can still edit any of them.")
            pair.clicked.connect(self._pairs)
            tw = QWidget(); tl = QVBoxLayout(tw); tl.setContentsMargins(0, 0, 0, 0)
            tl.addWidget(QLabel("Terminals:")); tl.addWidget(self.table); tl.addWidget(pair)
            self.rows["terms"] = tw; self.col.addWidget(tw)
        self.col.addStretch(1)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(body)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        if not self.make:
            g = bb.addButton("Edit geometry", QDialogButtonBox.ButtonRole.ActionRole)
            g.setToolTip("Save these changes and open the block's drawing in its own tab")
            g.clicked.connect(self._geometry)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        outer.addWidget(bb)
        self.type.currentIndexChanged.connect(self._type_changed)
        self._type_changed()
        self._note()
        self.resize(540, 660)

    # ---- layout helpers: every row is its own widget, so any of them can be hidden on every Qt 6 version
    def _line(self, label, *widgets):
        h = QHBoxLayout(); h.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(label); lab.setMinimumWidth(200)
        h.addWidget(lab)
        for i, w in enumerate(widgets):
            h.addWidget(w, 1 if i == 0 else 0)
        return h

    def _row(self, key, label, *widgets):
        box = QWidget(); box.setLayout(self._line(label, *widgets))
        self.rows[key] = box; self.col.addWidget(box)

    def _type_changed(self):
        vis = set(SHOW[self.type.currentData()])
        if not self.part_mode:
            vis -= {"profile", "terms"}
        for key, w in self.rows.items():
            w.setVisible(key in vis)

    def _geometry(self):
        self.geometry_requested = True
        self.accept()

    # ---- profiles
    def _apply_profile(self, name):
        prof = self.mine.get(name)
        if prof is None:
            return
        k = self.fp_unit.currentData()
        for key, nm in (("fp_w", "width"), ("fp_h", "height"), ("fp_d", "depth")):
            self.fp[key].setValue(prof[nm] * k)
        self.cl.setValue(prof["rail_cl"] * k)
        self.mount.setCurrentIndex(max(0, self.mount.findData(prof["mounting"])))
        self.mfr.setText(prof["manufacturer"]); self.part.setText(prof["part_number"]); self.link.setText(prof["hyperlink"])

    def _set_profile(self, idx):
        self._busy = True
        try:
            self.profile.setCurrentIndex(idx)
        finally:
            self._busy = False

    def _profile_picked(self, *_):
        if self._busy:
            return
        name = self.profile.currentData()
        if name:
            self._apply_profile(name)          # manufacturer, part number, hyperlink and footprint of the profile
        self._last = (self.mfr.text(), self.part.text(), self.link.text())
        self._note()

    def _lookup(self):
        """A pasted manufacturer / part number / link that matches a saved profile selects it and fills the footprint."""
        now = (self.mfr.text(), self.part.text(), self.link.text())
        if now == getattr(self, "_last", None):
            return                              # nothing was typed (focus just moved): leave the selection alone
        self._last = now
        name = pf.find(self.mine, self.mfr.text(), self.part.text(), self.link.text())[0]
        if name:
            self._set_profile(max(0, self.profile.findData(name)))
            keep = self.link.text().strip()
            self._apply_profile(name)
            if keep and not self.mine[name]["hyperlink"]:
                self.link.setText(keep)
        else:
            self._set_profile(0)
        self._note()

    def _note(self):
        name = self.profile.currentData()
        self.note.setText(f"Profile \"{name}\": changes are saved back to it on OK." if name else
                          "New profile: saved to " + pf.FILE + " on OK (needs a manufacturer or part number).")

    def _fp_units(self):
        k = self.fp_unit.currentData()
        for sp in list(self.fp.values()) + [self.cl]:
            sp.setValue(sp.value() * self._fp_last / k)
        self._fp_last = k

    def footprint(self):
        """-> (w, h, d, mounting, rail_cl) in inches."""
        k = self.fp_unit.currentData()
        w, h, d = (self.fp[x].value() / k for x in ("fp_w", "fp_h", "fp_d"))
        return (w, h, d, self.mount.currentData(), self.cl.value() / k)

    # ---- placed-part helpers
    def _pick(self):
        dlg = TagPickerDialog(self, self.project, skip=self.ref)
        if dlg.exec() and dlg.chosen() is not None:
            row = dlg.chosen()
            self.tag.setText(row["tag"])
            self.link_tag = row["ref"].id

    def _pairs(self):
        d = QDialog(self); d.setWindowTitle("Pair numbering")
        first, step = QSpinBox(), QSpinBox()
        first.setRange(0, 9999); first.setValue(13)
        step.setRange(1, 999); step.setValue(10)
        f = QFormLayout(); f.addRow("First number", first); f.addRow("Step between pairs", step)
        f.addRow(QLabel("13 / 10 gives 13,14  23,24 ...   1 / 2 gives 1,2  3,4 ..."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        lay = QVBoxLayout(d); lay.addLayout(f); lay.addWidget(bb)
        if d.exec():
            for i, n in enumerate(bk.pair_numbers(self.table.rowCount(), first.value(), step.value())):
                self.table.item(i, 1).setText(n)

    # ---- results
    def values(self):
        """Block-level values. In make / block mode also the block's defaults (description, part number,
        manufacturer, hyperlink) and footprint."""
        t = self.type.currentData()
        v = {"name": self.name.text().strip(), "tag_prefix": self.prefix.text().strip(),
             "folder": self.folder.currentData(), "poles": self.poles.value(), "increment": self.inc.currentData(),
             "prefix_rule": self.rule.currentData(), "connector": int(t == "conn"), "exclude_bom": t == "xbom"}
        checked = {k for k, cb in self.show.items() if cb.isChecked()}
        have = set(bk.label_lines_of(self.block)) if self.block else set()
        lines = (have | checked) if self.part_mode else checked
        v["labels"] = tuple(k for k, _ in LINES if k in lines)
        v["label_pos"] = self.pos.currentData()
        v["header"] = self.hdr.currentData() or ""
        if t != "plate":
            v["mount"] = ""
        elif self.part_mode:
            v["mount"] = (self.block.mount or "rail")          # the part's own mounting lives in its profile
        else:
            v["mount"] = self.mount.currentData()
        if not self.part_mode:
            v.update(description=self.desc.text().strip(), part_number=self.part.text().strip(),
                     manufacturer=self.mfr.text().strip(), hyperlink=self.link.text().strip())
            if t == "plate":
                k = self.fp_unit.currentData()
                for key, sp in self.fp.items():
                    v[key] = round(sp.value() / k, 6)
                v["rail_cl"] = round(self.cl.value() / k, 6)
            if self.origin is not None:
                v["origin"] = self.origin.currentData()
        return v

    def part_result(self):
        """-> (tag, props) of the placed part. For type On back plate the footprint profile is created or
        updated (auto-saved); with no manufacturer or part number it is kept on the part itself."""
        b, old = self.block, self.ref.props
        keep = {k: v for k, v in old.items()
                if k not in ("description", "part_number", "manufacturer", "hyperlink", "hide", "tag_mode", "tag_link",
                             "exclude_bom", "fp_w", "fp_h", "fp_d", "fp_mount", "fp_cl", "profile")
                and not k.startswith("term")}
        for key, widget, default in (("description", self.desc, b.description), ("part_number", self.part, b.part_number),
                                     ("manufacturer", self.mfr, b.manufacturer), ("hyperlink", self.link, b.hyperlink)):
            if widget.text().strip() != default:
                keep[key] = widget.text().strip()
        if self.type.currentData() == "plate":
            w, h, d, mounting, cl = self.footprint()
            if w > 0 and h > 0:
                if self.mfr.text().strip() or self.part.text().strip():
                    sec = self.profile.currentData() or None
                    cur = self.mine.get(sec) if sec else None
                    if cur and (pf._norm(cur["part_number"]), pf._norm(cur["manufacturer"])) != \
                            (pf._norm(self.part.text()), pf._norm(self.mfr.text())):
                        sec = None                      # a different part number / manufacturer is a new profile
                    _, name = pf.save(self.mfr.text(), self.part.text(), self.link.text(), w, h, d, mounting, cl,
                                      section=sec, return_name=True, block=self.bname)
                    if name:
                        keep["profile"] = name
                else:
                    keep.update(fp_w=f"{w:g}", fp_h=f"{h:g}", fp_d=f"{d:g}", fp_mount=mounting, fp_cl=f"{cl:g}")
        lines_after = set(self.values()["labels"])
        hide = [k for k, _ in LINES if k in lines_after and not self.show[k].isChecked()]
        if hide:
            keep["hide"] = ",".join(hide)
        for i, s in enumerate(b.slots):
            name = self.table.item(i, 1).text().strip()
            if name != s.terminal:
                keep[f"term{i}"] = name
        tag = self.tag.text().strip()
        mode = old.get("tag_mode")
        if self.link_tag:
            mode, keep["tag_link"] = "linked", self.link_tag
        elif tag != self.ref.tag or mode == "linked":
            mode = "manual"
        if tag in ("", getattr(b, "tag_prefix", "") or "") and not self.link_tag:
            mode = None              # a blank tag, or just the prefix (PS), is automatic: Update tags numbers it (PS0111)
        if mode:
            keep["tag_mode"] = mode
        return tag, keep
