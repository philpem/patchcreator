import pytest

from patchcreator.config.loader import loads_design
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
          - target: earth
            clearance: 1
      - id: earth
        type: earth
"""
    )

    result = render_design(design, allow_unsupported=True)

    assert any("skipping unsupported component 'earth'" in item for item in result.warnings)
    assert any(
        "could not apply avoidance target 'earth'" in item
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
