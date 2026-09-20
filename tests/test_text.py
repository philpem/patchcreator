from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from patchcreator.components import ComponentRegistry
from patchcreator.config.loader import loads_design
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design


def _find(root: ET.Element, tag: str, element_id: str):
    return root.find(f".//{{{SVG_NS}}}{tag}[@id='{element_id}']")


def test_text_is_builtin_and_bottom_arc_stays_live_editable_text():
    assert "text" in ComponentRegistry().component_types
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette: {gold: '#ffcc33'}
layers:
  - id: text
    elements:
      - id: title
        type: text
        text: SHARED ORBIT
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        layout:
          type: bottom-arc
          radius: 34
          start_angle: 225deg
          end_angle: 135deg
        font:
          family: DejaVu Sans
          weight: 700
          size: 5.5
          tracking: auto
        fill: gold
        clip: {target: none}
"""
    )

    root = ET.fromstring(render_design(design).svg)
    group = _find(root, "g", "title")
    baseline = _find(root, "path", "title-baseline")
    text = _find(root, "text", "title-text")
    text_path = text.find(f"{{{SVG_NS}}}textPath") if text is not None else None

    assert group is not None and baseline is not None and text is not None and text_path is not None
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}text-live"] == "true"
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}text-conversion"] == "live"
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}text-layout"] == "bottom-arc"
    assert baseline.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "text-baseline"
    assert baseline.attrib["stroke"] == "none"
    assert " A 34,34 0 0 0 " in baseline.attrib["d"]
    assert text.attrib["font-family"] == "DejaVu Sans"
    assert text.attrib["font-weight"] == "700"
    assert text.attrib["fill"] == "#ffcc33"
    assert text_path.attrib["href"] == "#title-baseline"
    assert text_path.attrib["startOffset"] == "50%"
    assert text_path.attrib["lengthAdjust"] == "spacing"
    assert float(text_path.attrib["textLength"]) == pytest.approx(34 * (3.141592653589793 / 2) * 0.9, abs=1e-5)
    assert text_path.text == "SHARED ORBIT"


def test_construction_guides_make_curved_text_baseline_visible():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
settings:
  construction_guides: true
layers:
  - id: text
    elements:
      - id: title
        type: text
        text: GUIDE ME
        layout: {type: top-arc, radius: 30}
        font: {size: 5, tracking: normal}
        clip: {target: none}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    baseline = _find(root, "path", "title-baseline")
    assert baseline is not None
    assert baseline.attrib["stroke"] == "#00a6ff"
    assert baseline.attrib["stroke-width"] == "0.2"
    assert baseline.attrib["stroke-dasharray"] == "1 1"
    assert baseline.attrib["vector-effect"] == "non-scaling-stroke"
    assert baseline.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "text-baseline"


def test_top_arc_defaults_to_clockwise_sweep():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: text
    elements:
      - id: title
        type: text
        text: TOP ARC
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        layout: {type: top-arc, radius: 30}
        font: {size: 5, tracking: normal}
        clip: {target: none}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    baseline = _find(root, "path", "title-baseline")
    assert baseline is not None
    assert " A 30,30 0 0 1 " in baseline.attrib["d"]


def test_external_path_reference_supports_live_textpath_and_explicit_length():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: paths
    elements:
      - id: route
        type: trajectory
        start: [-20, 0]
        segments: [{line: [20, 0]}]
        clip: {target: none}
      - id: label
        type: text
        text: ALONG THE ROUTE
        layout:
          type: path
          path: route
          length: 40
          bounds: [-20, -1, 20, 1]
          fit: 80%
        font: {size: 4, tracking: auto}
        clip: {target: none}
"""
    )

    result = render_design(design)
    root = ET.fromstring(result.svg)
    text = _find(root, "text", "label-text")
    text_path = text.find(f"{{{SVG_NS}}}textPath") if text is not None else None
    assert text_path is not None
    assert text_path.attrib["href"] == "#label-baseline"
    assert text_path.attrib["{http://www.w3.org/1999/xlink}href"] == "#label-baseline"
    assert text_path.attrib["textLength"] == "32"
    assert not result.warnings


def test_missing_external_path_warns_but_stays_live():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: text
    elements:
      - id: label
        type: text
        text: LABEL
        layout: {type: path, href: '#external-path'}
        font: {size: 4, tracking: auto}
"""
    )
    result = render_design(design)
    root = ET.fromstring(result.svg)
    text = _find(root, "text", "label-text")
    text_path = text.find(f"{{{SVG_NS}}}textPath") if text is not None else None
    assert text_path is not None
    assert text_path.attrib["href"] == "#external-path"
    assert "textLength" not in text_path.attrib
    assert any("baseline '#external-path' was not found" in warning for warning in result.warnings)


def test_basic_band_layout_can_auto_fit_to_physical_width():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: text
    elements:
      - id: motto
        type: text
        text: ONE HORIZON
        layout: {type: lower-band, offset: 20, width: 50, fit: 90%}
        font: {size: 5, tracking: auto}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    text = _find(root, "text", "motto-text")
    assert text is not None
    assert text.attrib["x"] == "0"
    assert text.attrib["y"] == "20"
    assert text.attrib["textLength"] == "45"
    assert text.attrib["lengthAdjust"] == "spacing"


def test_future_warp_and_text_to_path_hooks_fail_explicitly():
    warped = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: text
    elements:
      - id: title
        type: text
        text: WARP ME
        layout: {type: straight}
        warp: {type: envelope}
"""
    )
    with pytest.raises(ValueError, match="future text-to-path/warp"):
        render_design(warped)

    outlined = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: text
    elements:
      - id: title
        type: text
        text: OUTLINE ME
        layout: {type: straight}
        convert_to_path: true
"""
    )
    with pytest.raises(ValueError, match="patchcreator export --text paths"):
        render_design(outlined)
