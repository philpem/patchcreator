from __future__ import annotations

import math
from pathlib import Path

import pytest

import patchcreator.components.earth as earth_component
from patchcreator.cli import main
from patchcreator.components import ComponentRegistry
from patchcreator.config.loader import loads_design
from patchcreator.geography import Viewpoint, orthographic_point, visible_ring_polygons
from patchcreator.svg.writer import render_design


SIMPLE_LAND = (
    (
        (-20.0, -10.0),
        (20.0, -10.0),
        (20.0, 10.0),
        (-20.0, 10.0),
        (-20.0, -10.0),
    ),
)

# Coarse, offline outline preserving the important topology of Natural Earth's
# Antarctic ring: it crosses the antimeridian at the South Pole.  A planar
# unwrapped-orientation test mistakes this for the complement of Antarctica.
POLAR_LAND = (
    (-58.6, -64.2),
    (-72.2, -76.7),
    (-30.1, -80.6),
    (-7.4, -71.3),
    (30.0, -69.9),
    (62.4, -68.0),
    (84.7, -67.2),
    (118.6, -67.2),
    (153.6, -68.9),
    (163.7, -79.1),
    (180.0, -90.0),
    (-180.0, -90.0),
    (-164.2, -84.8),
    (-152.9, -77.5),
    (-108.7, -74.9),
    (-74.9, -73.9),
    (-58.6, -64.2),
)


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    return abs(
        sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(points, points[1:])
        )
        / 2.0
    )


def _polygon_contains(
    points: tuple[tuple[float, float], ...], point: tuple[float, float]
) -> bool:
    x, y = point
    inside = False
    for first, second in zip(points, points[1:]):
        if (first[1] > y) == (second[1] > y):
            continue
        crossing_x = first[0] + (y - first[1]) * (second[0] - first[0]) / (
            second[1] - first[1]
        )
        if x < crossing_x:
            inside = not inside
    return inside


def _path_contains(
    polygons: tuple[tuple[tuple[float, float], ...], ...],
    point: tuple[float, float],
) -> bool:
    return bool(sum(_polygon_contains(polygon, point) for polygon in polygons) % 2)


def _use_simple_land(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        earth_component,
        "load_natural_earth_land_rings",
        lambda: SIMPLE_LAND,
    )


def test_earth_is_a_builtin_component():
    assert "earth" in ComponentRegistry().component_types


def test_globe_renders_editable_sea_land_and_metadata(monkeypatch: pytest.MonkeyPatch):
    _use_simple_land(monkeypatch)
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette:
  sea: "#1358a8"
  land: "#63bd50"
layers:
  - id: art
    elements:
      - id: earth
        type: earth
        diameter: 30
        viewpoint: {latitude: 10deg, longitude: -20deg}
        style: {sea: sea, land: land}
"""
    )

    result = render_design(design)

    assert 'id="earth-sea"' in result.svg
    assert 'id="earth-land"' in result.svg
    assert 'fill="#1358a8"' in result.svg
    assert 'fill="#63bd50"' in result.svg
    assert 'patchcreator:earth-render="globe"' in result.svg
    assert 'patchcreator:earth-source="natural-earth-land-110m"' in result.svg
    assert not result.warnings


def test_outline_only_and_mapping_strokes_are_supported(monkeypatch: pytest.MonkeyPatch):
    _use_simple_land(monkeypatch)
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette:
  white: "#ffffff"
layers:
  - id: art
    elements:
      - id: earth
        type: earth
        diameter: 30
        style:
          sea: null
          land: null
          coastline: {colour: white, width: 0.7}
          outline: {colour: white, width: 0.5}
          atmosphere: {colour: white, width: 0.3}
"""
    )

    result = render_design(design)

    assert 'id="earth-sea"' not in result.svg
    assert 'id="earth-land"' in result.svg
    assert 'fill="none"' in result.svg
    assert 'stroke-width="0.7"' in result.svg
    assert 'id="earth-outline"' in result.svg
    assert 'id="earth-atmosphere"' in result.svg


def test_horizon_mode_exposes_named_anchors_and_clips_cap(monkeypatch: pytest.MonkeyPatch):
    _use_simple_land(monkeypatch)
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: earth
        type: earth
        render: horizon
        diameter: 40
        visible_height: 8
        position:
          mode: cartesian
          x: 0
          y: 30
          self_anchor: horizon-centre
      - id: marker
        type: star
        glyph: dot
        size: 2
        position:
          mode: relative
          target: earth
          target_anchor: apex
          self_anchor: centre
"""
    )

    result = render_design(design)

    assert 'patchcreator:earth-render="horizon"' in result.svg
    assert 'id="earth-horizon-clip-earth"' in result.svg
    assert 'id="earth-artwork"' in result.svg
    assert 'id="marker-glyph"' in result.svg


def test_visible_ring_polygons_close_crossing_land_along_limb():
    ring = [
        (-60, -20),
        (60, -20),
        (140, 20),
        (-140, 20),
        (-60, -20),
    ]
    polygons = visible_ring_polygons(
        ring,
        Viewpoint(),
        radius=20,
        limb_step_degrees=10,
    )

    assert polygons
    for polygon in polygons:
        assert polygon[0] == pytest.approx(polygon[-1])
        assert len(polygon) >= 4
        assert all(math.hypot(x, y) <= 20 + 1e-8 for x, y in polygon)
        # A horizon-crossing polygon contains an arc with multiple points on the limb.
        on_limb = [point for point in polygon if math.hypot(*point) == pytest.approx(20)]
        assert len(on_limb) >= 2


@pytest.mark.parametrize("latitude", [-1, 0, 1, 20])
def test_polar_ring_does_not_invert_equatorial_globe(latitude: float):
    radius = 10.0
    polygons = visible_ring_polygons(
        POLAR_LAND,
        Viewpoint(latitude=latitude, longitude=-90),
        radius=radius,
    )

    assert polygons
    assert all(_polygon_area(polygon) < math.pi * radius**2 / 2 for polygon in polygons)
    assert not _path_contains(polygons, (0.0, 0.0))


def test_polar_ring_classifies_visible_land_and_ocean():
    viewpoint = Viewpoint(latitude=0, longitude=-90)
    polygons = visible_ring_polygons(POLAR_LAND, viewpoint, radius=10)
    antarctica, visible = orthographic_point(-90, -80, viewpoint, radius=10)

    assert visible
    assert _path_contains(polygons, antarctica)
    assert not _path_contains(polygons, (0.0, 0.0))


def test_multiple_visible_chains_use_one_whole_disc_parity_correction(monkeypatch):
    # This band contains the camera but crosses the horizon four times.  Its two
    # small coastline closures need one whole-disc toggle to reconstruct the
    # connected visible interior under SVG's even-odd fill rule.
    band = tuple((longitude, -30.0) for longitude in range(-120, 121, 30)) + tuple(
        (longitude, 30.0) for longitude in range(120, -121, -30)
    )
    band += (band[0],)

    # Python 3.12 made built-in sum more accurate. The spherical result must not
    # depend on that interpreter detail: this emulates Python 3.11's sequential
    # accumulation, which exposed an antipodal triangle-fan singularity here.
    def sequential_sum(values, start=0):
        result = start
        for value in values:
            result += value
        return result

    monkeypatch.setattr("builtins.sum", sequential_sum)

    polygons = visible_ring_polygons(
        band,
        Viewpoint(),
        radius=10,
        limb_step_degrees=5,
    )

    assert len(polygons) == 3
    assert _path_contains(polygons, (0.0, 0.0))
    assert not _path_contains(polygons, (0.0, -9.0))


def test_antimeridian_ring_contains_dateline_viewpoint():
    ring = (
        (170.0, -10.0),
        (-170.0, -10.0),
        (-170.0, 10.0),
        (170.0, 10.0),
        (170.0, -10.0),
    )

    polygons = visible_ring_polygons(
        ring,
        Viewpoint(latitude=0, longitude=180),
        radius=10,
    )

    assert _path_contains(polygons, (0.0, 0.0))


def test_render_cli_reports_missing_natural_earth_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    data_root = tmp_path / "empty-data-cache"
    monkeypatch.setenv("PATCHCREATOR_DATA_DIR", str(data_root))
    design = tmp_path / "earth.yaml"
    design.write_text(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - {id: earth, type: earth, diameter: 30}
""",
        encoding="utf-8",
    )

    assert main(["render", str(design)]) == 2
    captured = capsys.readouterr()
    assert "patchcreator data fetch natural-earth-land-110m" in captured.err
    assert "Traceback" not in captured.err
    assert not design.with_suffix(".svg").exists()
