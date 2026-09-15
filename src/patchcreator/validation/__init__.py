"""Embroidery-aware geometry validation API."""

from .engine import check_svg
from .model import Finding, ValidationReport
from .strokes import validate_minimum_stroke_width
from .svg import SvgInspectionError

__all__ = [
    "Finding",
    "SvgInspectionError",
    "ValidationReport",
    "check_svg",
    "validate_minimum_stroke_width",
]
