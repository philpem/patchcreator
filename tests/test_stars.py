import re
import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.svg.writer import SVG_NS, render_design

PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _field_group(root, field_id="stars"):
    return root.find(f".//{{{SVG_NS}}}g[@id='{field_id}']")


def _generated_stars(root, field_id="stars"):
    group = _field_group(root, field_id)
    assert group is not None
    return [
        child
        for child in list(group)
        if child.tag == f"{{{SVG_NS}}}g" and child.attrib.get("id", "").startswith(f"{field_id}-star-")
    ]


@pytest.mark.parametrize(
    "glyph,tag",
    [
        ("dot", "circle"),
        ("four-point", "polygon"),
        ("four-point-narrow", "polygon"),
        ("five-point", "polygon"),
        ("eight-point", "polygon"),
    ],
)
def test_semantic_star_glyphs_render_as_editable_svg(glyph, tag):
    design = loads_design(
        f"""
version: 0.1
canvas: {{shape: circle, diameter: 80}}
palette: {{white: '#ffffff'}}
layers:
  - id: art
    elements:
      - id: symbol
        type: star
        glyph: {glyph}
        size: 4
        fill: white
        clip: {{target: none}}
        position: {{mode: cartesian, x: 0, y: 0}}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    group = root.find(f".//{{{SVG_NS}}}g[@id='symbol']")
    assert group is not None
    assert group.attrib["transform"] == "matrix(1 0 0 1 40 40)"
    assert group.find(f"{{{SVG_NS}}}{tag}") is not None


def test_fixed_seed_is_deterministic_and_embedded():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin: {fixed: 3}
layers:
  - id: background
    elements:
      - id: stars
        type: starfield
        seed: 123456789
        count: 10
        size: 1.5
        glyphs: [dot, four-point, five-point]
        region:
          type: annular-sector
          inner_radius: 0.2r
          outer_radius: 0.8r
          angle_start: 285deg
          angle_end: 75deg
"""
    )
    first = render_design(design)
    second = render_design(design)
    assert first.svg == second.svg
    assert not any("generated seed" in warning for warning in first.warnings)

    root = ET.fromstring(first.svg)
    field = _field_group(root)
    assert field is not None
    assert field.attrib[f"{{{PATCHCREATOR_NS}}}seed"] == "123456789"
    assert field.attrib[f"{{{PATCHCREATOR_NS}}}placed-count"] == "10"
    assert len(_generated_stars(root)) == 10


def test_auto_seed_is_reported_and_can_be_reused():
    auto_design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80, safe_margin: {fixed: 3}}
layers:
  - id: background
    elements:
      - id: stars
        type: starfield
        seed: auto
        count: 4
        size: 1.5
        region: {type: rectangle, x: -20, y: -20, width: 40, height: 40}
"""
    )
    result = render_design(auto_design)
    root = ET.fromstring(result.svg)
    field = _field_group(root)
    seed = int(field.attrib[f"{{{PATCHCREATOR_NS}}}seed"])
    warning = next(w for w in result.warnings if "generated seed" in w)
    assert str(seed) in warning

    fixed_design = loads_design(
        f"""
version: 0.1
canvas: {{shape: circle, diameter: 80, safe_margin: {{fixed: 3}}}}
layers:
  - id: background
    elements:
      - id: stars
        type: starfield
        seed: {seed}
        count: 4
        size: 1.5
        region: {{type: rectangle, x: -20, y: -20, width: 40, height: 40}}
"""
    )
    fixed = render_design(fixed_design)
    fixed_root = ET.fromstring(fixed.svg)
    assert [star.attrib["transform"] for star in _generated_stars(root)] == [
        star.attrib["transform"] for star in _generated_stars(fixed_root)
    ]


def test_starfield_avoids_later_sibling_resolved_bounds_with_clearance():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80, safe_margin: {fixed: 3}}
layers:
  - id: art
    elements:
      - id: stars
        type: starfield
        seed: 42
        count: 30
        size: 1
        minimum_separation: 0
        region: {type: rectangle, x: -15, y: -15, width: 30, height: 30}
        avoidance:
          - target: semantic
            clearance: 3
      - id: semantic
        type: star
        glyph: dot
        size: 8
        clip: {target: none}
        position: {mode: cartesian, x: 0, y: 0}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    translations = []
    for star in _generated_stars(root):
        match = re.fullmatch(r"translate\(([-0-9.]+) ([-0-9.]+)\)", star.attrib["transform"])
        assert match
        translations.append((float(match.group(1)), float(match.group(2))))

    # Semantic target occupies x/y 36..44 in world coordinates. With 3 mm
    # clearance and 0.5 mm decorative-star radius, generated centres must stay
    # outside 32.5..47.5 on at least one axis.
    for x, y in translations:
        assert not (32.5 <= x <= 47.5 and 32.5 <= y <= 47.5)


def test_rectangle_and_polygon_regions_are_supported():
    for region in (
        "{type: rectangle, x: -10, y: -8, width: 20, height: 16}",
        "{type: polygon, points: [[-12, -8], [12, -8], [0, 12]]}",
    ):
        design = loads_design(
            f"""
version: 0.1
canvas: {{shape: circle, diameter: 80, safe_margin: {{fixed: 3}}}}
layers:
  - id: background
    elements:
      - id: stars
        type: starfield
        seed: 99
        count: 8
        size: 1
        region: {region}
"""
        )
        root = ET.fromstring(render_design(design).svg)
        assert len(_generated_stars(root)) == 8


def test_overfull_starfield_reports_partial_placement():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80, safe_margin: {fixed: 3}}
layers:
  - id: background
    elements:
      - id: stars
        type: starfield
        seed: 1
        count: 20
        size: 4
        minimum_separation: 3
        max_attempts: 40
        region: {type: rectangle, x: -3, y: -3, width: 6, height: 6}
"""
    )
    result = render_design(design)
    assert any("placed" in warning and "of 20" in warning for warning in result.warnings)
