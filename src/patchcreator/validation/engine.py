"""Independent SVG validation engine shared by CLI and future compositor hooks."""

from __future__ import annotations

from pathlib import Path

from .model import Finding, ValidationReport
from .strokes import validate_minimum_stroke_width
from .svg import load_svg


def check_svg(
    path: str | Path,
    *,
    minimum_stroke_width_mm: float | None = None,
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

    return ValidationReport(
        source=source,
        findings=tuple(findings),
        validator_names=tuple(validators),
    )
