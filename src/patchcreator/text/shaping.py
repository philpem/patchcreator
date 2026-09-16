"""HarfBuzz shaping for resolved local fonts.

Shaping remains in font units.  SVG outlining/placement can then apply the
requested physical font size and layout without losing HarfBuzz's glyph
selection, kerning, ligatures, clusters or script positioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import uharfbuzz as hb

from .fonts import FontResolutionError, ResolvedFont, open_ttfont


@dataclass(frozen=True)
class ShapedGlyph:
    glyph_id: int
    glyph_name: str
    cluster: int
    x_advance: int
    y_advance: int
    x_offset: int
    y_offset: int


@dataclass(frozen=True)
class ShapedRun:
    text: str
    font: ResolvedFont
    glyphs: tuple[ShapedGlyph, ...]
    units_per_em: int
    direction: str
    script: str
    language: str

    @property
    def x_advance(self) -> int:
        return sum(glyph.x_advance for glyph in self.glyphs)

    @property
    def y_advance(self) -> int:
        return sum(glyph.y_advance for glyph in self.glyphs)


def shape_text(
    text: str,
    font: ResolvedFont,
    *,
    direction: str | None = None,
    script: str | None = None,
    language: str | None = None,
    features: Mapping[str, int | bool] | None = None,
) -> ShapedRun:
    """Shape Unicode ``text`` with HarfBuzz using ``font``.

    ``cluster`` values are HarfBuzz cluster indices for the original Python
    string.  Advances and offsets are returned in font units.  No SVG-specific
    assumptions are made here.
    """

    if not text:
        raise ValueError("cannot shape empty text")

    try:
        data = font.face.path.read_bytes()
    except OSError as exc:
        raise FontResolutionError(f"cannot read resolved font {font.face.path}: {exc}") from exc

    try:
        face = hb.Face(data, font.face.face_index)
        hb_font = hb.Font(face)
        upem = int(face.upem or font.face.units_per_em or 1000)
        hb_font.scale = (upem, upem)
        hb.ot_font_set_funcs(hb_font)

        buffer = hb.Buffer()
        buffer.add_str(text)
        if direction is not None:
            buffer.direction = direction
        if script is not None:
            buffer.script = script
        if language is not None:
            buffer.language = language
        buffer.guess_segment_properties()

        feature_values = (
            {name: int(value) for name, value in features.items()}
            if features is not None
            else None
        )
        hb.shape(hb_font, buffer, feature_values)
    except Exception as exc:
        raise FontResolutionError(
            f"HarfBuzz could not shape text with {font.face.path}: {exc}"
        ) from exc

    ttfont = open_ttfont(font)
    try:
        glyph_order = ttfont.getGlyphOrder()
    finally:
        ttfont.close()

    glyphs: list[ShapedGlyph] = []
    for info, position in zip(buffer.glyph_infos, buffer.glyph_positions, strict=True):
        glyph_id = int(info.codepoint)
        glyph_name = glyph_order[glyph_id] if 0 <= glyph_id < len(glyph_order) else f"gid{glyph_id}"
        glyphs.append(
            ShapedGlyph(
                glyph_id=glyph_id,
                glyph_name=glyph_name,
                cluster=int(info.cluster),
                x_advance=int(position.x_advance),
                y_advance=int(position.y_advance),
                x_offset=int(position.x_offset),
                y_offset=int(position.y_offset),
            )
        )

    return ShapedRun(
        text=text,
        font=font,
        glyphs=tuple(glyphs),
        units_per_em=upem,
        direction=str(buffer.direction),
        script=str(buffer.script),
        language=str(buffer.language),
    )
