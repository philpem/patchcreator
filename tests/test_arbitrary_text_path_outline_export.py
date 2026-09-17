from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.svg.export import CompatibilityExportError, ExportOptions, export_svg_text

SVG_NS = "http://www.w3.org/2000/svg"

_SYSTEM_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)


def _system_font() -> Path:
    for path in _SYSTEM_FONT_CANDIDATES:
        if path.is_file():
            return path
    pytest.skip("no known redistributable system test font is installed")


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_cubic_textpath_is_outlined_with_tangent_rotated_glyphs():
    svg = f'''<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="curve" d="M 5,45 C 20,10 55,10 75,45"/></defs>
  <text id="curve-title" font-size="5" text-anchor="middle" fill="#ffcc33">
    <textPath href="#curve" startOffset="50%">CURVE</textPath>
  </text>
</svg>'''
    result = export_svg_text(
        svg,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    group = root.find(f".//{{{SVG_NS}}}g[@id='curve-title']")
    assert group is not None
    paths = group.findall(f"{{{SVG_NS}}}path")
    assert len(paths) == 5
    # A non-horizontal cubic must rotate at least one glyph away from the
    # straight-text matrix form, so the matrix has non-zero off-diagonals.
    matrices = [path.get("transform", "") for path in paths]
    assert any("matrix(" in value and " 0 0 " not in value for value in matrices)


def test_svg_elliptical_arc_textpath_is_supported():
    svg = f'''<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="ellipse-arc" d="M 10,40 A 30,15 0 0 1 70,40"/></defs>
  <text id="arc-title" font-size="4" text-anchor="middle" dy="1.25">
    <textPath href="#ellipse-arc" startOffset="50%" textLength="30" lengthAdjust="spacing">ELLIPSE</textPath>
  </text>
</svg>'''
    result = export_svg_text(
        svg,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}textPath") is None
    assert root.findall(f".//{{{SVG_NS}}}g[@id='arc-title']/{{{SVG_NS}}}path")


def test_open_path_overflow_fails_explicitly():
    svg = f'''<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="short" d="M 10,20 L 20,20"/></defs>
  <text id="too-long" font-size="8" text-anchor="start">
    <textPath href="#short" startOffset="0">THIS WILL NOT FIT</textPath>
  </text>
</svg>'''
    with pytest.raises(CompatibilityExportError, match="falls outside its open baseline"):
        export_svg_text(
            svg,
            options=ExportOptions(text_mode="paths", font_path=_system_font()),
        )


def test_closed_path_can_wrap_start_offset_without_leaving_baseline():
    svg = f'''<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="loop" d="M 20,20 L 60,20 L 60,60 L 20,60 Z"/></defs>
  <text id="loop-title" font-size="3" text-anchor="middle">
    <textPath href="#loop" startOffset="98%">LOOP</textPath>
  </text>
</svg>'''
    result = export_svg_text(
        svg,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    assert result.outlined_text_count == 1
    assert root.findall(f".//{{{SVG_NS}}}g[@id='loop-title']/{{{SVG_NS}}}path")
