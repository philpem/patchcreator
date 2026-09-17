from __future__ import annotations

import xml.etree.ElementTree as ET

from patchcreator.config.loader import loads_design
from patchcreator.svg import export_svg_text
from patchcreator.svg.writer import render_design
from patchcreator.validation import check_svg_text


SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _design(*, shape: str = "circle", enabled: bool = True):
    if shape == "circle":
        canvas = """shape: circle
  diameter: 80"""
    else:
        canvas = """shape: ellipse
  width: 100
  height: 60"""
    return loads_design(
        f"""version: 0.1
canvas:
  {canvas}
  safe_margin:
    fixed: 5
settings:
  construction_guides: {str(enabled).lower()}
layers:
  - id: artwork
    elements: []
"""
    )


def _by_id(root: ET.Element, element_id: str) -> ET.Element:
    for element in root.iter():
        if element.get("id") == element_id:
            return element
    raise AssertionError(f"SVG element {element_id!r} not found")


def test_construction_guides_are_absent_when_disabled():
    root = ET.fromstring(render_design(_design(enabled=False)).svg)
    assert all(element.get("id") != "patchcreator-construction" for element in root.iter())


def test_construction_guides_append_top_inkscape_layer_for_circle():
    root = ET.fromstring(render_design(_design()).svg)
    layer = _by_id(root, "patchcreator-construction")

    assert list(root)[-1] is layer
    assert layer.get(f"{{{INKSCAPE_NS}}}groupmode") == "layer"
    assert layer.get(f"{{{INKSCAPE_NS}}}label") == "PatchCreator Construction"
    assert layer.get(f"{{{PATCHCREATOR_NS}}}construction-role") == "layer"

    patch = _by_id(root, "construction-patch-boundary")
    safe = _by_id(root, "construction-safe-area")
    centre = _by_id(root, "construction-centre")
    horizontal = _by_id(root, "construction-horizontal-axis")
    vertical = _by_id(root, "construction-vertical-axis")

    assert patch.tag == f"{{{SVG_NS}}}circle"
    assert (patch.get("cx"), patch.get("cy"), patch.get("r")) == ("40", "40", "40")
    assert (safe.get("cx"), safe.get("cy"), safe.get("r")) == ("40", "40", "35")
    assert (centre.get("cx"), centre.get("cy"), centre.get("r")) == ("40", "40", "0.8")
    assert (horizontal.get("x1"), horizontal.get("y1"), horizontal.get("x2"), horizontal.get("y2")) == (
        "0",
        "40",
        "80",
        "40",
    )
    assert (vertical.get("x1"), vertical.get("y1"), vertical.get("x2"), vertical.get("y2")) == (
        "40",
        "0",
        "40",
        "80",
    )


def test_ellipse_guides_use_resolved_safe_margin():
    root = ET.fromstring(render_design(_design(shape="ellipse")).svg)
    patch = _by_id(root, "construction-patch-boundary")
    safe = _by_id(root, "construction-safe-area")

    assert patch.tag == f"{{{SVG_NS}}}ellipse"
    assert (patch.get("cx"), patch.get("cy"), patch.get("rx"), patch.get("ry")) == (
        "50",
        "30",
        "50",
        "30",
    )
    assert (safe.get("cx"), safe.get("cy"), safe.get("rx"), safe.get("ry")) == (
        "50",
        "30",
        "45",
        "25",
    )


def test_default_compatibility_export_removes_construction_layer():
    rendered = render_design(_design()).svg
    exported = export_svg_text(rendered)

    assert exported.removed_construction_count == 1
    assert "patchcreator-construction" not in exported.svg
    assert "construction-patch-boundary" not in exported.svg


def test_construction_guides_do_not_create_validation_findings():
    rendered = render_design(_design()).svg
    report = check_svg_text(
        rendered,
        minimum_stroke_width_mm=0.6,
        minimum_feature_dimension_mm=2.0,
        minimum_island_area_mm2=4.0,
        minimum_gap_mm=0.6,
        overlap_diagnostics=True,
    )

    assert report.findings == ()


def test_filled_construction_geometry_is_ignored_by_feature_validation():
    svg = f"""<svg xmlns="{SVG_NS}" xmlns:patchcreator="{PATCHCREATOR_NS}"
        width="20mm" height="20mm" viewBox="0 0 20 20">
      <g patchcreator:construction-role="test">
        <rect id="tiny-guide" x="1" y="1" width="0.2" height="0.2" fill="#000"/>
      </g>
    </svg>"""
    report = check_svg_text(
        svg,
        minimum_feature_dimension_mm=1.0,
        minimum_island_area_mm2=1.0,
    )
    assert report.findings == ()
