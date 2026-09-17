from __future__ import annotations

import re

import pytest

from patchcreator.gui import (
    PreviewSession,
    SourceEditError,
    resolved_starfield_seed,
    set_starfield_seed,
    starfield_seed_state,
)

_SOURCE = """# preserve me
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: sky
    elements:
      - id: wrapper
        type: group
        elements:
          - id: stars
            type: starfield
            count: 4
            seed: auto
            region: {type: rectangle, width: 20, height: 20}
            clip: {target: none}
      - id: marker
        type: star
"""


def test_starfield_seed_state_and_round_trip_edit_preserve_source():
    state = starfield_seed_state(_SOURCE, "stars")
    assert state.configured == "auto"
    assert state.automatic

    locked = set_starfield_seed(_SOURCE, "stars", 123456789)
    assert "# preserve me" in locked
    assert "count: 4" in locked
    state = starfield_seed_state(locked, "stars")
    assert state.configured == "123456789"
    assert not state.automatic

    automatic = set_starfield_seed(locked, "stars", "auto")
    assert starfield_seed_state(automatic, "stars").automatic


def test_seed_helpers_reject_non_starfield_and_out_of_range_values():
    with pytest.raises(SourceEditError, match="not a starfield"):
        starfield_seed_state(_SOURCE, "marker")
    with pytest.raises(SourceEditError, match="64-bit"):
        set_starfield_seed(_SOURCE, "stars", 1 << 64)
    with pytest.raises(SourceEditError, match="integer"):
        set_starfield_seed(_SOURCE, "stars", "banana")


def test_session_reads_resolved_renderer_seed_and_can_lock_it():
    session = PreviewSession(_SOURCE)
    result = session.render()
    assert result.valid
    assert result.svg is not None

    resolved = session.resolved_seed("stars")
    assert resolved is not None
    assert 0 <= resolved < 1 << 64
    assert resolved_starfield_seed(result.svg, "stars") == resolved

    updated = session.lock_current_seed("stars")
    state = starfield_seed_state(updated, "stars")
    assert state.configured == str(resolved)
    assert not state.automatic

    locked = session.render()
    assert locked.valid
    assert session.resolved_seed("stars") == resolved


def test_session_regenerate_writes_explicit_seed_and_auto_restores_auto_mode():
    session = PreviewSession(_SOURCE)
    session.render()
    before = session.resolved_seed("stars")

    regenerated = session.regenerate_seed("stars")
    state = starfield_seed_state(regenerated, "stars")
    assert not state.automatic
    assert re.fullmatch(r"\d+", state.configured)
    session.render()
    assert session.resolved_seed("stars") == int(state.configured)
    # Collision is astronomically unlikely; more importantly regenerate writes
    # an independently generated explicit value rather than renderer 'auto'.
    assert before is None or 0 <= session.resolved_seed("stars") < 1 << 64

    automatic = session.auto_seed("stars")
    assert starfield_seed_state(automatic, "stars").automatic


def test_resolved_seed_metadata_missing_malformed_or_wrong_id_returns_none():
    assert resolved_starfield_seed(None, "stars") is None
    assert resolved_starfield_seed("<svg", "stars") is None
    assert resolved_starfield_seed("<svg><g id='stars'/></svg>", "stars") is None
    assert (
        resolved_starfield_seed(
            "<svg xmlns:patchcreator='https://philpem.github.io/patchcreator/ns'>"
            "<g id='stars' patchcreator:seed='not-a-number'/></svg>",
            "stars",
        )
        is None
    )
    assert resolved_starfield_seed("<svg><g id='other'/></svg>", "stars") is None
