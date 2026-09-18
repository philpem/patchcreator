from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.svg import export_svg_text
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design


def test_generic_trajectory_is_physically_split_around_named_object_bounds():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: target
        type: star
        glyph: dot
        size: 10
        clip: {target: none}
        position: {mode: cartesian, x: 0, y: 0}
      - id: route
        type: trajectory
        start: [-20, 0]
        segments: [{line: [20, 0]}]
        stroke: {width: 1}
        clip: {target: none}
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        occlusion:
          behind: target
          gap: 1
          shape: bounds
          samples: 64
"""
    )

    root = ET.fromstring(render_design(design).svg)
    source = root.find(f".//{{{SVG_NS}}}path[@id='route-path']")
    visible = root.find(f".//{{{SVG_NS}}}g[@id='route-visible']")
    route_group = root.find(f".//{{{SVG_NS}}}g[@id='route']")
    assert source is not None and visible is not None and route_group is not None
    assert "display:none" in source.attrib["style"]
    assert source.attrib[f"{{{PATCHCREATOR_NS}}}construction-source"] == "true"
    assert source.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "trajectory-source-path"
    assert route_group.attrib[f"{{{PATCHCREATOR_NS}}}occlusion-mode"] == "geometry-split"
    assert route_group.attrib[f"{{{PATCHCREATOR_NS}}}occlusion-targets"] == "target"

    paths = visible.findall(f"{{{SVG_NS}}}path")
    assert len(paths) == 2
    # The target is centred at local x=0 with 5 mm radius plus 1 mm gap.
    # The split boundary is refined between samples, rather than snapping to the
    # coarse 64-sample grid.
    assert paths[0].attrib["d"].startswith("M -20,0")
    assert paths[0].attrib["d"].endswith("-6,0")
    assert paths[1].attrib["d"].startswith("M 6,0")
    assert paths[1].attrib["d"].endswith("20,0")


def test_construction_guides_show_original_occluded_trajectory_source_path():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
settings:
  construction_guides: true
layers:
  - id: art
    elements:
      - id: target
        type: star
        glyph: dot
        size: 10
        clip: {target: none}
      - id: route
        type: trajectory
        start: [-20, 0]
        segments: [{line: [20, 0]}]
        stroke: {width: 1}
        arrowheads: end
        clip: {target: none}
        position: {mode: cartesian, x: 0, y: 0, self_anchor: origin}
        occlusion: {behind: target, shape: bounds}
"""
    )

    rendered = render_design(design).svg
    root = ET.fromstring(rendered)
    source = root.find(f".//{{{SVG_NS}}}path[@id='route-path']")
    visible = root.find(f".//{{{SVG_NS}}}g[@id='route-visible']")
    assert source is not None and visible is not None
    assert source.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "trajectory-source-path"
    assert "style" not in source.attrib or "display:none" not in source.attrib["style"]
    assert source.attrib["stroke"] == "#00a6ff"
    assert source.attrib["stroke-width"] == "0.2"
    assert source.attrib["stroke-dasharray"] == "1 1"
    assert "marker-end" not in source.attrib

    compat = export_svg_text(rendered)
    assert "route-path" not in compat.svg
    assert "route-visible" in compat.svg


def test_orbit_near_side_remains_visible_while_far_side_goes_behind_occluder():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: body
        type: star
        glyph: dot
        size: 12
        clip: {target: none}
        position: {mode: cartesian, x: 0, y: 0}
      - id: orbit
        type: orbit
        radius_x: 10
        radius_y: 4
        clip: {target: none}
        position:
          mode: relative
          target: body
          target_anchor: centre
          self_anchor: orbit-centre
        occlusion:
          behind: body
          shape: ellipse
          near_side: bottom
          samples: 128
"""
    )

    root = ET.fromstring(render_design(design).svg)
    source = root.find(f".//{{{SVG_NS}}}path[@id='orbit-path']")
    visible = root.find(f".//{{{SVG_NS}}}g[@id='orbit-visible']")
    orbit_group = root.find(f".//{{{SVG_NS}}}g[@id='orbit']")
    assert source is not None and visible is not None and orbit_group is not None
    assert "display:none" in source.attrib["style"]
    assert source.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "orbit-source-path"
    assert orbit_group.attrib[f"{{{PATCHCREATOR_NS}}}orbit-near-side-deg"] == "180"

    rendered = " ".join(path.attrib["d"] for path in visible.findall(f"{{{SVG_NS}}}path"))
    # Bottom is explicitly the near side and is inside the body's ellipse, so it
    # remains. The corresponding top point is on the far side and is removed.
    assert "0,4" in rendered
    assert "0,-4" not in rendered


def test_occlusion_target_skipped_in_partial_render_warns_and_leaves_source_path():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: route
        type: trajectory
        start: [0, 0]
        segments: [{line: [10, 0]}]
        clip: {target: none}
        occlusion: {behind: future-subject}
      - id: future-subject
        type: not-built-yet
"""
    )

    result = render_design(design, allow_unsupported=True)
    root = ET.fromstring(result.svg)
    source = root.find(f".//{{{SVG_NS}}}path[@id='route-path']")
    assert source is not None
    assert "style" not in source.attrib or "display:none" not in source.attrib["style"]
    assert root.find(f".//{{{SVG_NS}}}g[@id='route-visible']") is None
    assert any("could not apply occlusion target 'future-subject'" in warning for warning in result.warnings)


def test_missing_occlusion_target_is_an_error_even_in_partial_render():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: route
        type: trajectory
        start: [0, 0]
        segments: [{line: [10, 0]}]
        occlusion: {behind: typo-target}
"""
    )

    with pytest.raises(ValueError, match="typo-target.*does not exist"):
        render_design(design, allow_unsupported=True)


def test_near_side_is_rejected_for_non_orbit_trajectory():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: body
        type: star
        glyph: dot
        size: 4
      - id: route
        type: trajectory
        start: [0, 0]
        segments: [{line: [10, 0]}]
        occlusion: {behind: body, near_side: bottom}
"""
    )

    with pytest.raises(ValueError, match="near_side is only meaningful"):
        render_design(design)
