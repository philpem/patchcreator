from pathlib import Path

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.profiles import ProfileError, load_profile_catalog, resolve_profile


def test_builtin_profiles_are_available():
    catalog = load_profile_catalog()
    assert "brother-innovis-750e" in catalog.names("machine")
    assert "standard-patch" in catalog.names("intent")
    assert "display-art" in catalog.names("intent")


def test_machine_intent_and_document_overrides_merge():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
profile:
  machine: brother-innovis-750e
  intent: standard-patch
  overrides:
    minimum_gap: 0.9
layers: []
"""
    )
    effective = resolve_profile(design.profile)
    assert effective.constraints.validation_enabled is True
    assert effective.constraints.minimum_stroke_width == pytest.approx(0.6)
    assert effective.constraints.minimum_gap == pytest.approx(0.9)
    assert effective.sources[-1] == "document:profile.overrides"


def test_display_art_disables_validation():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
profile: {intent: display-art}
layers: []
"""
    )
    assert resolve_profile(design.profile).constraints.validation_enabled is False


def test_custom_directory_overrides_builtin(tmp_path: Path):
    (tmp_path / "standard-patch.yaml").write_text(
        """
name: standard-patch
kind: intent
constraints:
  minimum_gap: 1.25
""",
        encoding="utf-8",
    )
    catalog = load_profile_catalog([tmp_path])
    entry = catalog.get("intent", "standard-patch")
    assert entry.profile.constraints.minimum_gap == pytest.approx(1.25)
    assert entry.source.endswith("standard-patch.yaml")


def test_unknown_profile_is_actionable():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
profile: {intent: no-such-profile}
layers: []
"""
    )
    with pytest.raises(ProfileError, match="available"):
        resolve_profile(design.profile)
