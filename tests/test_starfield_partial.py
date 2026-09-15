from pathlib import Path

import pytest

import patchcreator.components.earth as earth_component
from patchcreator.config.loader import load_design, loads_design
from patchcreator.svg.writer import render_design


def test_unresolved_supported_avoidance_target_remains_error_in_strict_render():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: stars
        type: starfield
        seed: 1234
        count: 1
        region: {type: rectangle, x: -10, y: -10, width: 20, height: 20}
        avoidance:
          - target: empty-group
            clearance: 1
      - id: empty-group
        type: group
"""
    )

    with pytest.raises(ValueError, match="empty-group.*no resolved geometry"):
        render_design(design)


def test_skipped_unsupported_avoidance_target_warns_in_partial_render():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: stars
        type: starfield
        seed: 1234
        count: 2
        region: {type: rectangle, x: -10, y: -10, width: 20, height: 20}
        avoidance:
          - target: subject
            clearance: 1
      - id: subject
        type: future-subject
"""
    )

    result = render_design(design, allow_unsupported=True)

    assert any("skipping unsupported component 'subject'" in item for item in result.warnings)
    assert any(
        "could not apply avoidance target 'subject'" in item
        and "skipped in this partial render" in item
        for item in result.warnings
    )


def test_missing_avoidance_target_is_still_an_error_in_partial_render():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: stars
        type: starfield
        seed: 1234
        count: 1
        region: {type: rectangle, x: -10, y: -10, width: 20, height: 20}
        avoidance:
          - target: typo-does-not-exist
"""
    )

    with pytest.raises(ValueError, match="typo-does-not-exist.*does not exist"):
        render_design(design, allow_unsupported=True)


def test_basic_round_patch_renders_supported_earth_orbit_and_text(
    monkeypatch: pytest.MonkeyPatch,
):
    # Keep the regression offline while exercising supported Earth/orbit/text
    # components and starfield avoidance against resolved geometry.
    monkeypatch.setattr(
        earth_component,
        "load_natural_earth_land_rings",
        lambda: (
            (
                (-20.0, -10.0),
                (20.0, -10.0),
                (20.0, 10.0),
                (-20.0, 10.0),
                (-20.0, -10.0),
            ),
        ),
    )

    example = Path(__file__).parents[1] / "examples" / "basic-round-patch.yaml"
    result = render_design(load_design(example), allow_unsupported=True)

    assert "<svg" in result.svg
    assert 'patchcreator:earth-source="natural-earth-land-110m"' in result.svg
    assert 'id="orbit-main-path"' in result.svg
    assert 'id="orbit-main-visible"' in result.svg
    assert 'id="orbit-marker-glyph"' in result.svg
    assert 'id="title-text"' in result.svg
    assert 'id="title-baseline"' in result.svg
    assert not any("skipping unsupported component" in item for item in result.warnings)
    assert not any("could not apply avoidance target 'title'" in item for item in result.warnings)
