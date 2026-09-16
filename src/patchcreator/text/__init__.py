"""Font resolution and text shaping primitives.

This package is intentionally independent of SVG export.  The compatibility
exporter and a future GUI can both resolve fonts and shape text through the same
API before deciding how the glyphs should be rendered or positioned.
"""

from .fonts import (
    FontFaceInfo,
    FontRequest,
    FontResolutionError,
    ResolvedFont,
    default_font_directories,
    open_ttfont,
    resolve_font,
)
from .shaping import ShapedGlyph, ShapedRun, shape_text

__all__ = [
    "FontFaceInfo",
    "FontRequest",
    "FontResolutionError",
    "ResolvedFont",
    "ShapedGlyph",
    "ShapedRun",
    "default_font_directories",
    "open_ttfont",
    "resolve_font",
    "shape_text",
]
