from __future__ import annotations

import math
from pathlib import Path

import pytest
import shapefile

from patchcreator.data import DatasetNotInstalledError
from patchcreator.geography import (
    Viewpoint,
    default_simplification_tolerance,
    load_natural_earth_land_rings,
    load_shapefile_rings,
    orthographic_point,
    simplify_polyline,
    visible_polyline_parts,
)


def test_orthographic_projection_orientation_and_visibility():
    view = Viewpoint(latitude=0, longitude=0)

    centre, visible = orthographic_point(0, 0, view, radius=10)
    assert visible
    assert centre == pytest.approx((0, 0))

    east_limb, visible = orthographic_point(90, 0, view, radius=10)
    assert visible
    assert east_limb == pytest.approx((10, 0))

    north_limb, visible = orthographic_point(0, 90, view, radius=10)
    assert visible
    assert north_limb == pytest.approx((0, -10))

    back, visible = orthographic_point(180, 0, view, radius=10)
    assert not visible
    assert back == pytest.approx((0, 0), abs=1e-10)


def test_viewpoint_recentres_requested_location():
    point, visible = orthographic_point(-90, 20, Viewpoint(latitude=20, longitude=-90), radius=15)
    assert visible
    assert point == pytest.approx((0, 0), abs=1e-10)


def test_visible_polyline_inserts_horizon_crossing_on_limb():
    parts = visible_polyline_parts(
        [(0, 0), (120, 0)],
        Viewpoint(),
        radius=10,
    )
    assert len(parts) == 1
    assert parts[0][0] == pytest.approx((0, 0))
    crossing = parts[0][-1]
    assert math.hypot(*crossing) == pytest.approx(10)
    assert crossing[0] > 0


def test_closed_ring_crossing_back_hemisphere_splits_into_visible_chains():
    ring = [(-60, -20), (60, -20), (140, 20), (-140, 20), (-60, -20)]
    parts = visible_polyline_parts(ring, Viewpoint(), radius=20, closed=True)
    assert parts
    for part in parts:
        assert len(part) >= 2
        assert all(math.hypot(x, y) <= 20 + 1e-9 for x, y in part)
        # Mixed front/back rings terminate at the projected limb.
        assert math.hypot(*part[0]) == pytest.approx(20)
        assert math.hypot(*part[-1]) == pytest.approx(20)


def test_fully_visible_closed_ring_stays_closed():
    ring = [(-10, -10), (10, -10), (10, 10), (-10, 10), (-10, -10)]
    parts = visible_polyline_parts(ring, Viewpoint(), radius=10, closed=True)
    assert len(parts) == 1
    assert parts[0][0] == pytest.approx(parts[0][-1])


def test_douglas_peucker_simplifies_in_projected_physical_units():
    points = [(0.0, 0.0), (1.0, 0.01), (2.0, -0.01), (3.0, 0.0)]
    assert simplify_polyline(points, 0.05) == [(0.0, 0.0), (3.0, 0.0)]
    assert simplify_polyline(points, 0.0) == points


def test_simplification_default_responds_to_intent_and_scale():
    standard_30 = default_simplification_tolerance(30, intent="standard-patch")
    standard_80 = default_simplification_tolerance(80, intent="standard-patch")
    small = default_simplification_tolerance(30, intent="small-patch")
    display = default_simplification_tolerance(30, intent="display-art")

    assert standard_80 > standard_30 > 0
    assert small > standard_30
    assert display < standard_30


def test_shapefile_adapter_returns_closed_polygon_parts(tmp_path: Path):
    base = tmp_path / "land"
    writer = shapefile.Writer(str(base), shapeType=shapefile.POLYGON)
    writer.field("id", "N")
    writer.poly(
        [
            [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]],
            [[-2, -2], [-2, 2], [2, 2], [2, -2], [-2, -2]],
        ]
    )
    writer.record(1)
    writer.close()

    rings = load_shapefile_rings(base.with_suffix(".shp"))
    assert len(rings) == 2
    assert all(ring[0] == ring[-1] for ring in rings)
    assert rings[0][0] == pytest.approx((-5, -5))


def test_natural_earth_loader_never_downloads_missing_data(tmp_path: Path):
    with pytest.raises(DatasetNotInstalledError, match="patchcreator data fetch natural-earth-land-110m"):
        load_natural_earth_land_rings(data_root=tmp_path)
