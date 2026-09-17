from __future__ import annotations

import math

import pytest

from patchcreator.geometry import SvgPathSamplingError, svg_path_sampler


def test_line_path_has_exact_length_and_direction():
    path = svg_path_sampler("M 1 2 L 4 6")
    assert path.length() == pytest.approx(5.0)
    assert path.sample(0.0).point == pytest.approx((1.0, 2.0))
    assert path.sample(1.0).point == pytest.approx((4.0, 6.0))
    assert path.sample(0.5).tangent == pytest.approx((3.0, 4.0))


def test_relative_commands_and_closed_path_include_closing_segment():
    path = svg_path_sampler("m 10 10 l 10 0 l 0 10 l -10 0 z")
    assert path.length() == pytest.approx(40.0)
    assert path.sample(0.0).point == pytest.approx((10.0, 10.0))
    assert path.sample(1.0).point == pytest.approx((10.0, 10.0))


def test_cubic_and_quadratic_curves_are_measurable():
    cubic = svg_path_sampler("M 0 0 C 0 10 10 10 10 0")
    quadratic = svg_path_sampler("M 0 0 Q 5 10 10 0")

    assert cubic.length() > 10.0
    assert quadratic.length() > 10.0
    assert cubic.sample(0.5).point[1] > 0.0
    assert quadratic.sample(0.5).point[1] > 0.0
    assert cubic.sample(1.0).point == pytest.approx((10.0, 0.0))
    assert quadratic.sample(1.0).point == pytest.approx((10.0, 0.0))


def test_elliptical_arc_is_sampled_in_path_direction():
    path = svg_path_sampler("M 0 0 A 10 5 0 0 1 20 0")
    assert path.length() > 20.0
    assert path.sample(0.0).point == pytest.approx((0.0, 0.0))
    assert path.sample(1.0).point == pytest.approx((20.0, 0.0))
    mid = path.sample(0.5)
    assert math.isfinite(mid.point[0]) and math.isfinite(mid.point[1])
    assert math.hypot(*mid.tangent) > 0.0


def test_multiple_disconnected_subpaths_are_rejected():
    with pytest.raises(SvgPathSamplingError, match="multiple disconnected subpaths"):
        svg_path_sampler("M 0 0 L 10 0 M 20 0 L 30 0")


def test_empty_and_move_only_paths_are_rejected():
    with pytest.raises(SvgPathSamplingError, match="empty"):
        svg_path_sampler("   ")
    with pytest.raises(SvgPathSamplingError, match="no measurable segments"):
        svg_path_sampler("M 0 0")
