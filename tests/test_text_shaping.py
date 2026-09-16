from __future__ import annotations

from pathlib import Path

import pytest

from patchcreator.text import (
    FontRequest,
    FontResolutionError,
    open_ttfont,
    resolve_font,
    shape_text,
)


_SYSTEM_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)


def _system_font() -> Path:
    for path in _SYSTEM_FONT_CANDIDATES:
        if path.is_file():
            return path
    pytest.skip("no known redistributable system test font is installed")


def test_explicit_font_path_is_reproducible_and_exposes_fonttools_metrics():
    path = _system_font()
    resolved = resolve_font(FontRequest(family="requested-name-is-ignored-by-path", path=path))

    assert resolved.face.path == path.resolve()
    assert resolved.face.units_per_em > 0
    assert resolved.face.family
    assert resolved.substituted

    font = open_ttfont(resolved)
    try:
        assert font["head"].unitsPerEm == resolved.face.units_per_em
        assert ".notdef" in font.getGlyphSet()
    finally:
        font.close()


def test_family_discovery_can_be_limited_to_an_explicit_directory():
    path = _system_font()
    explicit = resolve_font(FontRequest(path=path))
    discovered = resolve_font(
        FontRequest(family=explicit.face.family, weight=explicit.face.weight, style=explicit.face.style),
        search_directories=[path.parent],
    )

    assert discovered.face.family == explicit.face.family
    assert discovered.face.style == explicit.face.style
    assert discovered.face.weight == explicit.face.weight
    assert not discovered.substituted


def test_nearest_face_reports_weight_and_style_substitution():
    path = _system_font()
    resolved = resolve_font(FontRequest(path=path, family="sans-serif", weight=900, style="italic"))

    assert resolved.substituted
    assert any("weight" in note for note in resolved.substitutions)
    assert any("style" in note for note in resolved.substitutions)


def test_missing_explicit_font_has_actionable_error(tmp_path: Path):
    missing = tmp_path / "missing.ttf"
    with pytest.raises(FontResolutionError, match="font file does not exist"):
        resolve_font(FontRequest(path=missing))


def test_missing_family_does_not_silently_pick_unrelated_font():
    path = _system_font()
    with pytest.raises(FontResolutionError, match="could not resolve font family"):
        resolve_font(
            FontRequest(family="PatchCreator Definitely Missing Font"),
            search_directories=[path.parent],
        )


def test_harfbuzz_shapes_latin_text_and_exposes_glyph_metrics():
    resolved = resolve_font(FontRequest(path=_system_font()))
    run = shape_text("AV Patch", resolved)

    assert run.text == "AV Patch"
    assert run.units_per_em == resolved.face.units_per_em
    assert run.direction == "ltr"
    assert run.glyphs
    assert run.x_advance > 0
    assert all(glyph.glyph_id >= 0 for glyph in run.glyphs)
    assert all(glyph.glyph_name for glyph in run.glyphs)

    font = open_ttfont(resolved)
    try:
        glyph_set = font.getGlyphSet()
        assert all(glyph.glyph_name in glyph_set for glyph in run.glyphs)
    finally:
        font.close()


def test_harfbuzz_guesses_rtl_script_properties():
    resolved = resolve_font(FontRequest(path=_system_font()))
    run = shape_text("سلام", resolved)

    assert run.direction == "rtl"
    assert run.glyphs
    assert run.x_advance > 0


def test_harfbuzz_feature_overrides_are_accepted():
    resolved = resolve_font(FontRequest(path=_system_font()))
    normal = shape_text("AV", resolved)
    no_kern = shape_text("AV", resolved, features={"kern": 0})

    assert len(normal.glyphs) == len(no_kern.glyphs) == 2
    assert normal.x_advance > 0
    assert no_kern.x_advance > 0
