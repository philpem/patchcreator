from __future__ import annotations

import math
from pathlib import Path

import pytest

import patchcreator.components.earth as earth_component
from patchcreator.cli import main
from patchcreator.components import ComponentRegistry
from patchcreator.config.loader import loads_design
from patchcreator.geography import Viewpoint, visible_ring_polygons
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
