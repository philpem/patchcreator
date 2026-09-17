from __future__ import annotations

import math

import pytest

from patchcreator.gui.drag_edit import (
    canvas_size,
    drag_position,
    set_drag_position,
    viewport_to_canvas,
)
from patchcreator.gui.source_edit import SourceEditError, placement_state


_BASE = """version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: marker
        type: star
        custom_field: keep-me  # retained
"""


def test_viewport_mapping_accounts_for_letterboxing():
    assert viewport_to_canvas(
        100,
        0,
        viewport_width=800,
        viewport_height=600,
        canvas_width=80,
        canvas_height=80,
    ) == pytest.approx((0, 0))
    assert viewport_to_canvas(
        700,
        600,
        viewport_width=800,
        viewport_height=600,
        canvas_width=80,
        canvas_height=80,
    ) == pytest.approx((80, 80))
    assert viewport_to_canvas(
        50,
        300,
        viewport_width=800,
        viewport_height=600,
        canvas_width=80,
        canvas_height=80,
    ) is None


def test_default_drag_becomes_cartesian_relative_to_patch_centre():
    position = drag_position(_BASE, "marker", canvas_x=50, canvas_y=30)
    assert position.mode == "cartesian"
    assert (position.first, position.second) == pytest.approx((10, -10))

    updated = set_drag_position(_BASE, "marker", canvas_x=50, canvas_y=30)
    state = placement_state(updated, "marker")
    assert state.mode == "cartesian"
    assert (float(state.first), float(state.second)) == pytest.approx((10, -10))
    assert "custom_field: keep-me" in updated
    assert "# retained" in updated


def test_drag_preserves_cartesian_mode_and_self_anchor():
    source = _BASE.replace(
        "custom_field: keep-me  # retained",
        """position:
          mode: cartesian
          x: 1
          y: 2
          self_anchor: top-left
        custom_field: keep-me  # retained""",
    )
    updated = set_drag_position(source, "marker", canvas_x=44, canvas_y=46)
    state = placement_state(updated, "marker")
    assert state.mode == "cartesian"
    assert (float(state.first), float(state.second)) == pytest.approx((4, 6))
    assert state.self_anchor == "top-left"


def test_polar_drag_uses_zero_up_clockwise_angles_and_physical_radius():
    source = _BASE.replace(
        "custom_field: keep-me  # retained",
        """position: {mode: polar, angle: 0, radius: 1}
        custom_field: keep-me  # retained""",
    )
    right = drag_position(source, "marker", canvas_x=50, canvas_y=40)
    assert right.mode == "polar"
    assert right.first == pytest.approx(90)
    assert right.second == pytest.approx(10)

    upper_left = drag_position(source, "marker", canvas_x=30, canvas_y=30)
    assert upper_left.first == pytest.approx(315)
    assert upper_left.second == pytest.approx(math.sqrt(200))


def test_ellipse_canvas_uses_its_own_centre():
    source = _BASE.replace(
        "canvas: {shape: circle, diameter: 80}",
        "canvas: {shape: ellipse, width: 100, height: 60}",
    )
    size = canvas_size(source)
    assert (size.width, size.height, size.centre) == (100, 60, (50, 30))
    position = drag_position(source, "marker", canvas_x=55, canvas_y=25)
    assert (position.first, position.second) == pytest.approx((5, -5))


@pytest.mark.parametrize("mode", ["relative", "path"])
def test_drag_rejects_position_modes_that_need_semantic_targets(mode: str):
    if mode == "relative":
        position = "{mode: relative, target: other}"
    else:
        position = "{mode: path, path: orbit}"
    source = _BASE.replace(
        "custom_field: keep-me  # retained",
        f"position: {position}\n        custom_field: keep-me  # retained",
    )
    with pytest.raises(SourceEditError, match="supports only default/cartesian/polar"):
        drag_position(source, "marker", canvas_x=40, canvas_y=40)


def test_drag_rejects_non_default_ancestor_coordinate_frame():
    source = """version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: group
        type: group
        frame: {origin: self, reference_radius: 10}
        elements:
          - id: marker
            type: star
"""
    with pytest.raises(SourceEditError, match="non-default ancestor coordinate frame"):
        drag_position(source, "marker", canvas_x=40, canvas_y=40)


def test_inherit_only_ancestor_frame_does_not_block_dragging():
    source = """version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    frame: {origin: inherit}
    elements:
      - id: group
        type: group
        frame: {origin: inherit}
        elements:
          - id: marker
            type: star
"""
    position = drag_position(source, "marker", canvas_x=42, canvas_y=39)
    assert (position.first, position.second) == pytest.approx((2, -1))


def test_invalid_viewport_dimensions_are_rejected():
    with pytest.raises(ValueError, match="finite and positive"):
        viewport_to_canvas(
            0,
            0,
            viewport_width=0,
            viewport_height=100,
            canvas_width=80,
            canvas_height=80,
        )
