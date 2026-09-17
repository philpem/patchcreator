from __future__ import annotations

import pytest

from patchcreator.gui import SourceEditError, placement_state, set_element_position
from patchcreator.config.loader import loads_design

_SOURCE = """# keep this header comment
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    label: Artwork
    elements:
      - id: group
        type: group
        note: keep-extra-field
        elements:
          - id: child
            type: star
            position: {mode: cartesian, x: 12, y: 18, self_anchor: origin}
            custom_setting: 123
      - id: polar
        type: star
        position:
          mode: polar
          angle: 45deg
          radius: 50%
"""


def _find(design, element_id: str):
    def walk(elements):
        for element in elements:
            if element.id == element_id:
                return element
            found = walk(element.elements)
            if found is not None:
                return found
        return None

    for layer in design.layers:
        found = walk(layer.elements)
        if found is not None:
            return found
    raise AssertionError(element_id)


def test_reads_nested_cartesian_and_polar_position_state():
    child = placement_state(_SOURCE, "child")
    assert child.mode == "cartesian"
    assert child.first == "12"
    assert child.second == "18"
    assert child.self_anchor == "origin"

    polar = placement_state(_SOURCE, "polar")
    assert polar.mode == "polar"
    assert polar.first == "45deg"
    assert polar.second == "50%"


def test_updates_nested_cartesian_position_and_preserves_unrelated_source():
    updated = set_element_position(
        _SOURCE,
        "child",
        mode="cartesian",
        first="21.5",
        second="7",
    )

    assert "# keep this header comment" in updated
    assert "note: keep-extra-field" in updated
    assert "custom_setting: 123" in updated
    design = loads_design(updated)
    child = _find(design, "child")
    assert child.position.mode == "cartesian"
    assert child.position.x == 21.5
    assert child.position.y == 7
    assert child.position.self_anchor == "origin"


def test_switches_cartesian_to_polar_without_touching_component_fields():
    updated = set_element_position(
        _SOURCE,
        "child",
        mode="polar",
        first="135deg",
        second="75%",
    )

    design = loads_design(updated)
    child = _find(design, "child")
    assert child.position.mode == "polar"
    assert child.position.angle == "135deg"
    assert child.position.radius == "75%"
    assert child.position.self_anchor == "origin"
    assert child.component_config()["custom_setting"] == 123


def test_adds_position_to_previously_unpositioned_element():
    updated = set_element_position(
        _SOURCE,
        "group",
        mode="cartesian",
        first="10",
        second="20",
    )
    state = placement_state(updated, "group")
    assert (state.mode, state.first, state.second) == ("cartesian", "10", "20")


def test_missing_or_unsupported_element_position_is_explicit():
    with pytest.raises(SourceEditError, match="does not exist"):
        placement_state(_SOURCE, "missing")

    relative = _SOURCE.replace(
        "position: {mode: cartesian, x: 12, y: 18, self_anchor: origin}",
        "position: {mode: relative, target: polar}",
    )
    with pytest.raises(SourceEditError, match="supports only cartesian/polar"):
        placement_state(relative, "child")


def test_empty_editor_value_is_rejected():
    with pytest.raises(SourceEditError, match="must not be empty"):
        set_element_position(
            _SOURCE,
            "child",
            mode="cartesian",
            first="",
            second="2",
        )
