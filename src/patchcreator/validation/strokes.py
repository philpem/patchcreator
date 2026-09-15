"""Minimum visible-stroke-width embroidery validator."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .model import Finding
from .svg import iter_visible_strokes


def validate_minimum_stroke_width(
    root: ET.Element,
    *,
    minimum_mm: float,
) -> tuple[Finding, ...]:
    if minimum_mm < 0:
        raise ValueError("minimum stroke width must not be negative")
    if minimum_mm == 0:
        return ()

    findings: list[Finding] = []
    for stroke in iter_visible_strokes(root):
        if stroke.width_mm + 1e-9 >= minimum_mm:
            continue
        findings.append(
            Finding(
                code="stroke-too-thin",
                severity="warning",
                message="visible stroke is below the selected embroidery profile minimum",
                element_id=stroke.element_id,
                element_tag=stroke.element_tag,
                measured_mm=stroke.width_mm,
                threshold_mm=minimum_mm,
            )
        )
    return tuple(findings)
