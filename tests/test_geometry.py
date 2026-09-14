import pytest

from patchcreator.config.schema import CanvasSpec, SafeMarginSpec
from patchcreator.geometry.patch import CanvasGeometry
from patchcreator.geometry.units import parse_radius, polar_to_cartesian


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
