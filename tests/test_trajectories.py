from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from patchcreator.components import ComponentRegistry
from patchcreator.config.loader import loads_design
from patchcreator.geometry import CompoundPath, CubicBezierPath, EllipsePath, LinePath
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design


def test_measurable_path_geometry_and_compound_bounds():
    line = LinePath((0.0, 0.0), (3.0, 4.0))
    assert line.length() == pytest.approx(5.0)
    assert line.sample(0.5).point == pytest.approx((1.5, 2.0))

    curve = CubicBezierPath(
        (3.0, 4.0),
        (5.0, 8.0),
        (8.0, 8.0),
        (10.0, 4.0),
    )
    assert curve.sample(0.0).point == pytest.approx((3.0, 4.0))
    assert curve.sample(1.0).point == pytest.approx((10.0, 4.0))
    assert curve.length() > 7.0
    assert curve.bounds.max_y > 4.0

    path = CompoundPath((line, curve))
    assert path.length() == pytest.approx(line.length() + curve.length())
    assert path.bounds.min_x == pytest.approx(0.0)
    assert path.bounds.min_y == pytest.approx(0.0)
    assert path.bounds.max_x == pytest.approx(10.0)
    assert path.bounds.max_y == pytest.approx(curve.bounds.max_y)


def test_ellipse_path_uses_patch_polar_convention_and_rotation():
    ellipse = EllipsePath(10.0, 5.0)
    assert ellipse.sample(0.0).point == pytest.approx((0.0, -5.0))
    assert ellipse.sample(0.25).point == pytest.approx((10.0, 0.0), abs=1e-6)
    assert ellipse.sample(0.5).point == pytest.approx((0.0, 5.0), abs=1e-6)
    assert ellipse.length() > 2.0 * math.pi * 5.0
    assert ellipse.length() < 2.0 * math.pi * 10.0

    rotated = EllipsePath(10.0, 5.0, rotation_degrees=90.0)
    assert rotated.sample(0.0).point == pytest.approx((5.0, 0.0), abs=1e-6)
    assert rotated.bounds.width == pytest.approx(10.0)
    assert rotated.bounds.height == pytest.approx(20.0)


def test_trajectory_renders_bezier_halo_dash_arrow_and_scene_path():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette: {route: '#ffcc33', halo: '#111111'}
layers:
  - id: paths
    elements:
      - id: route
        type: trajectory
        start: [-15, 5]
        segments:
          - line: [-5, 0]
          - cubic:
              control1: [0, -8]
              control2: [10, -8]
              to: [15, 0]
        stroke:
          colour: route
          width: 0.8
          dash: [2, 1]
        halo:
          colour: halo
          width: 1.8
        arrowheads: end
        clip: {target: none}
      - id: traveller
        type: star
        glyph: dot
        size: 2
        clip: {target: none}
        position:
          mode: path
          path: route
          at: 0.5
          orient: tangent
"""
    )

    result = render_design(design)
    root = ET.fromstring(result.svg)
    route = root.find(f".//{{{SVG_NS}}}g[@id='route']")
    assert route is not None
    assert route.attrib[f"{{{PATCHCREATOR_NS}}}path-kind"] == "trajectory"
    assert float(route.attrib[f"{{{PATCHCREATOR_NS}}}path-length-mm"]) > 30

    halo = root.find(f".//{{{SVG_NS}}}path[@id='route-halo']")
    path = root.find(f".//{{{SVG_NS}}}path[@id='route-path']")
    traveller = root.find(f".//{{{SVG_NS}}}g[@id='traveller']")
    marker = root.find(f".//{{{SVG_NS}}}marker[@id='trajectory-arrow-route']")
    assert halo is not None and path is not None and traveller is not None and marker is not None
    assert path.attrib["d"].startswith("M -15,5 L -5,0 C")
    assert path.attrib["stroke"] == "#ffcc33"
    assert path.attrib["stroke-dasharray"] == "2 1"
    assert path.attrib["marker-end"] == "url(#trajectory-arrow-route)"
    assert halo.attrib["stroke-width"] == "1.8"
    assert "transform" in traveller.attrib


def test_orbit_is_builtin_and_supports_relative_and_path_following_placement():
    assert {"orbit", "trajectory"}.issubset(ComponentRegistry().component_types)
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: reference
        type: star
        glyph: dot
        size: 2
        clip: {target: none}
        position: {mode: cartesian, x: 8, y: -4}
      - id: orbit
        type: orbit
        radius_x: 10
        radius_y: 5
        rotation: 20deg
        phase: 90deg
        clip: {target: none}
        position:
          mode: relative
          target: reference
          target_anchor: centre
          self_anchor: orbit-centre
      - id: marker
        type: star
        glyph: dot
        size: 1.5
        clip: {target: none}
        position:
          mode: path
          path: orbit
          at: 25%
          orient: tangent
"""
    )

    root = ET.fromstring(render_design(design).svg)
    orbit_group = root.find(f".//{{{SVG_NS}}}g[@id='orbit']")
    orbit_path = root.find(f".//{{{SVG_NS}}}path[@id='orbit-path']")
    marker = root.find(f".//{{{SVG_NS}}}g[@id='marker']")
    assert orbit_group is not None and orbit_path is not None and marker is not None
    assert orbit_group.attrib[f"{{{PATCHCREATOR_NS}}}path-kind"] == "orbit"
    assert orbit_group.attrib[f"{{{PATCHCREATOR_NS}}}orbit-phase-deg"] == "90"
    assert orbit_path.attrib["transform"] == "rotate(20)"
    assert "transform" in orbit_group.attrib
    assert "transform" in marker.attrib


def test_halo_must_be_wider_than_main_stroke():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: paths
    elements:
      - id: route
        type: trajectory
        start: [0, 0]
        segments: [{line: [10, 0]}]
        stroke: {width: 1.0}
        halo: {width: 0.8}
"""
    )

    with pytest.raises(ValueError, match="halo width must exceed"):
        render_design(design)
