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


def test_cubic_textpath_is_outlined_with_tangent_aligned_glyph_paths():
    svg = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="curve" d="M 10 50 C 25 10 55 10 70 50"/></defs>
  <text id="title" font-size="5" text-anchor="middle" fill="#ffd84d">
    <textPath href="#curve" startOffset="50%">CURVE</textPath>
  </text>
</svg>"""
    result = export_svg_text(svg, options=ExportOptions(text_mode="paths", font_path=_system_font()))
    root = _root(result.svg)

    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    group = root.find(f".//{{{SVG_NS}}}g[@id='title']")
    assert group is not None
    glyphs = group.findall(f"{{{SVG_NS}}}path")
    assert glyphs
    assert all(path.get("transform", "").startswith("matrix(") for path in glyphs)
    # A curved baseline must produce at least two distinct tangent matrices.
    assert len({path.attrib["transform"] for path in glyphs}) > 1


def test_elliptical_closed_textpath_is_supported():
    svg = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="loop" d="M 20 40 A 20 12 0 1 1 60 40 A 20 12 0 1 1 20 40 Z"/></defs>
  <text id="loop-title" font-size="4" fill="#fff">
    <textPath href="#loop" startOffset="8">ORBIT</textPath>
  </text>
</svg>"""
    result = export_svg_text(svg, options=ExportOptions(text_mode="paths", font_path=_system_font()))
    root = _root(result.svg)

    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    assert root.findall(f".//{{{SVG_NS}}}g[@id='loop-title']/{{{SVG_NS}}}path")


def test_disconnected_textpath_fails_explicitly():
    svg = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="broken" d="M 0 0 L 20 0 M 30 0 L 50 0"/></defs>
  <text id="title" font-size="5"><textPath href="#broken">BROKEN</textPath></text>
</svg>"""
    with pytest.raises(CompatibilityExportError, match="multiple disconnected subpaths"):
        export_svg_text(svg, options=ExportOptions(text_mode="paths", font_path=_system_font()))


def test_transformed_arbitrary_textpath_fails_instead_of_approximating():
    svg = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="curve" d="M 10 40 Q 40 10 70 40" transform="translate(1 2)"/></defs>
  <text id="title" font-size="5"><textPath href="#curve">CURVE</textPath></text>
</svg>"""
    with pytest.raises(CompatibilityExportError, match="transformed arbitrary textPath baselines"):
        export_svg_text(svg, options=ExportOptions(text_mode="paths", font_path=_system_font()))
