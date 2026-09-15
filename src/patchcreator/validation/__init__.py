"""Embroidery-aware geometry validation API."""

from .engine import check_svg
from .features import validate_small_features
from .geometry import FilledGeometry, iter_visible_fills, polygon_components
from .model import Finding, ValidationReport
from .strokes import validate_minimum_stroke_width
from .svg import SvgInspectionError

__all__ = [
    "FilledGeometry",
    "Finding",
    "SvgInspectionError",
    "ValidationReport",
    "check_svg",
    "iter_visible_fills",
    "polygon_components",
    "validate_minimum_stroke_width",
    "validate_small_features",
]
