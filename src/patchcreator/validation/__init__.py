"""Embroidery-aware geometry validation API."""

from .engine import check_svg
from .features import validate_small_features
from .gaps import validate_narrow_gaps
from .geometry import FilledGeometry, iter_visible_fills, polygon_components
from .model import Finding, ValidationReport
from .overlaps import validate_overlaps
from .overlay import OverlayStyle, add_debug_layer, write_debug_svg
from .strokes import validate_minimum_stroke_width
from .svg import SvgInspectionError

__all__ = [
    "FilledGeometry",
    "Finding",
    "OverlayStyle",
    "SvgInspectionError",
    "ValidationReport",
    "add_debug_layer",
    "check_svg",
    "iter_visible_fills",
    "polygon_components",
    "validate_minimum_stroke_width",
    "validate_narrow_gaps",
    "validate_overlaps",
    "validate_small_features",
    "write_debug_svg",
]
