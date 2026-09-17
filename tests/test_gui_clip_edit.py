from __future__ import annotations

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.gui import (
    SourceEditError,
    clip_state,
    safe_margin_state,
    set_element_clip,
    set_safe_margin,
)

_SOURCE = """# keep comment
version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin: {percent: 5, min: 2, max: 5}
layers:
  - id: artwork
    elements:
      - id: group
        type: group
        elements:
          - id: child
            type: star
            custom_setting: keep-me
      - id: clipped
        type: star
        clip: {target: custom:child, enabled: false, inset: -0.5}
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


def test_reads_percent_safe_margin_with_clamps():
    state = safe_margin_state(_SOURCE)
    assert state.mode == "percent"
    assert state.value == 5
    assert state.minimum == 2
    assert state.maximum == 5


def test_switching_safe_margin_modes_removes_invalid_fields_and_preserves_source():
    fixed = set_safe_margin(_SOURCE, mode="fixed", value="3")
    assert "# keep comment" in fixed
    state = safe_margin_state(fixed)
    assert state.mode == "fixed"
    assert state.value == 3
    assert state.minimum is None and state.maximum is None
    design = loads_design(fixed)
    assert design.canvas.safe_margin.fixed == 3
    assert design.canvas.safe_margin.percent is None

    percent = set_safe_margin(fixed, mode="percent", value=4, minimum=1.5, maximum=6)
    state = safe_margin_state(percent)
    assert state.mode == "percent"
    assert (state.value, state.minimum, state.maximum) == (4, 1.5, 6)
    loads_design(percent)


def test_safe_margin_rejects_negative_or_reversed_clamps():
    with pytest.raises(SourceEditError, match="must not be negative"):
        set_safe_margin(_SOURCE, mode="fixed", value=-1)
    with pytest.raises(SourceEditError, match="must not exceed"):
        set_safe_margin(_SOURCE, mode="percent", value=5, minimum=6, maximum=2)


def test_clip_state_distinguishes_inherit_omission_from_explicit_mapping():
    inherited = clip_state(_SOURCE, "child")
    assert not inherited.explicit
    assert inherited.target == "inherit"
    assert inherited.enabled
    assert inherited.inset == 0

    clipped = clip_state(_SOURCE, "clipped")
    assert clipped.explicit
    assert clipped.target == "custom:child"
    assert not clipped.enabled
    assert clipped.inset == -0.5


def test_set_clip_handles_custom_disabled_and_inset_outset_without_touching_extras():
    updated = set_element_clip(
        _SOURCE,
        "child",
        explicit=True,
        target="safe-area",
        enabled=False,
        inset=1.25,
    )
    child = _find(loads_design(updated), "child")
    assert child.clip is not None
    assert child.clip.target == "safe-area"
    assert not child.clip.enabled
    assert child.clip.inset == 1.25
    assert child.component_config()["custom_setting"] == "keep-me"

    outset = set_element_clip(updated, "child", explicit=True, target="patch", inset=-2)
    assert _find(loads_design(outset), "child").clip.inset == -2


def test_removing_explicit_clip_restores_inheritance():
    removed = set_element_clip(_SOURCE, "clipped", explicit=False)
    assert not clip_state(removed, "clipped").explicit
    assert _find(loads_design(removed), "clipped").clip is None


def test_clip_edit_rejects_bad_target_and_missing_id():
    with pytest.raises(SourceEditError, match="clip target"):
        set_element_clip(_SOURCE, "child", explicit=True, target="somewhere")
    with pytest.raises(SourceEditError, match="does not exist"):
        clip_state(_SOURCE, "missing")
