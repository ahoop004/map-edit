"""Undo/redo commands for annotation edits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtGui import QUndoCommand

from map_editor.models.annotations import MapAnnotations, SpawnPoint, StartFinishLine


@dataclass
class AnnotationContext:
    """Callback hooks required by annotation undo commands."""

    annotations: MapAnnotations
    on_annotations_changed: Callable[[MapAnnotations], None]


class SetStartFinishLineCommand(QUndoCommand):
    """Set or update the start/finish line."""

    def __init__(
        self,
        context: AnnotationContext,
        new_value: Optional[StartFinishLine],
        description: str = "Set start/finish line",
    ) -> None:
        super().__init__(description)
        self._context = context
        self._new_value = new_value
        self._old_value = context.annotations.start_finish_line

    def redo(self) -> None:
        self._context.annotations.start_finish_line = self._new_value
        self._context.on_annotations_changed(self._context.annotations)

    def undo(self) -> None:
        self._context.annotations.start_finish_line = self._old_value
        self._context.on_annotations_changed(self._context.annotations)


class AddSpawnPointCommand(QUndoCommand):
    """Append a new spawn point to the list."""

    def __init__(self, context: AnnotationContext, spawn: SpawnPoint) -> None:
        super().__init__("Add spawn point")
        self._context = context
        self._spawn = spawn

    def redo(self) -> None:
        self._context.annotations.spawn_points.append(self._spawn)
        self._context.on_annotations_changed(self._context.annotations)

    def undo(self) -> None:
        if self._spawn in self._context.annotations.spawn_points:
            self._context.annotations.spawn_points.remove(self._spawn)
        self._context.on_annotations_changed(self._context.annotations)


class UpdateSpawnPointCommand(QUndoCommand):
    """Modify an existing spawn point by index."""

    def __init__(self, context: AnnotationContext, index: int, new_spawn: SpawnPoint) -> None:
        super().__init__("Update spawn point")
        self._context = context
        self._index = index
        self._new_spawn = new_spawn
        self._old_spawn = context.annotations.spawn_points[index]

    def redo(self) -> None:
        self._context.annotations.spawn_points[self._index] = self._new_spawn
        self._context.on_annotations_changed(self._context.annotations)

    def undo(self) -> None:
        self._context.annotations.spawn_points[self._index] = self._old_spawn
        self._context.on_annotations_changed(self._context.annotations)


class DeleteSpawnPointCommand(QUndoCommand):
    """Remove a spawn point by index."""

    def __init__(self, context: AnnotationContext, index: int) -> None:
        super().__init__("Delete spawn point")
        self._context = context
        self._index = index
        self._removed: Optional[SpawnPoint] = None

    def redo(self) -> None:
        if 0 <= self._index < len(self._context.annotations.spawn_points):
            self._removed = self._context.annotations.spawn_points.pop(self._index)
        self._context.on_annotations_changed(self._context.annotations)

    def undo(self) -> None:
        if self._removed is not None:
            self._context.annotations.spawn_points.insert(self._index, self._removed)
        self._context.on_annotations_changed(self._context.annotations)
