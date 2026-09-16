"""Map bundle loading and validation services."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QPixmap

from map_editor.models.map_bundle import MapBundle
from map_editor.services.yaml_serializer import (
    MapYamlDocument,
    MapYamlError,
    dump_map_yaml,
    load_map_yaml,
)


@dataclass(frozen=True)
class MapBundleLoadResult:
    """Outcome of attempting to load a map bundle from disk."""

    bundle: MapBundle
    warnings: tuple[str, ...] = ()


class MapBundleLoader:
    """High-level service to load YAML metadata + associated map image."""

    def __init__(self, search_image: bool = True) -> None:
        self.search_image = search_image

    def load_from_yaml(self, yaml_path: Path) -> MapBundleLoadResult:
        """Load a map bundle from a YAML file, resolving the image path."""
        document = load_map_yaml(yaml_path)
        image_path = self._resolve_image_path(yaml_path, Path(document.image))

        if not image_path.exists():
            raise MapYamlError(f"Image does not exist: {image_path}")

        self._validate_image_readable(image_path)

        bundle = MapBundle(
            image_path=image_path,
            yaml_path=yaml_path,
            metadata=document.metadata,
            annotations=document.annotations,
            negate=document.negate,
            extra_fields=document.extra_fields,
        )

        warnings = self._collect_warnings(document)
        return MapBundleLoadResult(bundle=bundle, warnings=warnings)

    def save_bundle(
        self,
        bundle: MapBundle,
        destination: Path | None = None,
        create_backup: bool = True,
    ) -> Path:
        """Serialize the bundle metadata + annotations to YAML and return the saved path."""
        if bundle.yaml_path is None and destination is None:
            raise ValueError("Destination path required for bundles without YAML path")

        target = destination or bundle.yaml_path
        assert target is not None

        document = MapYamlDocument(
            yaml_path=target,
            image=Path(os.path.relpath(bundle.image_path.resolve(), target.parent.resolve())).as_posix(),
            metadata=bundle.metadata,
            annotations=bundle.annotations,
            negate=bundle.negate,
            extra_fields=bundle.extra_fields,
        )
        yaml_text = dump_map_yaml(document)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent, suffix=".tmp", delete=False
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(yaml_text)
            if target.exists():
                shutil.copymode(target, temporary_path)
                if create_backup:
                    shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
            temporary_path.replace(target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return target

    def _resolve_image_path(self, yaml_path: Path, image_value: Path) -> Path:
        if image_value.is_absolute():
            return image_value
        resolved = (yaml_path.parent / image_value).resolve()
        if resolved.exists() or not self.search_image:
            return resolved
        # Optionally search for matching stems with different extensions (e.g. .png vs .pgm)
        for candidate in yaml_path.parent.glob(f"{image_value.stem}.*"):
            if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".pgm"}:
                return candidate
        return resolved

    @staticmethod
    def _validate_image_readable(image_path: Path) -> None:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise MapYamlError(f"Unable to load image: {image_path}")

    @staticmethod
    def _collect_warnings(document: MapYamlDocument) -> tuple[str, ...]:
        warnings = []
        # Check for unknown extra fields to surface to users.
        if document.extra_fields:
            warnings.append(
                "YAML contains additional keys that are preserved but not editable in the UI: "
                + ", ".join(sorted(document.extra_fields.keys()))
            )
        # Example: warn if annotations missing for racetrack context.
        if document.annotations.start_finish_line is None:
            warnings.append("No start/finish line defined in annotations")
        if not document.annotations.spawn_points:
            warnings.append("No spawn points defined in annotations")
        return tuple(warnings)


__all__ = ["MapBundleLoader", "MapBundleLoadResult"]
