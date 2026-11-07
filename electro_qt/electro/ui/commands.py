"""Undo commands. They mutate the model, then ask the scene to sync items."""
from PySide6.QtGui import QUndoCommand
from ..geometry import translate


class AddCmd(QUndoCommand):
    def __init__(self, scene, entities, text="Add"):
        super().__init__(text)
        self.scene, self.entities = scene, list(entities)

    def redo(self):
        for e in self.entities:
            self.scene.sheet.entities.append(e)
            self.scene.sync_add(e)

    def undo(self):
        for e in reversed(self.entities):
            self.scene.sheet.entities.remove(e)
            self.scene.sync_remove(e.id)


class DeleteCmd(QUndoCommand):
    def __init__(self, scene, entities):
        super().__init__("Delete")
        ents = scene.sheet.entities
        self.scene = scene
        self.items = sorted(((ents.index(e), e) for e in entities), key=lambda t: t[0])

    def redo(self):
        for _, e in reversed(self.items):
            self.scene.sheet.entities.remove(e)
            self.scene.sync_remove(e.id)

    def undo(self):
        for i, e in self.items:
            self.scene.sheet.entities.insert(i, e)
            self.scene.sync_add(e)


class MoveCmd(QUndoCommand):
    def __init__(self, scene, entities, dx, dy):
        super().__init__("Move")
        self.scene, self.entities, self.dx, self.dy = scene, list(entities), dx, dy

    def _apply(self, dx, dy):
        for e in self.entities:
            translate(e, dx, dy)
            self.scene.sync_refresh(e)

    def redo(self): self._apply(self.dx, self.dy)
    def undo(self): self._apply(-self.dx, -self.dy)


class EditCmd(QUndoCommand):
    """Modify fields on existing entities, add new ones, remove some: one undo step.
    modify = [(entity, {field: new_value})]"""

    def __init__(self, scene, label, modify=(), add=(), remove=()):
        super().__init__(label)
        self.scene = scene
        self.modify = [(e, dict(v)) for e, v in modify]
        self.old = [{k: getattr(e, k) for k in v} for e, v in self.modify]
        self.add = list(add)
        ents = scene.sheet.entities
        self.remove = sorted(((ents.index(e), e) for e in remove), key=lambda t: t[0])

    # Order matters: an entity can be both added and modified (e.g. a rectangle
    # exploded into lines, then filleted), so add before modify and undo in reverse.
    def redo(self):
        for _, e in reversed(self.remove):
            self.scene.sheet.entities.remove(e)
            self.scene.sync_remove(e.id)
        for e in self.add:
            self.scene.sheet.entities.append(e)
            self.scene.sync_add(e)
        for (e, new) in self.modify:
            for k, v in new.items():
                setattr(e, k, v)
            self.scene.sync_refresh(e)

    def undo(self):
        for (e, _), old in zip(self.modify, self.old):
            for k, v in old.items():
                setattr(e, k, v)
            self.scene.sync_refresh(e)
        for e in reversed(self.add):
            self.scene.sheet.entities.remove(e)
            self.scene.sync_remove(e.id)
        for i, e in self.remove:
            self.scene.sheet.entities.insert(i, e)
            self.scene.sync_add(e)


class LayerStateCmd(QUndoCommand):
    """Layer-table edits (and the entity changes they cause) as one undo step."""

    def __init__(self, scene, before, after):
        super().__init__("Layers")
        self.scene, self.before, self.after = scene, before, after

    def redo(self): self.scene.restore_layer_state(self.after)
    def undo(self): self.scene.restore_layer_state(self.before)


class StretchCmd(QUndoCommand):
    """One completed grip drag on a group. before/after = [(entity, {field: value})]."""

    def __init__(self, scene, group, before, after):
        super().__init__("Resize")
        self.scene, self.group, self.before, self.after = scene, group, before, after

    def _apply(self, snap):
        for e, vals in snap:
            for k, v in vals.items():
                setattr(e, k, v)
        self.scene.sync_refresh(self.group)

    def redo(self): self._apply(self.after)
    def undo(self): self._apply(self.before)


class MoveEachCmd(QUndoCommand):
    """Move several entities by different amounts (align / distribute)."""

    def __init__(self, scene, moves, label="Move"):
        super().__init__(label)
        self.scene, self.moves = scene, list(moves)      # [(entity, dx, dy)]

    def _apply(self, sign):
        for e, dx, dy in self.moves:
            translate(e, sign * dx, sign * dy)
            self.scene.sync_refresh(e)

    def redo(self): self._apply(1)
    def undo(self): self._apply(-1)


class AddBundleCmd(QUndoCommand):
    def __init__(self, sheet, bundle):
        super().__init__("Bundle")
        self.sheet, self.bundle = sheet, bundle

    def redo(self): self.sheet.bundles.append(self.bundle)
    def undo(self): self.sheet.bundles.remove(self.bundle)


class StateCmd(QUndoCommand):
    """Set many fields at once and refresh the affected objects (rotate, mirror, ...).
    before / after = [(entity, {field: value})] from geometry.snapshot(); tops = the
    top-level entities whose items need rebuilding."""

    def __init__(self, scene, tops, before, after, label):
        super().__init__(label)
        self.scene, self.tops, self.before, self.after = scene, list(tops), before, after

    def _apply(self, snap):
        for e, vals in snap:
            for k, v in vals.items():
                setattr(e, k, v)
        for e in self.tops:
            self.scene.sync_refresh(e)

    def redo(self): self._apply(self.after)
    def undo(self): self._apply(self.before)


class BlockDefCmd(QUndoCommand):
    """Add a block definition to the project (Make block)."""

    def __init__(self, scene, block):
        super().__init__("Add block definition")
        self.scene, self.block = scene, block

    def redo(self):
        self.scene.project.blocks[self.block.name] = self.block
        self.scene.blocks_changed.emit()

    def undo(self):
        self.scene.project.blocks.pop(self.block.name, None)
        self.scene.blocks_changed.emit()
