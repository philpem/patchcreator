"""Regression checks for path text rendering and compatibility export."""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import load_design, loads_design
from patchcreator.cli import main
from patchcreator.geometry import svg_path_sampler
from patchcreator.svg.text_path_outline import outline_arc_text
from patchcreator.svg.writer import render_design

SVG = "{http://www.w3.org/2000/svg}"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _outline(root: ET.Element) -> ET.Element:
    outline_arc_text(root)
    return root


def test_procedural_path_label_uses_placed_baseline_and_survives_outlining():
    svg = render_design(load_design(EXAMPLES / "text-layouts.yaml")).svg
    master = ET.fromstring(svg)
    label = master.find(f".//{SVG}text[@id='route-label-text']/{SVG}textPath")
    baseline = master.find(f".//{SVG}path[@id='{label.get('href')[1:]}']")
    midpoint = svg_path_sampler(baseline.get("d")).sample(.5).point
    # The trajectory is placed at the patch centre (40,40); its cubic midpoint
    # is (0,-7). Referencing its raw local path wrongly placed text off-canvas.
    assert midpoint == pytest.approx((40, 33), abs=.01)
    preview = _outline(ET.fromstring(svg))
    assert preview.find(f".//{SVG}textPath") is None
    assert preview.find(f".//{SVG}g[@id='route-label-text']/{SVG}path") is not None
    assert preview.find(f".//{SVG}g[@id='patchcreator-construction']") is not None
    assert master.find(f".//{SVG}textPath") is not None  # Master remains editable.


def test_procedural_baseline_length_is_measured_when_not_supplied():
    design = loads_design('''version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: route
        type: trajectory
        start: [-20, 0]
        segments: [{line: [20, 0]}]
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
      - id: label
        type: text
        text: MEASURE THIS BASELINE
        layout: {type: path, path: route}
''')
    rendered = render_design(design)
    assert not rendered.warnings
    root = ET.fromstring(rendered.svg)
    path = root.find(f".//{SVG}textPath")
    assert float(path.get("textLength")) == pytest.approx(36)
    _outline(root)
    assert root.find(f".//{SVG}textPath") is None


def test_render_can_outline_for_viewers_without_textpath(tmp_path):
    output = tmp_path / "outlined.svg"
    assert main(["render", str(EXAMPLES / "text-layouts.yaml"), "--text", "paths", "-o", str(output)]) == 0
    root = ET.parse(output).getroot()
    assert root.find(f".//{SVG}text") is None
    assert root.find(f".//{SVG}g[@id='top-title-text']/{SVG}path") is not None
    assert root.find(f".//{SVG}g[@id='route-label-text']/{SVG}path") is not None
    assert root.find(f".//{SVG}g[@id='patchcreator-construction']") is not None
