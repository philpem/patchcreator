"""Regression checks for live-text font fitting."""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from patchcreator.config.loader import load_design, loads_design
from patchcreator.svg.text_path_outline import outline_arc_text
from patchcreator.svg.writer import render_design
from patchcreator.text import FontRequest, resolve_font, shape_text

SVG = "{http://www.w3.org/2000/svg}"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _outline(root: ET.Element) -> ET.Element:
    outline_arc_text(root)
    return root


def test_trajectory_title_fits_without_textlength_or_negative_tracking():
    root = ET.fromstring(render_design(load_design(EXAMPLES / "trajectory-and-placement.yaml")).svg)
    text = root.find(f".//{SVG}text[@id='top-title-text']")
    path = text.find(f"{SVG}textPath")
    assert path.text == "TRAJECTORY / PATH PLACEMENT"
    assert text.text is None
    assert path.tail is None
    size = float(text.get("font-size"))
    assert 0 < size < 4.2
    spacing = float(text.get("letter-spacing"))
    assert spacing >= 0
    run = shape_text(path.text, resolve_font(FontRequest(family=text.get("font-family"), weight=700)))
    advance = run.x_advance * size / run.units_per_em + spacing * (len(run.glyphs) - 1)
    assert advance == pytest.approx(33 * math.radians(110) * .9, abs=1e-4)
    # Outlining must preserve every non-space glyph, including both end letters.
    _outline(root)
    outlined = root.find(f".//{SVG}g[@id='top-title-text']")
    assert len(outlined.findall(f"{SVG}path")) == len(path.text.replace(" ", ""))


def test_single_glyph_auto_fit_does_not_request_impossible_spacing():
    design = loads_design('''version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: label
        type: text
        text: A
        layout: {type: top-arc, radius: 30}
        font: {family: sans-serif, size: 5, tracking: auto}
''')
    root = ET.fromstring(render_design(design).svg)
    assert root.find(f".//{SVG}textPath").get("textLength") is None
    _outline(root)
    assert root.find(f".//{SVG}textPath") is None


def test_live_text_with_missing_font_remains_editable_with_a_warning():
    design = loads_design('''version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: label
        type: text
        text: A CUSTOM FONT
        layout: {type: top-arc, radius: 30}
        font: {family: Definitely Missing Font For This Test}
''')
    result = render_design(design)
    root = ET.fromstring(result.svg)
    assert root.find(f".//{SVG}textPath").text == "A CUSTOM FONT"
    assert any("cannot measure live text font" in warning for warning in result.warnings)
