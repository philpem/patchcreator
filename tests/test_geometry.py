import pytest

from patchcreator.config.schema import CanvasSpec, SafeMarginSpec
from patchcreator.geometry import AffineTransform, Bounds
from patchcreator.geometry.patch import CanvasGeometry
from patchcreator.geometry.units import (
    parse_angle_degrees,
    parse_length_mm,
    parse_radius,
    polar_to_cartesian,
)


def test_fixed_safe_margin():
    geometry = CanvasGeometry.from_spec(
        CanvasSpec(shape="circle", diameter=80, safe_margin=SafeMarginSpec(fixed=3))
    )
    assert geometry.safe_width == 74
    assert geometry.reference_radius == 40


def test_percent_safe_margin_with_clamps():
    geometry = CanvasGeometry.from_spec(
        CanvasSpec(
            shape="circle",
            diameter=100,
            safe_margin=SafeMarginSpec(percent=10, min=2, max=4),
        )
    )
    assert geometry.safe_margin == 4


def test_polar_zero_is_up_and_clockwise():
    assert polar_to_cartesian(10, 0) == pytest.approx((0, -10))
    assert polar_to_cartesian(10, 90) == pytest.approx((10, 0))
    assert polar_to_cartesian(10, 180) == pytest.approx((0, 10))


def test_relative_radius():
    assert parse_radius("0.75r", 40) == pytest.approx(30)


@pytest.mark.parametrize("parser", [parse_length_mm, parse_angle_degrees])
@pytest.mark.parametrize("value", [None, [], {}])
def test_scalar_unit_parsers_report_invalid_types_as_value_error(parser, value):
    with pytest.raises(ValueError):
        parser(value)


def test_radius_parser_reports_invalid_types_as_value_error():
    with pytest.raises(ValueError):
        parse_radius([], 40)


def test_affine_transform_composition_matches_scene_hierarchy():
    transform = AffineTransform.translation(10, 20) @ AffineTransform.translation(5, 0)
    assert transform.apply((1, 2)) == pytest.approx((16, 22))


def test_rotated_bounds_are_axis_aligned_after_transform():
    bounds = Bounds(0, 0, 10, 4)
    transformed = bounds.transformed(AffineTransform.rotation(90))
    assert transformed.min_x == pytest.approx(-4)
    assert transformed.min_y == pytest.approx(0)
    assert transformed.max_x == pytest.approx(0)
    assert transformed.max_y == pytest.approx(10)


def test_bounds_supply_standard_layout_anchors():
    bounds = Bounds(10, 20, 30, 40)
    assert bounds.anchor("centre") == (20, 30)
    assert bounds.anchor("top") == (20, 20)
    assert bounds.anchor("bottom-right") == (30, 40)
