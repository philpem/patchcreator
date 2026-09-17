from __future__ import annotations

from patchcreator.gui import PreviewSession

_SOURCE = """version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin: {fixed: 3}
layers:
  - id: art
    elements:
      - id: star
        type: star
"""


def test_session_safe_margin_round_trip_marks_dirty_and_renders():
    session = PreviewSession(_SOURCE)
    assert session.safe_margin().mode == "fixed"

    updated = session.set_safe_margin(
        mode="percent",
        value="5",
        minimum="2",
        maximum="6",
    )
    state = session.safe_margin()
    assert (state.mode, state.value, state.minimum, state.maximum) == (
        "percent",
        5,
        2,
        6,
    )
    assert session.dirty
    assert updated == session.text
    assert session.render().valid


def test_session_clip_round_trip_handles_explicit_and_inherited():
    session = PreviewSession(_SOURCE)
    assert not session.clip("star").explicit

    updated = session.set_clip(
        "star",
        explicit=True,
        target="safe-area",
        enabled=False,
        inset="-0.75",
    )
    assert updated == session.text
    state = session.clip("star")
    assert state.explicit
    assert state.target == "safe-area"
    assert not state.enabled
    assert state.inset == -0.75
    assert session.render().valid

    session.set_clip("star", explicit=False)
    assert not session.clip("star").explicit
    assert session.render().valid
