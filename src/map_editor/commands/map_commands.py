"""Undo commands for changes to map geometry."""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtGui import QUndoCommand

from map_editor.models.annotations import MapAnnotations
from map_editor.models.map_bundle import MapMetadata


@dataclass(frozen=True)
class MapGeometryState:
    metadata: MapMetadata
    annotations: MapAnnotations
    centerline_spacing: float


class ScaleMapCommand(QUndoCommand):
    """Restore metadata and annotations together when undoing a scale change.

    Keep annotation object identities so adjacent annotation commands continue
    editing the correct state on either side of this command.
    """

    def __init__(
        self,
        before: MapGeometryState,
        after: MapGeometryState,
        apply_state: Callable[[MapGeometryState], None],
    ) -> None:
        super().__init__("Scale map to target width")
        self._before = before
        self._after = after
        self._apply_state = apply_state

    def redo(self) -> None:
        self._apply_state(self._after)

    def undo(self) -> None:
        self._apply_state(self._before)
