from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.svg.export import CompatibilityExportError, ExportOptions, export_svg_text
from patchcreator.svg.writer import render_design

SVG_NS = "http://www.w3.org/2000/svg"

_SYSTEM_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)
_MATRIX_RE = re.compile(
    r"matrix\(([-+0-9.eE]+) 0 0 ([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+)\)"
)


def _system_font() -> Path:
    for path in _SYSTEM_FONT_CANDIDATES:
        if path.is_file():
            return path
    pytest.skip("no known redistributable system test font is installed")


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _matrix(element: ET.Element) -> tuple[float, float, float, float]:
    match = _MATRIX_RE.fullmatch(element.attrib["transform"])
    assert match is not None
    return tuple(float(value) for value in match.groups())  # type: ignore[return-value]


def test_export_outlines_shaped_straight_text_and_preserves_style_and_transform():
    font = _system_font()
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <text id="title" x="40" y="20" font-family="Definitely Not The File Family"
        font-size="6" font-weight="700" text-anchor="middle"
        fill="#f3c344" stroke="#111111" stroke-width="0.2"
        opacity="0.8" transform="rotate(5 40 20)">AV</text>
</svg>""",
        options=ExportOptions(text_mode="paths", font_path=font),
    )

    root = _root(result.svg)
    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    group = root.find(f".//{{{SVG_NS}}}g[@id='title']")
    assert group is not None
    assert group.attrib["fill"] == "#f3c344"
    assert group.attrib["stroke"] == "#111111"
    assert group.attrib["stroke-width"] == "0.2"
    assert group.attrib["opacity"] == "0.8"
    assert group.attrib["transform"] == "rotate(5 40 20)"
    paths = group.findall(f"{{{SVG_NS}}}path")
    assert len(paths) == 2
    assert all(path.attrib["d"] for path in paths)
    assert all("matrix(" in path.attrib["transform"] for path in paths)
    assert any("substituted" in warning for warning in result.warnings)


def test_textlength_spacing_and_middle_anchor_are_applied_to_glyph_origins():
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <text id="label" x="40" y="30" font-size="5" text-anchor="middle"
        textLength="20" lengthAdjust="spacing">AB</text>
</svg>""",
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    paths = root.findall(f".//{{{SVG_NS}}}g[@id='label']/{{{SVG_NS}}}path")
    assert len(paths) == 2
    first = _matrix(paths[0])
    second = _matrix(paths[1])
    assert first[2] == pytest.approx(30.0)
    assert second[2] > first[2]
    assert first[3] == pytest.approx(30.0)
    assert second[3] == pytest.approx(30.0)


def test_patchcreator_lower_band_with_auto_fit_can_be_exported_to_paths():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette: {gold: '#ffcc33'}
layers:
  - id: text
    elements:
      - id: motto
        type: text
        text: ONE HORIZON
        layout: {type: lower-band, offset: 20, width: 50, fit: 90%}
        font: {family: DejaVu Sans, size: 5, tracking: auto}
        fill: gold
        clip: {target: none}
"""
    )
    master = render_design(design).svg
    result = export_svg_text(
        master,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    group = root.find(f".//{{{SVG_NS}}}g[@id='motto-text']")
    assert group is not None
    assert group.findall(f"{{{SVG_NS}}}path")


def test_external_single_path_textpath_is_exported_to_paths():
    svg = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="arc" d="M 10,20 A 20,20 0 0 1 50,20"/></defs>
  <text id="title" font-size="5"><textPath href="#arc">CURVED</textPath></text>
</svg>"""
    result = export_svg_text(
        svg,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    assert root.findall(f".//{{{SVG_NS}}}g[@id='title']/{{{SVG_NS}}}path")


def test_tspan_and_unsupported_textlength_mode_fail_explicitly():
    tspan = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <text id="label" x="10" y="20" font-size="5"><tspan>SPAN</tspan></text>
</svg>"""
    with pytest.raises(CompatibilityExportError, match="tspan"):
        export_svg_text(
            tspan,
            options=ExportOptions(text_mode="paths", font_path=_system_font()),
        )

    scaled = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <text id="label" x="10" y="20" font-size="5" textLength="20"
        lengthAdjust="spacingAndGlyphs">AB</text>
</svg>"""
    with pytest.raises(CompatibilityExportError, match="lengthAdjust='spacing'"):
        export_svg_text(
            scaled,
            options=ExportOptions(text_mode="paths", font_path=_system_font()),
        )
