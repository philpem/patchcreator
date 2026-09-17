"""Independent SVG validation engine shared by CLI and interactive front ends."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from .features import validate_small_features
from .gaps import validate_narrow_gaps
from .model import Finding, ValidationReport
from .overlaps import validate_overlaps
from .strokes import validate_minimum_stroke_width
from .svg import load_svg, parse_svg_text


def _check_root(
    root: ET.Element,
    *,
    source: Path | None,
    minimum_stroke_width_mm: float | None,
    minimum_feature_dimension_mm: float | None,
    minimum_island_area_mm2: float | None,
    minimum_gap_mm: float | None,
    overlap_diagnostics: bool,
) -> ValidationReport:
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

    if overlap_diagnostics:
        validators.append("overlaps")
        findings.extend(validate_overlaps(root))

    return ValidationReport(
        source=source,
        findings=tuple(findings),
        validator_names=tuple(validators),
    )


def check_svg(
    path: str | Path,
    *,
    minimum_stroke_width_mm: float | None = None,
    minimum_feature_dimension_mm: float | None = None,
    minimum_island_area_mm2: float | None = None,
    minimum_gap_mm: float | None = None,
    overlap_diagnostics: bool = False,
) -> ValidationReport:
    """Validate an existing SVG file without requiring a PatchCreator design."""

    source, root = load_svg(path)
    return _check_root(
        root,
        source=source,
        minimum_stroke_width_mm=minimum_stroke_width_mm,
        minimum_feature_dimension_mm=minimum_feature_dimension_mm,
        minimum_island_area_mm2=minimum_island_area_mm2,
        minimum_gap_mm=minimum_gap_mm,
        overlap_diagnostics=overlap_diagnostics,
    )


def check_svg_text(
    text: str,
    *,
    source: str | Path | None = None,
    minimum_stroke_width_mm: float | None = None,
    minimum_feature_dimension_mm: float | None = None,
    minimum_island_area_mm2: float | None = None,
    minimum_gap_mm: float | None = None,
    overlap_diagnostics: bool = False,
) -> ValidationReport:
    """Validate SVG text already held in memory.

    ``source`` is optional metadata used only for diagnostics/report identity; the
    SVG is never re-read from that path. This makes the API suitable for live GUI
    previews and other callers that have just rendered an SVG string.
    """

    source_path = Path(source) if source is not None else None
    root = parse_svg_text(text, source=source_path)
    return _check_root(
        root,
        source=source_path,
        minimum_stroke_width_mm=minimum_stroke_width_mm,
        minimum_feature_dimension_mm=minimum_feature_dimension_mm,
        minimum_island_area_mm2=minimum_island_area_mm2,
        minimum_gap_mm=minimum_gap_mm,
        overlap_diagnostics=overlap_diagnostics,
    )
