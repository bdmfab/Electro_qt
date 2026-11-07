"""Electro_qt main window: one tab per sheet, shared toolbars."""
from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QColor, QPixmap, QIcon, QUndoGroup
from PySide6.QtWidgets import (QApplication, QMainWindow, QToolBar, QComboBox, QLabel, QTabWidget,
                               QFileDialog, QMessageBox, QInputDialog, QColorDialog,
                               QFontComboBox, QDoubleSpinBox, QDockWidget)
from .. import model as m
from .. import save_project, load_project, fields
from ..geometry import walk
from ..templates import default_templates, sheet_from_template
from .scene import EditorScene, DEFAULT_BG
from .commands import LayerStateCmd
from .layers import LayerDialog
from .presets import PresetDialog
from .titledlg import TitleBlockDialog
from .textdlg import fill_color_combo
from .view import EditorView
from .properties import PropertiesPanel
from .library import LibraryPanel
from .blockdlg import BlockDialog, CopyBlockDialog
from .. import blocks as bk
from .. import numbering as nb
from .commands import EditCmd
from .. import xmlio
from .. import __version__
from .tools import TOOLS
from .items import aci_color

# toolbar / panel widths (pixels): change these to taste
LAYER_BOX_W = 210        # layer drop-down
STANDARDS_BOX_W = 120    # colour standard drop-down
STYLES_BOX_W = 85        # text style drop-down

TOOL_KEYS = {"select": "V", "line": "L", "rect": "R", "circle": "C", "arc": "A", "dot": "D", "text": "T",
             "trim": "X", "fillet": "F", "chamfer": "H", "multiline": "M", "slot": "S"}


def default_project() -> m.Project:
    p = m.Project("Untitled")
    p.layers["0"] = m.Layer("0", 7, "graphics")      # everything else is user-made (Layers...)
    p.templates.update(default_templates())
    p.info["date"] = fields.today()
    first = next(iter(p.templates.values()))
    p.add_sheet(sheet_from_template(first, 1, "Sheet 1"))
    return p


class MainWindow(QMainWindow):
    def __init__(self, project=None, path=None):
        super().__init__()
        self.path = path
        self.project = project or default_project()
        from ..libstore import LibraryStore
        self.store = LibraryStore(self._library_root())
        self.bg_color = DEFAULT_BG
        self._extra_dirty = False                  # changes that are not on an undo stack
        self.undo_group = QUndoGroup(self)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.props = PropertiesPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props)
        self.lib = LibraryPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.lib)
        self.lib.place.connect(self.on_place_block)
        self.lib.edit.connect(self.on_edit_block)
        self.lib.edit_geometry.connect(self.on_edit_block_geometry)
        self.lib.delete.connect(self.on_delete_block)
        self.lib.copy.connect(self.on_copy_block)
        self.lib.save_to_library.connect(self.on_save_to_library)
        self.lib.reload.connect(self.on_reload_library)
        self.lib.choose_root.connect(self.on_choose_library)
        self.lib.edit_files.connect(self.on_edit_library)
        self.lib.new_folder.connect(self.on_new_folder)
        self.lib.rename_folder.connect(self.on_rename_folder)
        self.lib.delete_folder.connect(self.on_delete_folder)
        self.lib.import_lib.connect(self.on_import_library)
        self.lib.export_lib.connect(self.on_export_library)
        self.coord = QLabel("")
        self.statusBar().addPermanentWidget(self.coord)
        self._build_ui()
        for pg in sorted(self.project.sheets):
            self._add_tab(self.project.sheets[pg])
        self.tabs.setTabsClosable(True)              # only block-editing tabs keep their close button
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self._tab_buttons()
        self.tabs.currentChanged.connect(self._tab_changed)
        self._tab_changed(self.tabs.currentIndex())
        self._title()
        self.resize(1300, 880)

    # ------------------------------------------------------------ current tab
    @property
    def view(self):
        return self.tabs.currentWidget()

    @property
    def scene_(self):
        v = self.tabs.currentWidget()
        return v.scene() if v is not None else None

    def _refresh_xrefs(self):
        for sc in self._sheet_scenes():
            sc.refresh_xrefs()

    def on_add_connector_block(self):
        import copy
        blk = bk.default_connector_block()
        if blk.name in self.store.blocks:
            QMessageBox.information(self, "Off-page connector", "The library already has a block named GOTO."); return
        self.project.blocks.setdefault(blk.name, copy.deepcopy(blk))
        try:
            self.store.save_block(blk)
        except OSError as ex:
            QMessageBox.warning(self, "Library", f"Could not write the library file:\n{ex}")
        self._dirty_library()
        self.statusBar().showMessage("Added block GOTO to the library. Place it at the end of a wire on each sheet, "
                                     "giving both the same name.", 10000)

    def _sheet_scenes(self):
        return [sc for sc in self._scenes() if not sc.block_edit]

    def _tab_buttons(self):
        from PySide6.QtWidgets import QTabBar
        bar = self.tabs.tabBar()
        self.tabs.setTabsClosable(False)             # re-create the buttons, then keep them on block tabs only
        self.tabs.setTabsClosable(True)
        for i in range(self.tabs.count()):
            if not self.tabs.widget(i).scene().block_edit:
                bar.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)

    def _scenes(self):
        return [self.tabs.widget(i).scene() for i in range(self.tabs.count())]

    def _tab_label(self, sheet):
        return f"{sheet.page:02d}  {sheet.title}".rstrip()

    def _add_tab(self, sheet):
        sc = EditorScene(self.project, sheet)
        v = EditorView(sc)
        self.undo_group.addStack(sc.undo)
        sc.status.connect(lambda s, sc=sc: self.coord.setText(s) if sc is self.scene_ else None)
        sc.prompt.connect(lambda s, sc=sc: self.statusBar().showMessage(s) if sc is self.scene_ else None)
        sc.tool_changed.connect(lambda n, sc=sc: self._follow_tool(sc, n))
        sc.layers_changed.connect(lambda sc=sc: self._layers_changed(sc))
        sc.blocks_changed.connect(lambda sc=sc: self._blocks_changed(sc))
        sc.block_made.connect(self._block_made)
        sc.edit_block_requested.connect(self.on_edit_block_geometry)
        sc.undo.indexChanged.connect(lambda _i: self._refresh_xrefs())
        sc.folder_choices = list(self.store.folders)
        sc.undo.cleanChanged.connect(self._title)
        i = self.tabs.addTab(v, self._tab_label(sheet))
        self._tab_buttons()
        self._sync(sc)
        return i

    def _tab_changed(self, i):
        sc = self.scene_
        if sc is None:
            return
        self.undo_group.setActiveStack(sc.undo)
        self.props.attach(sc)
        self._sync(sc)
        self._follow_tool(sc, sc.tool.name)
        self.statusBar().showMessage(sc.tool.hint())
        self.view.setFocus()

    def _sync(self, sc=None):
        """Toolbar state is the source of truth; push it into a scene."""
        sc = sc or self.scene_
        if sc is None:
            return
        s = sc.snap_settings
        s.ortho, s.grid = self.act_ortho.isChecked(), self.act_snap.isChecked()
        s.end = s.mid = s.center = s.quad = self.act_osnap.isChecked()
        sc.show_grid = self.act_grid.isChecked()
        sc.current_layer = self.layer_box.currentData() or "0"
        sc.preset_name = self.preset_box.currentData()
        sc.text_style_name = self.tstyle_box.currentData() or "Default"
        if sc.bg.name() != QColor(self.bg_color).name():
            sc.set_background(self.bg_color)
        sc.update()

    def _title(self, *_):
        dirty = self._extra_dirty or any(not sc.undo.isClean() for sc in self._scenes())
        self.setWindowTitle(f"Electro_qt - {self.path or 'unsaved'}{' *' if dirty else ''}")

    # ------------------------------------------------------------------ UI
    def _act(self, text, slot=None, shortcut=None, checkable=False, checked=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
        if slot:
            (a.toggled if checkable else a.triggered).connect(slot)
        return a

    def _on_scene(self, fn):
        """Slot that runs fn(scene) on the current sheet (ignores the 'checked' argument)."""
        return lambda _=False: fn(self.scene_) if self.scene_ is not None else None

    def _build_ui(self):
        S = QKeySequence.StandardKey
        fm = self.menuBar().addMenu("&File")
        fm.addAction(self._act("&New", self.on_new, S.New))
        fm.addAction(self._act("&Open...", self.on_open, S.Open))
        fm.addAction(self._act("&Save", self.on_save, S.Save))
        fm.addAction(self._act("Save &As...", self.on_save_as, S.SaveAs))
        fm.addSeparator()
        ex = fm.addMenu("&Export")
        ex.addAction(self._act("&Wire list (CSV)...", lambda: self.on_export("wires")))
        ex.addAction(self._act("Wire &labels (CSV)...", lambda: self.on_export("labels")))
        ex.addAction(self._act("&Bill of materials (CSV)...", lambda: self.on_export("bom")))
        fm.addSeparator()
        fm.addAction(self._act("&Quit", self.close, S.Quit))

        em = self.menuBar().addMenu("&Edit")
        self.undo_act = self.undo_group.createUndoAction(self, "Undo")
        self.undo_act.setShortcut(S.Undo)
        self.redo_act = self.undo_group.createRedoAction(self, "Redo")
        self.redo_act.setShortcut(S.Redo)
        em.addAction(self.undo_act); em.addAction(self.redo_act)
        em.addSeparator()
        em.addAction(self._act("&Copy", self._on_scene(lambda s: s.copy_selected()), S.Copy))
        em.addAction(self._act("Cu&t", self._on_scene(lambda s: s.cut_selected()), S.Cut))
        em.addAction(self._act("&Paste", self._on_scene(lambda s: s.paste()), S.Paste))
        em.addAction(self._act("&Delete", self._on_scene(lambda s: s.delete_selected()), S.Delete))
        em.addAction(self._act("Select &all", self._on_scene(
            lambda s: [i.setSelected(True) for i in s.items() if hasattr(i, "entity_id") and i.parentItem() is None]),
            S.SelectAll))
        em.addAction(self._act("Make &block...", self._on_scene(lambda s: s.make_block_dialog()), "Ctrl+B"))
        em.addAction(self._act("E&xplode block", self._on_scene(lambda s: s.explode_blocks()), "Ctrl+Shift+X"))
        em.addAction(self._act("&Array...", self._on_scene(lambda s: s.array_dialog()), "Ctrl+Shift+A"))
        em.addSeparator()
        em.addAction(self._act("Rotate 90° counter-clockwise", self._on_scene(lambda s: s.rotate_selected(90)), "Ctrl+R"))
        em.addAction(self._act("Rotate 90° clockwise", self._on_scene(lambda s: s.rotate_selected(-90)), "Ctrl+Shift+R"))
        em.addAction(self._act("Mirror left-right", self._on_scene(lambda s: s.mirror_selected("v")), "Ctrl+M"))
        em.addAction(self._act("Mirror top-bottom", self._on_scene(lambda s: s.mirror_selected("h")), "Ctrl+Shift+M"))

        sm = self.menuBar().addMenu("&Sheet")
        sm.addAction(self._act("&Add sheet from template...", self.on_add_sheet))
        sm.addAction(self._act("&Delete this sheet...", self.on_delete_sheet))
        sm.addSeparator()
        sm.addAction(self._act("&Letter rules...", self.on_letter_rules))
        sm.addAction(self._act("Update &wire numbers", self.on_update_numbers, "F5"))
        sm.addAction(self._act("Update device &tags...", self.on_update_tags))
        sm.addSeparator()
        sm.addAction(self._act("&Title block...", self.on_title_block))
        sm.addAction(self._act("Title block &image...", self.on_logo))
        sm.addAction(self._act("&Remove title block image", self.on_remove_logo))

        vm = self.menuBar().addMenu("&View")
        vm.addAction(self._act("Zoom &extents", lambda _=False: self.view.zoom_extents(), "Home"))
        vm.addAction(self._act("Grid &divisions...", self.on_grid_divisions))
        lm = self.menuBar().addMenu("&Library")
        lm.addAction(self._act("Add off-page &connector block", self.on_add_connector_block))
        lm.addAction(self._act("Close &block edit tab", lambda: self._close_tab(self.tabs.currentIndex())))
        lm.addAction(self._act("&Apply block edit", lambda: self.on_apply_block_edit(), "Ctrl+Shift+B"))
        lm.addAction(self._act("&Update project blocks from library...", self.on_update_from_library))
        lm.addAction(self._act("&Reload library", self.on_reload_library))
        lm.addSeparator()
        lm.addAction(self._act("Library &folder...", self.on_choose_library))
        lm.addAction(self._act("Use the &default library folder", self.on_default_library))

        vm.addAction(self.props.toggleViewAction())
        vm.addAction(self.lib.toggleViewAction())
        bm = vm.addMenu("&Background")
        for label, col in (("Dark", DEFAULT_BG), ("Black", "#000000"), ("Gray", "#6b6f76"),
                           ("Light", "#d9dbe0"), ("White", "#ffffff")):
            bm.addAction(self._act(label, lambda _=False, c=col: self._set_bg(c)))
        bm.addAction(self._act("Custom...", self.on_custom_bg))

        hm = self.menuBar().addMenu("&Help")
        hm.addAction(self._act("&About Electro_qt", self.on_about))

        # ---- first toolbar: tools and snaps
        tb = QToolBar("Tools"); tb.setMovable(False)
        self.addToolBar(tb)
        grp = QActionGroup(self); grp.setExclusive(True)
        self.tool_actions = {}
        for name in TOOLS:
            if name not in TOOL_KEYS:          # resize / paste: started from menus, not the toolbar
                continue
            a = self._act(f"{name.capitalize()} ({TOOL_KEYS[name]})", None, TOOL_KEYS[name], True, name == "select")
            a.toggled.connect(lambda on, n=name: on and self.scene_ is not None
                              and self.scene_.tool.name != n and self.scene_.request_tool(n))
            grp.addAction(a); tb.addAction(a); self.tool_actions[name] = a
        tb.addSeparator()
        self.act_ortho = self._act("Ortho (F8)", lambda _on: self._sync(), "F8", True, True)
        self.act_snap = self._act("Snap grid (F9)", lambda _on: self._sync(), "F9", True, True)
        self.act_osnap = self._act("Object snap (F3)", lambda _on: self._sync(), "F3", True, True)
        self.act_grid = self._act("Grid (F7)", lambda _on: self._sync(), "F7", True, True)
        from PySide6.QtWidgets import QToolButton
        for a in (self.act_ortho, self.act_snap, self.act_osnap, self.act_grid):
            btn = QToolButton(); btn.setDefaultAction(a); btn.setAutoRaise(True)       # next to the X Y readout
            self.statusBar().addPermanentWidget(btn)

        # ---- second toolbar row: layer, colour standard, text
        tb2 = QToolBar("Properties"); tb2.setMovable(False)
        self.addToolBarBreak()
        self.addToolBar(tb2)
        tb2.addAction(self._act("Layers...", self.on_layers, "Ctrl+L"))
        self.layer_box = QComboBox(); self.layer_box.setToolTip("Layer new objects are drawn on")
        self.layer_box.setMinimumWidth(LAYER_BOX_W)
        self.layer_box.currentIndexChanged.connect(self._ui_changed)
        tb2.addWidget(self.layer_box)
        tb2.addSeparator()

        tb2.addAction(self._act("Standards...", self.on_presets))
        self.preset_box = QComboBox(); self.preset_box.setToolTip("Color standard for the Multiline tool (M)")
        self.preset_box.setMinimumWidth(STANDARDS_BOX_W)
        self.preset_box.setMaximumWidth(STANDARDS_BOX_W)
        self.preset_box.currentIndexChanged.connect(self._ui_changed)
        tb2.addWidget(self.preset_box)
        tb2.addSeparator()

        tb2.addAction(self._act("Styles...", self.on_text_styles))
        self.tstyle_box = QComboBox(); self.tstyle_box.setToolTip("Style for new text")
        self.tstyle_box.setMinimumWidth(STYLES_BOX_W)
        self.tstyle_box.setMaximumWidth(STYLES_BOX_W)
        self.tstyle_box.currentIndexChanged.connect(self._ui_changed)
        tb2.addWidget(self.tstyle_box)

        self.refresh_layers()
        self.refresh_presets()
        self.refresh_text_styles()
        self._refresh_library()
        try:
            saved = QSettings("Electro_qt", "Electro_qt").value("background")
            if saved:
                self.bg_color = str(saved)
        except Exception:        # noqa: BLE001 - settings are a convenience only
            pass

    def _ui_changed(self, *_):
        self._sync()
        if self.view is not None:
            self.view.setFocus()

    def _follow_tool(self, sc, name):
        if sc is not self.scene_:
            return
        a = self.tool_actions.get(name)
        if a is not None and not a.isChecked():
            a.blockSignals(True); a.setChecked(True); a.blockSignals(False)

    def _layers_changed(self, origin):
        for sc in self._scenes():
            if sc is not origin:
                sc.rebuild()
        self.refresh_layers()

    # ------------------------------------------------------------ appearance
    def _set_bg(self, color, remember=True):
        self.bg_color = str(color)
        for sc in self._scenes():
            sc.set_background(self.bg_color)
        self.refresh_layers()
        if remember:
            try:
                QSettings("Electro_qt", "Electro_qt").setValue("background", self.bg_color)
            except Exception:    # noqa: BLE001
                pass

    def on_about(self):
        QMessageBox.about(self, "About Electro_qt",
                          f"<b>Electro_qt</b><br>Version {__version__}<br>"
                          "2D CAD for industrial electrical schematics")

    def on_custom_bg(self):
        c = QColorDialog.getColor(QColor(self.bg_color), self, "Background color")
        if c.isValid():
            self._set_bg(c.name())

    # ------------------------------------------------------------ layers / standards
    def refresh_layers(self):
        cur = self.layer_box.currentData()
        self.layer_box.blockSignals(True)
        self.layer_box.clear()
        for name, lay in self.project.layers.items():
            pm = QPixmap(14, 14); pm.fill(aci_color(lay.color))
            self.layer_box.addItem(QIcon(pm), name + ("  (wire)" if lay.kind == "wire" else ""), name)
        self.layer_box.setCurrentIndex(max(0, self.layer_box.findData(cur)))
        self.layer_box.blockSignals(False)
        self._sync()

    def refresh_presets(self):
        cur = self.preset_box.currentData()
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        for name, p in self.project.multiline_presets.items():
            self.preset_box.addItem(f"{name}", name)
        self.preset_box.setCurrentIndex(max(0, self.preset_box.findData(cur)))
        self.preset_box.blockSignals(False)
        self._sync()

    def on_layers(self):
        sc = self.scene_
        used = {e.style.layer for s in self.project.sheets.values() for e in walk(s.entities)}
        dlg = LayerDialog(self, self.project.layers, used, self.project.prefix_rules, self.project.schemes)
        if not dlg.exec():
            return
        new_layers, renames = dlg.result_layers()
        self.project.schemes = dlg.result_schemes()
        before = sc.capture_layer_state()
        self.project.layers.clear()
        self.project.layers.update(new_layers)
        for s in self.project.sheets.values():
            for e in walk(s.entities):
                e.style.layer = renames.get(e.style.layer, e.style.layer)
                if isinstance(e, m.Line):
                    if sc.is_numbered_wire(e.style.layer):
                        e.number = e.number or m.WireNumber("auto", "")
                    else:
                        e.number = None
        for s2 in self._scenes():
            s2.current_layer = renames.get(s2.current_layer, s2.current_layer)
        after = sc.capture_layer_state()
        sc.undo.push(LayerStateCmd(sc, before, after))
        self.view.setFocus()

    def refresh_text_styles(self):
        cur = self.tstyle_box.currentData()
        self.tstyle_box.blockSignals(True)
        self.tstyle_box.clear()
        for name in self.project.text_styles:
            self.tstyle_box.addItem(name, name)
        self.tstyle_box.setCurrentIndex(max(0, self.tstyle_box.findData(cur)))
        self.tstyle_box.blockSignals(False)
        self._sync()
        self.props.refresh()

    def on_text_styles(self):
        from .styledlg import TextStylesDialog
        old = {k: (v.font, v.height, v.color, v.align) for k, v in self.project.text_styles.items()}
        dlg = TextStylesDialog(self, self.project.text_styles)
        if not dlg.exec():
            return
        self.project.text_styles = dict(dlg.result_styles())
        self.project.text_styles.setdefault("Default", m.TextStyle("Default"))
        new = {k: (v.font, v.height, v.color, v.align) for k, v in self.project.text_styles.items()}
        changed = {k for k in old if new.get(k) != old[k]}      # edited or deleted
        if changed:
            self.scene_.restyle_text(changed)
            self._refresh_all()
            for sc in self._scenes():        # earlier undo steps would restore stale text looks
                sc.undo.clear()
            self._extra_dirty = True
            self._title()
        self.refresh_text_styles()
        self.view.setFocus()

    # ------------------------------------------------------------ blocks / shared library
    def _library_root(self):
        try:
            v = QSettings("Electro_qt", "Electro_qt").value("library_root")
            if v:
                return str(v)
        except Exception:        # noqa: BLE001 - settings are a convenience only
            pass
        return None              # -> the 'blocks' folder next to run_electro.py

    def _blocks_changed(self, origin):
        for sc in self._scenes():
            if sc is not origin:
                sc.rebuild()
        self._refresh_library()
        self.props.refresh()

    def _refresh_library(self):
        st = self.store
        for sc in self._scenes():
            sc.folder_choices = list(st.folders)
        self.lib.refresh(st.blocks, st.folders,
                         [n for n in sorted(self.project.blocks) if n not in st.blocks], str(st.root))

    def _dirty_library(self):
        self._refresh_library()
        self._extra_dirty = True
        self._title()

    def _block_made(self, blk):
        """A block was just made from a selection: keep a copy in the shared library."""
        import copy
        try:
            self.store.save_block(copy.deepcopy(blk))
        except OSError as ex:
            QMessageBox.warning(self, "Library", f"The block is in this project but could not be saved "
                                                  f"to the shared library:\n{ex}")
        self._refresh_library()

    def _find_block(self, name):
        return self.store.blocks.get(name) or self.project.blocks.get(name)

    def on_place_block(self, name):
        import copy
        sc = self.scene_
        if sc is None:
            return
        if name not in self.project.blocks:              # first use in this project: copy it in
            src = self.store.blocks.get(name)
            if src is None:
                return
            self.project.blocks[name] = copy.deepcopy(src)
            self._refresh_library()
            self._extra_dirty = True
            self._title()
        sc.place_block_name = name
        sc.request_tool("place")
        self.view.setFocus()

    def on_edit_block(self, name):
        import copy
        blk = self._find_block(name)
        if blk is None:
            return
        dlg = BlockDialog(self, blk, folders=self.store.folders, rules=self.project.prefix_rules)
        if not dlg.exec():
            return
        v = dlg.values()
        for k in ("description", "part_number", "manufacturer", "hyperlink", "tag_prefix",
                  "poles", "increment", "prefix_rule", "connector"):
            setattr(blk, k, v[k])
        bk.rebuild_label(blk, v["labels"], v["label_pos"])
        if name in self.store.blocks:
            blk.folder = v["folder"]
            try:
                self.store.save_block(blk)
            except OSError as ex:
                QMessageBox.warning(self, "Library", f"Could not write the library file:\n{ex}")
            if name in self.project.blocks:              # this project's copy follows
                self.project.blocks[name] = copy.deepcopy(blk)
        self._refresh_all()
        self._dirty_library()

    # ------------------------------------------------------------ edit a block's geometry
    def on_edit_block_geometry(self, name):
        blk = self._find_block(name)
        if blk is None:
            return
        for i in range(self.tabs.count()):
            sc = self.tabs.widget(i).scene()
            if sc.block_edit and sc.block_edit["name"] == name:
                self.tabs.setCurrentIndex(i); return
        i = self._add_tab(bk.edit_sheet(blk))
        sc = self.tabs.widget(i).scene()
        sc.block_edit = {"name": name}
        sc.rebuild()
        self.tabs.setTabText(i, f"Block: {name}")
        self._tab_buttons()
        self.tabs.setCurrentIndex(i)
        self.tabs.widget(i).zoom_extents()
        self.statusBar().showMessage(f"Editing block {name}: draw / move / delete, add slots with the Slot tool "
                                     "(magenta cross = block origin). Library > Apply block edit saves it.", 12000)

    def on_apply_block_edit(self, sc=None):
        import copy
        sc = sc or self.scene_
        if sc is None or not sc.block_edit:
            QMessageBox.information(self, "Apply block edit", "Open a block first (Library > right-click a block > Edit block)."); return False
        name = sc.block_edit["name"]
        old = self._find_block(name)
        if old is None:
            QMessageBox.warning(self, "Apply block edit", f"Block {name} no longer exists."); return False
        new = bk.block_from_sheet(old, sc.sheet)
        bk.capture_layers(self.project, new)
        if name in self.store.blocks:
            try:
                self.store.save_block(copy.deepcopy(new))
            except OSError as ex:
                QMessageBox.warning(self, "Library", f"Could not write the library file:\n{ex}")
        if name in self.project.blocks or name not in self.store.blocks:
            self.project.blocks[name] = copy.deepcopy(new)
        sc.undo.setClean()
        self._refresh_all()
        self._dirty_library()
        self.statusBar().showMessage(f"Block {name} updated ({len(new.slots)} slot(s)); placed copies follow", 8000)
        return True

    def _close_tab(self, i):
        sc = self.tabs.widget(i).scene()
        if not sc.block_edit:
            self.statusBar().showMessage("Only block-edit tabs can be closed.", 4000)
            return
        if not sc.undo.isClean():
            B = QMessageBox.StandardButton
            r = QMessageBox.question(self, "Block edit", f"Save the changes to block {sc.block_edit['name']}?",
                                     B.Save | B.Discard | B.Cancel)
            if r == B.Cancel or (r == B.Save and not self.on_apply_block_edit(sc)):
                return
        self.props.attach(None)
        self.undo_group.removeStack(sc.undo)
        self.tabs.removeTab(i)

    def on_delete_block(self, name):
        used = [pg for pg, sh in self.project.sheets.items()
                if any(isinstance(e, m.BlockRef) and e.block == name for e in walk(sh.entities))]
        if used:
            QMessageBox.information(self, "Delete block",
                                    f"'{name}' is placed on sheet(s) {', '.join(f'{p:02d}' for p in used)}. "
                                    "Delete those first.")
            return
        where = "the shared library" if name in self.store.blocks else "this project"
        if QMessageBox.question(self, "Delete block", f"Remove '{name}' from {where}?") \
                != QMessageBox.StandardButton.Yes:
            return
        if name in self.store.blocks:
            self.store.delete_block(name)
        self.project.blocks.pop(name, None)
        self._dirty_library()

    def on_copy_block(self, name):
        import copy
        src = self._find_block(name)
        if src is None:
            return
        dlg = CopyBlockDialog(self, name, self.store.folders, src.folder if name in self.store.blocks else "")
        if not dlg.exec():
            return
        new, folder = dlg.values()
        if not new or new in self.store.blocks or new in self.project.blocks:
            QMessageBox.warning(self, "Copy block", "Give the copy a name that is not already in use.")
            return
        b = copy.deepcopy(src)
        b.name, b.folder = new, folder
        for e in walk(b.entities):
            e.id = m.new_id()
        try:
            self.store.save_block(b)
        except OSError as ex:
            QMessageBox.warning(self, "Library", f"Could not write the library file:\n{ex}"); return
        self._dirty_library()

    def on_save_to_library(self, name):
        import copy
        blk = self.project.blocks.get(name)
        if blk is None or name in self.store.blocks:
            return
        folder, ok = QInputDialog.getItem(self, "Save to shared library", "Folder:",
                                          ["(top level)"] + self.store.folders, 0, False)
        if not ok:
            return
        b = copy.deepcopy(blk)
        b.folder = "" if folder == "(top level)" else folder
        try:
            self.store.save_block(b)
        except OSError as ex:
            QMessageBox.warning(self, "Library", f"Could not write the library file:\n{ex}"); return
        self._dirty_library()

    def on_update_from_library(self):
        """Replace this project's copies of blocks with the library's current versions."""
        import copy
        import xml.etree.ElementTree as ET

        def sig(b):
            c = copy.deepcopy(b); c.folder = ""
            return ET.tostring(xmlio.block_to_xml(c))
        diff = [n for n in self.project.blocks if n in self.store.blocks
                and sig(self.project.blocks[n]) != sig(self.store.blocks[n])]
        if not diff:
            QMessageBox.information(self, "Update from library", "This project's blocks already match the library.")
            return
        r = QMessageBox.question(self, "Update from library",
                                 "Replace this project's copy of these blocks with the library version? "
                                 "Placed parts change to match.\n\n" + "\n".join(sorted(diff)[:30]))
        if r != QMessageBox.StandardButton.Yes:
            return
        for n in diff:
            self.project.blocks[n] = copy.deepcopy(self.store.blocks[n])
            bk.ensure_layers(self.project, self.project.blocks[n])
        self.refresh_layers()
        self._refresh_all()
        self._dirty_library()

    def on_choose_library(self):
        from ..libstore import LibraryStore
        d = QFileDialog.getExistingDirectory(self, "Shared block library folder", str(self.store.root))
        if d:
            self._set_library(d)

    def on_default_library(self):
        self._set_library(None)

    def _set_library(self, root):
        from ..libstore import LibraryStore
        try:
            QSettings("Electro_qt", "Electro_qt").setValue("library_root", root or "")
        except Exception:        # noqa: BLE001
            pass
        self.store = LibraryStore(root)
        self._refresh_library()
        self._library_status()

    def _library_status(self):
        n = len(self.store.errors)
        self.statusBar().showMessage(f"Library: {self.store.root}  ({len(self.store.blocks)} block(s)"
                                     + (f", {n} file(s) could not be read" if n else "") + ")")

    def on_edit_library(self):
        """Open the library folder in the file manager so blocks can be copied, pasted and
        dragged in; OK reloads the library, Cancel leaves it as it is."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        root = str(self.store.root)
        os.makedirs(root, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))
        box = QMessageBox(QMessageBox.Icon.Question, "Edit library",
                          f"The library folder is open:\n{root}\n\nCopy, paste, drag and drop block files "
                          "(.eqblock) and folders there.\n\nOK reloads the library; Cancel leaves it as it is.",
                          QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel, self)
        if box.exec() == QMessageBox.StandardButton.Ok:
            self.on_reload_library()

    def on_reload_library(self):
        self.store.reload()
        self._refresh_library()
        self._library_status()
        if self.store.errors:
            QMessageBox.warning(self, "Library", "Some library files were skipped:\n\n"
                                + "\n".join(self.store.errors[:20]))

    def on_new_folder(self, parent):
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:" + (f"\n(inside {parent})" if parent else ""))
        name = name.strip().replace("/", "-")
        if ok and name:
            try:
                self.store.new_folder(f"{parent}/{name}" if parent else name)
            except OSError as ex:
                QMessageBox.warning(self, "Library", str(ex)); return
            self._refresh_library()

    def on_rename_folder(self, path):
        leaf = path.rsplit("/", 1)[-1]
        name, ok = QInputDialog.getText(self, "Rename folder", "New name:", text=leaf)
        name = name.strip().replace("/", "-")
        if not ok or not name or name == leaf:
            return
        new = (path.rsplit("/", 1)[0] + "/" + name) if "/" in path else name
        try:
            self.store.rename_folder(path, new)
        except (ValueError, OSError) as ex:
            QMessageBox.warning(self, "Rename folder", str(ex)); return
        self._refresh_library()

    def on_delete_folder(self, path):
        r = QMessageBox.question(self, "Delete folder",
                                 f"Delete the folder '{path}'? Blocks inside move up one level.")
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_folder(path)
        except (ValueError, OSError) as ex:
            QMessageBox.warning(self, "Delete folder", str(ex)); return
        self._refresh_library()

    def on_export_library(self, kind="all", value=""):
        import xml.etree.ElementTree as ET
        st = self.store
        if kind == "block":
            b = self._find_block(value)
            blocks, folders, strip = ([b] if b else []), [], None
        elif kind == "folder":
            inside = lambda f: f == value or f.startswith(value + "/")
            blocks = [b for b in st.blocks.values() if inside(b.folder)]
            folders = [f for f in st.folders if inside(f)]
            strip = value.rsplit("/", 1)[0] if "/" in value else ""
        else:
            blocks, folders, strip = list(st.blocks.values()), list(st.folders), ""
        if not blocks and not folders:
            QMessageBox.information(self, "Export library", "There is nothing to export."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export library", "", "Electro_qt library (*.eqlib)")
        if not path:
            return

        def rel(f):                                     # folder path as stored in the file
            if strip is None:
                return ""
            return f[len(strip):].lstrip("/") if strip and f.startswith(strip) else f
        root = ET.Element("library")
        for f in folders:
            ET.SubElement(root, "folder", path=rel(f))
        for b in blocks:
            el = xmlio.block_to_xml(b)
            el.set("folder", rel(b.folder) if kind != "block" else "")
            root.append(el)
        ET.indent(root)
        ET.ElementTree(root).write(path if path.endswith(".eqlib") else path + ".eqlib",
                                   encoding="utf-8", xml_declaration=True)
        self.statusBar().showMessage(f"Exported {len(blocks)} block(s)")

    def on_import_library(self, folder=""):
        import xml.etree.ElementTree as ET
        path, _ = QFileDialog.getOpenFileName(self, "Import library", "", "Electro_qt library (*.eqlib)")
        if not path:
            return

        def join(a, b):
            return "/".join(x for x in (a, b) if x)
        try:
            root = ET.parse(path).getroot()
            added = renamed = 0
            for f in root.findall("folder"):
                full = join(folder, f.get("path", ""))
                if full:
                    self.store.new_folder(full)
            for el in root.findall("block"):
                b = xmlio.block_from_xml(el)
                b.folder = join(folder, b.folder)
                new = self.store.unique_name(b.name, also=self.project.blocks)
                if new != b.name:
                    renamed += 1
                    b.name = new
                self.store.save_block(b)
                added += 1
        except Exception as ex:            # noqa: BLE001 - surface any file problem
            QMessageBox.critical(self, "Import failed", str(ex)); return
        self._refresh_library()
        QMessageBox.information(self, "Import library",
                                f"{added} block(s) added" + (f"; {renamed} renamed because the name was in use." if renamed else "."))

    def on_export(self, kind):
        from .. import reports
        from PySide6.QtWidgets import QFileDialog
        if kind == "bom":
            header, rows = reports.bom(self.project); title, stem = "Bill of materials", "bom"
        elif kind == "labels":
            header, rows = reports.LABEL_HEADER, reports.wire_labels(self.project); title, stem = "Wire labels", "wire_labels"
        else:
            header, rows = reports.WIRE_HEADER, reports.wire_list(self.project); title, stem = "Wire list", "wire_list"
        if not rows:
            QMessageBox.information(self, title, "Nothing to export yet." + (
                "" if kind == "bom" else " Number the wires first (Sheet > Update wire numbers)."))
            return
        base = os.path.splitext(self.path)[0] if getattr(self, "path", None) else stem
        path, _ = QFileDialog.getSaveFileName(self, f"Export {title}", f"{base}_{stem}.csv" if base != stem else f"{stem}.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        try:
            reports.write_csv(path, header, rows)
        except OSError as e:
            QMessageBox.warning(self, title, f"Could not write the file:\n{e}"); return
        self.statusBar().showMessage(f"{title}: {len(rows)} row(s) written to {path}", 8000)

    def on_letter_rules(self):
        from .ruledlg import RulesDialog
        dlg = RulesDialog(self, self.project.prefix_rules)
        if dlg.exec():
            self.project.prefix_rules = dlg.rules()
            self._extra_dirty = True
            self._title()

    def on_update_numbers(self):
        rep = nb.update(self.project)
        n = 0
        for sc in self._sheet_scenes():
            lst = rep.changes.get(sc.sheet.page, [])
            if lst:
                sc.undo.push(EditCmd(sc, "Update wire numbers", modify=[(l, {"number": num}) for l, num in lst]))
                n += len(lst)
        self.statusBar().showMessage(f"Wire numbers: {rep.numbered} of {rep.nets} wire(s) numbered, {n} line(s) changed")
        if rep.warnings:
            QMessageBox.warning(self, "Wire number warnings", "\n".join(rep.warnings[:30])
                                + ("\n..." if len(rep.warnings) > 30 else ""))
        if rep.nets == 0:
            QMessageBox.information(self, "Wire numbers",
                                    "No numbered wire lines were found. Wires must be on a wire layer with "
                                    "'numbered' ticked (Layers...), and a wire must be marked: right-click > Mark wire.")

    def on_update_tags(self):
        r = QMessageBox.question(self, "Update device tags",
                                 "Recompute all automatic device tags (prefix + page + zone, letter on a clash)?\n"
                                 "Tags you typed yourself are kept. This clears undo history.")
        if r != QMessageBox.StandardButton.Yes:
            return
        n = bk.update_tags(self.project)
        self._refresh_all()
        for sc in self._scenes():
            sc.undo.clear()
        self._extra_dirty = self._extra_dirty or n > 0
        self._title()
        self.statusBar().showMessage(f"{n} tag(s) changed")
        broken = bk.broken_links(self.project)
        if broken:
            QMessageBox.warning(self, "Tag links",
                                "These parts take their tag from a block that no longer exists (tag kept as is):\n\n"
                                + "\n".join(f"{r.block} on sheet {pg:02d}, tag {r.tag}" for pg, r in broken[:25]))
        dups = bk.duplicate_tags(self.project)
        if dups:
            lines = [f"{t}: " + ", ".join(f"{r['block']} ({r['page']:02d}-{r['zone']})" for r in rows)
                     for t, rows in sorted(dups.items())]
            QMessageBox.information(self, "Tags used more than once",
                                    "These tags appear on more than one part. That is expected for a coil and its "
                                    "contacts; check the rest:\n\n" + "\n".join(lines[:25]))

    def on_presets(self):
        dlg = PresetDialog(self, self.project.multiline_presets, list(self.project.layers))
        if dlg.exec():
            self.project.multiline_presets = dict(dlg.result_presets())
            self._extra_dirty = True
            self.refresh_presets()
            self._title()
        self.view.setFocus()

    def on_grid_divisions(self):
        n, ok = QInputDialog.getInt(self, "Grid divisions",
                                    "Grid lines between the major (row-centre) lines\n(0 = none, 1 = one line halfway):",
                                    self.scene_.sheet.grid_divisions, 0, 9)
        if ok:
            self.scene_.apply_grid_divisions(n)
            self._extra_dirty = True
            self._title()

    # ------------------------------------------------------------ sheets
    def _refresh_all(self):
        for sc in self._scenes():
            sc.rebuild()

    def on_add_sheet(self):
        names = list(self.project.templates)
        if not names:
            self.project.templates.update(default_templates())
            names = list(self.project.templates)
        name, ok = QInputDialog.getItem(self, "Add sheet", "Template:", names, 0, False)
        if not ok:
            return
        page = max(self.project.sheets, default=0) + 1
        if page > 99:
            QMessageBox.warning(self, "Add sheet", "A project holds at most 99 sheets."); return
        sheet = sheet_from_template(self.project.templates[name], page, f"Sheet {page}")
        self.project.add_sheet(sheet)
        i = self._add_tab(sheet)
        self.tabs.setCurrentIndex(i)
        self._refresh_all()                        # "01 OF 02" etc. on every sheet
        self._extra_dirty = True
        self._title()

    def on_delete_sheet(self):
        if len(self.project.sheets) <= 1:
            QMessageBox.information(self, "Delete sheet", "A project needs at least one sheet."); return
        sc = self.scene_
        if sc.block_edit:
            QMessageBox.information(self, "Delete sheet", "This tab is editing a block, not a sheet."); return
        r = QMessageBox.question(self, "Delete sheet",
                                 f"Delete sheet {sc.sheet.page:02d} and everything on it? This cannot be undone.")
        if r != QMessageBox.StandardButton.Yes:
            return
        i = self.tabs.currentIndex()
        self.props.attach(None)
        self.undo_group.removeStack(sc.undo)
        del self.project.sheets[sc.sheet.page]
        self.tabs.removeTab(i)
        self._refresh_all()
        self._extra_dirty = True
        self._title()

    def on_logo(self):
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        from PySide6.QtGui import QImage
        path, _ = QFileDialog.getOpenFileName(self, "Title block image", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Title block image", "That file could not be read as an image."); return
        if max(img.width(), img.height()) > 1200:          # keep the project file small
            img = img.scaled(1200, 1200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        self.project.assets["logo.png"] = bytes(ba)
        self.project.info["logo"] = "logo.png"
        self._refresh_all()
        self._extra_dirty = True
        self._title()

    def on_remove_logo(self):
        self.project.info.pop("logo", None)
        self.project.assets.pop("logo.png", None)
        self._refresh_all()
        self._extra_dirty = True
        self._title()

    def on_title_block(self):
        sc = self.scene_
        dlg = TitleBlockDialog(self, self.project.info, sc.sheet)
        if dlg.exec():
            info, name, lines = dlg.result_values()
            self.project.info.update(info)
            sc.sheet.title, sc.sheet.title_lines = name, lines
            self.tabs.setTabText(self.tabs.currentIndex(), self._tab_label(sc.sheet))
            self._refresh_all()
            self._extra_dirty = True
            self._title()

    # ---------------------------------------------------------------- files
    def _dirty(self):
        return self._extra_dirty or any(not sc.undo.isClean() for sc in self._scenes())

    def _confirm_discard(self):
        if not self._dirty():
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Discard unsaved changes?")
        return r == QMessageBox.StandardButton.Yes

    def on_new(self):
        if self._confirm_discard():
            self._replace(default_project(), None)

    def on_open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Electro_qt project (*.eqt)")
        if path:
            try:
                self._replace(load_project(path), path)
            except Exception as ex:           # noqa: BLE001 - surface any load problem
                QMessageBox.critical(self, "Open failed", str(ex))

    def _replace(self, project, path):
        new = MainWindow(project, path)
        new.showMaximized()
        MainWindow._keep = getattr(MainWindow, "_keep", []) + [new]
        self._extra_dirty = False
        for sc in self._scenes():
            sc.undo.setClean()
        self.close()

    def on_save(self):
        if not self.path:
            return self.on_save_as()
        save_project(self.project, self.path)
        for sc in self._sheet_scenes():
            sc.undo.setClean()
        self._extra_dirty = False
        self._title()

    def on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "", "Electro_qt project (*.eqt)")
        if path:
            if not path.endswith(".eqt"):
                path += ".eqt"
            self.path = path
            self.on_save()

    def closeEvent(self, ev):
        ev.accept()


ICON = os.path.join(os.path.dirname(__file__), "resources", "icon.png")


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Electro_qt")
    if sys.platform == "win32":                    # own taskbar entry / icon instead of python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Electro_qt.app")
        except Exception:   # noqa: BLE001
            pass
    app.setWindowIcon(QIcon(ICON))
    win = MainWindow()
    win.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
