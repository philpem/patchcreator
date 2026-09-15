"""Independent SVG validation engine shared by CLI and future compositor hooks."""

from __future__ import annotations

from pathlib import Path

from .features import validate_small_features
from .gaps import validate_narrow_gaps
from .model import Finding, ValidationReport
from .strokes import validate_minimum_stroke_width
from .svg import load_svg


def check_svg(
    path: str | Path,
    *,
    minimum_stroke_width_mm: float | None = None,
    minimum_feature_dimension_mm: float | None = None,
    minimum_island_area_mm2: float | None = None,
    minimum_gap_mm: float | None = None,
) -> ValidationReport:
    """Validate an existing SVG without requiring a PatchCreator design."""

    source, root = load_svg(path)
    findings: list[Finding] = []
    validators: list[str] = []

    if minimum_stroke_width_mm is not None:
        validators.append("minimum-stroke-width")
        findings.extend(
            validate_minimum_stroke_width(
                root,
                minimum_mm=minimum_stroke_width_mm,
            )
        )

    if minimum_feature_dimension_mm is not None or minimum_island_area_mm2 is not None:
        validators.append("small-features")
        findings.extend(
            validate_small_features(
                root,
                minimum_dimension_mm=minimum_feature_dimension_mm,
                minimum_island_area_mm2=minimum_island_area_mm2,
            )
        )

    if minimum_gap_mm is not None:
        validators.append("narrow-gaps")
        findings.extend(
            validate_narrow_gaps(
                root,
                minimum_mm=minimum_gap_mm,
            )
        )

    return ValidationReport(
        source=source,
        findings=tuple(findings),
        validator_names=tuple(validators),
    )
