"""An explicitly approximate paper circuit and reproducible shape variations."""

from __future__ import annotations

from dataclasses import asdict, replace
import math
from pathlib import Path
import random

import yaml

from map_editor.models.annotations import Point2D
from map_editor.services.procedural_track import TrackSpec, TrackSpecError, generate_track_bundle


def build_paper_track_spec(
    stem: str = "paper_l_reference", *, target_length: float = 17.0,
    track_width: float = 1.0, horizontal_extent: float = 6.0,
    vertical_extent: float = 5.0, arm_extent: float = 2.8,
) -> TrackSpec:
    """Rounded L-loop fitted to a target lap length, not an author-supplied map.

    Extents define the control polygon before smoothing and length fitting;
    they are shape parameters, not final map dimensions.
    """
    if not all(math.isfinite(v) and v > 0 for v in
               (horizontal_extent, vertical_extent, arm_extent)):
        raise TrackSpecError("Shape extents must be finite and positive.")
    if arm_extent >= min(horizontal_extent, vertical_extent):
        raise TrackSpecError("L-shaped arm must be shorter than both outer extents.")
    points = [(0, 0), (horizontal_extent, 0), (horizontal_extent, arm_extent),
              (arm_extent, arm_extent), (arm_extent, vertical_extent), (0, vertical_extent)]
    return TrackSpec(
        stem=stem, control_points=[Point2D(x, y) for x, y in points],
        track_width=track_width, target_length=target_length,
        centerline_spacing=0.05, resolution=0.02, padding=1.0,
        wall_thickness_px=1, min_curvature_radius=0.65,
        min_wall_separation=track_width,
        provenance={
            "family": "paper_l", "role": "reference_approximation",
            "paper": "https://arxiv.org/abs/2504.02420v2",
            "description": "Rounded L-shaped approximation; not the authors' original geometry.",
            "assumptions": [
                "The reported 17 m length is treated as centerline lap length.",
                "Nominal width is 1 m; corner shapes and proportions are approximated.",
                "Minimum radius of 0.65 m is a generation constraint, not a paper measurement.",
            ],
            "shape_parameters": dict(horizontal_extent=horizontal_extent,
                                     vertical_extent=vertical_extent, arm_extent=arm_extent),
        },
    )


def vary_paper_track(reference: TrackSpec, *, stem: str, seed: int, variation: float) -> TrackSpec:
    """Vary the three control-polygon dimensions and retain physical constraints."""
    if not math.isfinite(variation) or not 0 < variation <= 0.5:
        raise TrackSpecError("Variation must be greater than 0 and at most 0.5.")
    if reference.provenance.get("family") != "paper_l":
        raise TrackSpecError("Collection generation requires a paper L reference.")
    rng = random.Random(seed)
    parameters = {name: value * rng.uniform(1 - variation, 1 + variation)
                  for name, value in reference.provenance["shape_parameters"].items()}
    candidate = build_paper_track_spec(stem, **parameters)
    provenance = dict(candidate.provenance, role="generated_variant", seed=seed,
                      variation=variation, reference=reference.stem)
    return replace(reference, stem=stem, control_points=candidate.control_points,
                   provenance=provenance)


def generate_paper_collection(
    reference: TrackSpec, output_root: Path, *, count: int = 12, seed: int = 42,
    variation: float = 0.2, max_attempts: int | None = None,
) -> dict:
    """Write the reference plus count accepted variants and an audit manifest.

    A fresh output directory is required. Constraint failures are recorded and
    retried with new seeds, while I/O failures propagate. Partial collections
    retain an explicit incomplete status and every rejection reason.
    """
    if count < 1 or count > 10000:
        raise TrackSpecError("Collection count must be between 1 and 10000.")
    if not math.isfinite(variation) or not 0 < variation <= 0.5:
        raise TrackSpecError("Variation must be greater than 0 and at most 0.5.")
    if reference.provenance.get("family") != "paper_l":
        raise TrackSpecError("Collection generation requires a paper L reference.")
    budget = max_attempts if max_attempts is not None else count * 20
    if budget < 1:
        raise TrackSpecError("Maximum attempts must be positive.")
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise TrackSpecError("Choose an empty output directory for a collection.")

    reference_path = generate_track_bundle(reference, output_root / reference.stem)
    reference_recipe = yaml.safe_load(reference_path.with_name(
        f"{reference.stem}_generation.yaml").read_text(encoding="utf-8"))
    report = {
        "schema_version": 1, "family": "paper_l", "seed": seed,
        "variation": variation, "requested_variants": count, "max_attempts": budget,
        "complete": False,
        "reference": {"map": str(reference_path.relative_to(output_root)),
                      "achieved": reference_recipe["achieved"]},
        "accepted": [], "rejected": [],
    }
    manifest = output_root / "collection.yaml"

    def save_report():
        manifest.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")

    save_report()
    rng = random.Random(seed)
    for attempt in range(1, budget + 1):
        candidate_seed = rng.getrandbits(63)
        stem = f"paper_l_{len(report['accepted']) + 1:03d}"
        if stem == reference.stem:
            stem += "_variant"
        candidate = None
        try:
            candidate = vary_paper_track(reference, stem=stem, seed=candidate_seed, variation=variation)
            path = generate_track_bundle(candidate, output_root / stem)
        except TrackSpecError as exc:
            entry = {"attempt": attempt, "seed": candidate_seed,
                     "reason": str(exc), "achieved": exc.metrics}
            if candidate is not None:
                entry["recipe"] = asdict(candidate)
                entry["recipe"]["control_points"] = [[p.x, p.y] for p in candidate.control_points]
            report["rejected"].append(entry)
        else:
            recipe = yaml.safe_load(path.with_name(f"{stem}_generation.yaml").read_text(encoding="utf-8"))
            report["accepted"].append({"attempt": attempt, "seed": candidate_seed,
                                       "map": str(path.relative_to(output_root)),
                                       "achieved": recipe["achieved"]})
        report["complete"] = len(report["accepted"]) == count
        save_report()
        if report["complete"]:
            break
    return report
