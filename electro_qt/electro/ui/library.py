"""Library dock: the project's blocks in folders. Double-click a block to place it;
right-click for copy, data, folders, import and export."""
from __future__ import annotations
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
                               QPushButton, QLabel, QMenu, QStyle)
from .. import blocks as bk

KIND, VALUE, PROJ = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1, Qt.ItemDataRole.UserRole + 2


class LibraryPanel(QDockWidget):
    place = Signal(str)
    edit = Signal(str)
    edit_geometry = Signal(str)
    delete = Signal(str)
    copy = Signal(str)
    new_folder = Signal(str)            # parent folder path ("" = top)
    rename_folder = Signal(str)
    delete_folder = Signal(str)
    import_lib = Signal(str)            # folder to import into
    export_lib = Signal(str, str)       # ("all" | "folder" | "block", folder path / block name)
    save_to_library = Signal(str)
    reload = Signal()
    choose_root = Signal()
    edit_files = Signal()

    def __init__(self, parent=None):
        super().__init__("Library", parent)
        self.setObjectName("library")
        w = QWidget(); lay = QVBoxLayout(w)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemDoubleClicked.connect(self._double)
        self.tree.keyPressEvent = self._tree_key
        self.tree.currentItemChanged.connect(lambda *_: self._show())
        self.where = QLabel(""); self.where.setWordWrap(True)
        self.where.setStyleSheet("color: gray; font-size: 10px;")
        self.info = QLabel(""); self.info.setWordWrap(True)
        row = QHBoxLayout()
        for text, fn in (("Place", self._place), ("New folder", self._new_folder)):
            b = QPushButton(text); b.clicked.connect(lambda _=False, f=fn: f()); row.addWidget(b)
        row2 = QHBoxLayout()
        for text, fn in (("Import...", lambda: self.import_lib.emit(self._folder())),
                         ("Export...", self._export)):
            b = QPushButton(text); b.clicked.connect(lambda _=False, f=fn: f()); row2.addWidget(b)
        lay.addWidget(self.where); lay.addWidget(self.tree); lay.addWidget(self.info); lay.addLayout(row); lay.addLayout(row2)
        self.setWidget(w)
        self.setMinimumWidth(120)
        self.blocks, self.folders = {}, []

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Delete:
            kind, val = self._cur()
            if kind == "block":
                self.delete.emit(val)
            elif kind == "folder":
                self.delete_folder.emit(val)
            ev.accept(); return
        super().keyPressEvent(ev)

    # ---- selection helpers
    def _tree_key(self, ev):
        if ev.key() == Qt.Key.Key_Delete:
            self.keyPressEvent(ev)
        else:
            QTreeWidget.keyPressEvent(self.tree, ev)

    def _cur(self):
        it = self.tree.currentItem()
        return (it.data(0, KIND), it.data(0, VALUE)) if it is not None else (None, None)

    def _folder(self):
        """Folder the selection sits in (or is): where new things should go."""
        kind, val = self._cur()
        if kind == "folder":
            return val
        if kind == "block":
            return self.blocks[val].folder if val in self.blocks else ""
        return ""

    def _block(self, signal):
        kind, val = self._cur()
        if kind == "block":
            signal.emit(val)

    def _place(self):
        self._block(self.place)

    def _new_folder(self):
        self.new_folder.emit(self._folder())

    def _export(self):
        kind, val = self._cur()
        self.export_lib.emit(kind if kind in ("folder", "block") else "all", val or "")

    def _double(self, item, _col):
        if item.data(0, KIND) == "block":
            self.place.emit(item.data(0, VALUE))

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is not None:
            self.tree.setCurrentItem(it)
        kind, val = self._cur()
        m = QMenu(self)
        acts = {}
        proj_only = bool(it is not None and it.data(0, PROJ))
        if kind == "block":
            acts[m.addAction("Place")] = lambda: self.place.emit(val)
            if proj_only:
                acts[m.addAction("Save to shared library...")] = lambda: self.save_to_library.emit(val)
            acts[m.addAction("Edit block (geometry)...")] = lambda: self.edit_geometry.emit(val)
            acts[m.addAction("Data...")] = lambda: self.edit.emit(val)
            acts[m.addAction("Copy (rename)...")] = lambda: self.copy.emit(val)
            acts[m.addAction("Delete")] = lambda: self.delete.emit(val)
            m.addSeparator()
        if kind == "folder":
            acts[m.addAction("Rename folder...")] = lambda: self.rename_folder.emit(val)
            acts[m.addAction("Delete folder")] = lambda: self.delete_folder.emit(val)
            m.addSeparator()
        acts[m.addAction("New folder...")] = lambda: self.new_folder.emit(self._folder())
        acts[m.addAction("Import into here...")] = lambda: self.import_lib.emit(self._folder())
        if kind in ("block", "folder"):
            acts[m.addAction("Export this...")] = lambda: self.export_lib.emit(kind, val)
        acts[m.addAction("Export whole library...")] = lambda: self.export_lib.emit("all", "")
        m.addSeparator()
        acts[m.addAction("Edit library...")] = lambda: self.edit_files.emit()
        acts[m.addAction("Reload library")] = lambda: self.reload.emit()
        acts[m.addAction("Library folder...")] = lambda: self.choose_root.emit()
        chosen = m.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen in acts:
            acts[chosen]()

    def _show(self):
        kind, val = self._cur()
        b = self.blocks.get(val) if kind == "block" else None
        self.info.setText("" if b is None else
                          f"{b.description or '(no description)'}\n#{b.part_number or '-'}   "
                          f"{len(b.slots)} slot(s), {b.poles} pole(s)")

    # ---- fill
    def refresh(self, blocks, folders, project_only=(), root=""):
        sel = self._cur()
        self.blocks, self.folders = dict(blocks), folders
        self.where.setText(root)
        self.tree.clear()
        style = self.style()
        nodes = {"": self.tree.invisibleRootItem()}
        for path in folders:                                   # sorted: parents come first
            parent, _, leaf = path.rpartition("/")
            it = QTreeWidgetItem(nodes.get(parent, nodes[""]), [leaf])
            it.setIcon(0, style.standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            it.setData(0, KIND, "folder"); it.setData(0, VALUE, path)
            nodes[path] = it
        for name in sorted(blocks):
            it = QTreeWidgetItem(nodes.get(blocks[name].folder, nodes[""]), [name])
            it.setData(0, KIND, "block"); it.setData(0, VALUE, name)
        if project_only:                                       # used here, but not in the shared library
            top = QTreeWidgetItem(self.tree.invisibleRootItem(), ["This project only"])
            top.setIcon(0, style.standardIcon(QStyle.StandardPixmap.SP_FileIcon))
            top.setData(0, KIND, "projfolder"); top.setData(0, VALUE, "")
            for name in project_only:
                it = QTreeWidgetItem(top, [name])
                it.setData(0, KIND, "block"); it.setData(0, VALUE, name); it.setData(0, PROJ, True)
        self.tree.expandAll()
        for i in self._all_items():
            if (i.data(0, KIND), i.data(0, VALUE)) == sel:
                self.tree.setCurrentItem(i)
        self._show()

    def _all_items(self):
        out, stack = [], [self.tree.invisibleRootItem()]
        while stack:
            n = stack.pop()
            for i in range(n.childCount()):
                c = n.child(i); out.append(c); stack.append(c)
        return out
