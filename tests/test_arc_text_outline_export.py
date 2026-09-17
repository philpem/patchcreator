from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.svg.export import ExportOptions, export_svg_text
from patchcreator.svg.writer import render_design

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"

_SYSTEM_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)
_MATRIX_RE = re.compile(
    r"matrix\(([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+)\)"
)


def _system_font() -> Path:
    for path in _SYSTEM_FONT_CANDIDATES:
        if path.is_file():
            return path
    pytest.skip("no known redistributable system test font is installed")


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _matrix(path: ET.Element) -> tuple[float, ...]:
    match = _MATRIX_RE.fullmatch(path.attrib["transform"])
    assert match is not None
    return tuple(float(value) for value in match.groups())


def test_patchcreator_top_and_bottom_arc_text_are_outlined_on_tangents():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette: {gold: '#ffcc33'}
layers:
  - id: text
    elements:
      - id: top-title
        type: text
        text: TOP ORBIT
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        layout:
          type: top-arc
          radius: 30
          start_angle: 300deg
          end_angle: 60deg
          baseline_shift: 0.8
        font: {family: DejaVu Sans, size: 5, tracking: auto}
        fill: gold
        clip: {target: none}
      - id: bottom-title
        type: text
        text: BOTTOM ORBIT
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        layout:
          type: bottom-arc
          radius: 31
          start_angle: 240deg
          end_angle: 120deg
        font: {family: DejaVu Sans, size: 5, tracking: auto}
        fill: gold
        clip: {target: none}
"""
    )

    master = render_design(design).svg
    master_root = _root(master)
    assert len(master_root.findall(f".//{{{SVG_NS}}}textPath")) == 2
    assert len(master_root.findall(f".//{{{SVG_NS}}}path[@{{{PATCHCREATOR_NS}}}construction-role='text-baseline']")) == 2

    result = export_svg_text(
        master,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)

    assert result.outlined_text_count == 2
    assert root.find(f".//{{{SVG_NS}}}text") is None
    assert root.find(f".//{{{SVG_NS}}}textPath") is None
    assert root.find(f".//*[@{{{PATCHCREATOR_NS}}}construction-role='text-baseline']") is None

    for text_id in ("top-title-text", "bottom-title-text"):
        group = root.find(f".//{{{SVG_NS}}}g[@id='{text_id}']")
        assert group is not None
        assert group.attrib["fill"] == "#ffcc33"
        paths = group.findall(f"{{{SVG_NS}}}path")
        assert len(paths) >= 3
        matrices = [_matrix(path) for path in paths]
        assert any(abs(values[1]) > 1e-5 and abs(values[2]) > 1e-5 for values in matrices)


def test_arc_text_startoffset_anchor_and_textlength_stay_inside_baseline():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: text
    elements:
      - id: title
        type: text
        text: CENTRED
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        layout:
          type: top-arc
          radius: 30
          start_angle: 300deg
          end_angle: 60deg
          fit: 70%
        font: {family: DejaVu Sans, size: 5, tracking: auto}
        clip: {target: none}
"""
    )
    result = export_svg_text(
        render_design(design).svg,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    root = _root(result.svg)
    paths = root.findall(f".//{{{SVG_NS}}}g[@id='title-text']/{{{SVG_NS}}}path")
    assert paths
    origins = [(_matrix(path)[4], _matrix(path)[5]) for path in paths]
    radii = [(x * x + y * y) ** 0.5 for x, y in origins]
    assert all(28.5 <= radius <= 31.5 for radius in radii)


def test_non_patchcreator_and_elliptical_textpaths_are_supported():
    ordinary = f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="arc" d="M 10,20 A 20,20 0 0 1 50,20"/></defs>
  <text id="title" font-family="DejaVu Sans" font-size="5">
    <textPath href="#arc">CURVED</textPath>
  </text>
</svg>"""
    result = export_svg_text(
        ordinary,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    assert result.outlined_text_count == 1
    assert _root(result.svg).find(f".//{{{SVG_NS}}}text") is None

    elliptical = f"""<svg xmlns="{SVG_NS}" xmlns:patchcreator="{PATCHCREATOR_NS}"
      width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="baseline" d="M 10,20 A 20,15 0 0 1 50,20"
        patchcreator:construction-role="text-baseline"/>
  <text id="title" font-family="DejaVu Sans" font-size="5">
    <textPath href="#baseline">CURVED</textPath>
  </text>
</svg>"""
    result = export_svg_text(
        elliptical,
        options=ExportOptions(text_mode="paths", font_path=_system_font()),
    )
    assert result.outlined_text_count == 1
    assert _root(result.svg).find(f".//{{{SVG_NS}}}text") is None
