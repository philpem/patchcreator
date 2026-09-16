"""Convert simple live SVG text into shaped editable glyph paths.

This module is intentionally limited to horizontal text with direct text
content.  Text-on-path/tspan placement is a separate geometry problem and is
rejected explicitly until the follow-up implementation lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Iterable

from fontTools.pens.svgPathPen import SVGPathPen

from patchcreator.text import FontRequest, FontResolutionError, open_ttfont, resolve_font, shape_text

SVG_NS = "http://www.w3.org/2000/svg"

_NUMBER_RE = re.compile(r"^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*$")
_FONT_ATTRS = {
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "font-stretch",
    "letter-spacing",
    "text-anchor",
    "direction",
    "writing-mode",
}
_TEXT_LAYOUT_ATTRS = {"x", "y", "dx", "dy", "rotate", "textLength", "lengthAdjust"}


class TextOutlineError(ValueError):
    pass


@dataclass(frozen=True)
class TextOutlineResult:
    converted_count: int
    warnings: tuple[str, ...] = ()


def _q(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _style(element: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for declaration in element.get("style", "").split(";"):
        if ":" not in declaration:
            continue
        key, value = declaration.split(":", 1)
        result[key.strip().lower()] = value.strip()
    return result


def _property(element: ET.Element, style: dict[str, str], name: str, default: str | None = None) -> str | None:
    if name in style:
        return style[name]
    value = element.get(name)
    return value if value is not None else default


def _number(raw: str | None, *, name: str, default: float = 0.0) -> float:
    if raw is None:
        return default
    if name == "letter-spacing" and raw.strip().lower() == "normal":
        return 0.0
    if not _NUMBER_RE.match(raw):
        raise TextOutlineError(
            f"straight text outlining currently requires a single unitless numeric {name}; got {raw!r}"
        )
    return float(raw)


def _family_request(raw: str | None) -> tuple[str, tuple[str, ...]]:
    if not raw:
        return "sans-serif", ()
    names = []
    for part in raw.split(","):
        value = part.strip().strip("\"'")
        if value:
            names.append(value)
    if not names:
        return "sans-serif", ()
    return names[0], tuple(names[1:])


def _copy_group_attrs(text: ET.Element) -> dict[str, str]:
    attrs = dict(text.attrib)
    for key in _FONT_ATTRS | _TEXT_LAYOUT_ATTRS:
        attrs.pop(key, None)
    return attrs


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base
    serial = 2
    while candidate in used:
        candidate = f"{base}-{serial}"
        serial += 1
    used.add(candidate)
    return candidate


def _outline_one(
    text_node: ET.Element,
    *,
    explicit_font_path: str | Path | None,
    search_directories: Iterable[str | Path] | None,
    used_ids: set[str],
) -> tuple[ET.Element, tuple[str, ...]]:
    if len(text_node):
        child_names = {_local_name(child.tag) for child in text_node}
        if "textPath" in child_names:
            raise TextOutlineError(
                "text-on-path outlining is not implemented in this compatibility-export slice; "
                "use --text preserve until the textPath follow-up lands"
            )
        raise TextOutlineError(
            "straight text outlining does not yet support child elements such as tspan; "
            "normalise the text or preserve it as live SVG text"
        )

    text = text_node.text or ""
    if not text:
        raise TextOutlineError("cannot outline an empty SVG text node")

    style = _style(text_node)
    writing_mode = (_property(text_node, style, "writing-mode", "horizontal-tb") or "horizontal-tb").lower()
    if writing_mode not in {"horizontal-tb", "lr", "lr-tb"}:
        raise TextOutlineError(f"vertical/non-horizontal SVG text is not supported yet: writing-mode={writing_mode!r}")
    if text_node.get("rotate") not in {None, "", "0", "0.0"}:
        raise TextOutlineError("per-character SVG text rotate is not supported by compatibility outlining")
    if text_node.get("dx") not in {None, "", "0", "0.0"}:
        raise TextOutlineError("SVG text dx lists are not supported by compatibility outlining")

    x = _number(text_node.get("x"), name="x")
    y = _number(text_node.get("y"), name="y")
    y += _number(text_node.get("dy"), name="dy")
    font_size = _number(_property(text_node, style, "font-size", "16"), name="font-size", default=16.0)
    if font_size <= 0:
        raise TextOutlineError("SVG text font-size must be positive")

    stretch = (_property(text_node, style, "font-stretch", "normal") or "normal").strip().lower()
    if stretch not in {"normal", "100%"}:
        raise TextOutlineError(
            f"font-stretch={stretch!r} is not supported by compatibility outlining yet"
        )

    family, fallback = _family_request(_property(text_node, style, "font-family", "sans-serif"))
    request = FontRequest(
        family=family,
        fallback_families=fallback,
        weight=_property(text_node, style, "font-weight", "normal") or "normal",
        style=_property(text_node, style, "font-style", "normal") or "normal",
        path=explicit_font_path,
    )
    try:
        resolved = resolve_font(request, search_directories=search_directories)
        run = shape_text(
            text,
            resolved,
            direction=_property(text_node, style, "direction"),
        )
    except FontResolutionError as exc:
        element_id = text_node.get("id") or "<text>"
        raise TextOutlineError(f"cannot outline text {element_id!r}: {exc}") from exc

    if run.y_advance != 0 or run.direction in {"ttb", "btt"}:
        raise TextOutlineError("vertical HarfBuzz runs are not supported by straight text outlining")

    scale = font_size / run.units_per_em
    glyph_count = len(run.glyphs)
    letter_spacing = _number(
        _property(text_node, style, "letter-spacing", "0"),
        name="letter-spacing",
    )
    base_advance = run.x_advance * scale
    spacing_step = letter_spacing
    natural_advance = base_advance + spacing_step * max(0, glyph_count - 1)

    raw_text_length = text_node.get("textLength")
    if raw_text_length is not None:
        length_adjust = text_node.get("lengthAdjust", "spacing")
        if length_adjust != "spacing":
            raise TextOutlineError(
                "straight text outlining currently supports textLength only with lengthAdjust='spacing'"
            )
        target = _number(raw_text_length, name="textLength")
        if target <= 0:
            raise TextOutlineError("SVG textLength must be positive")
        if glyph_count <= 1:
            if abs(target - abs(natural_advance)) > 1e-9:
                raise TextOutlineError(
                    "cannot satisfy textLength=spacing for a single-glyph text run"
                )
        else:
            spacing_step += (target - natural_advance) / (glyph_count - 1)
            natural_advance = target

    anchor = (_property(text_node, style, "text-anchor", "start") or "start").lower()
    if anchor not in {"start", "middle", "end"}:
        raise TextOutlineError(f"unsupported SVG text-anchor {anchor!r}")
    anchor_fraction = {"start": 0.0, "middle": 0.5, "end": 1.0}[anchor]
    pen_x = x - natural_advance * anchor_fraction

    group = ET.Element(_q("g"), _copy_group_attrs(text_node))
    element_id = text_node.get("id")
    warnings = tuple(
        f"text {element_id or '<text>'}: {note}" for note in resolved.substitutions
    )

    ttfont = open_ttfont(resolved, lazy=False)
    try:
        glyph_set = ttfont.getGlyphSet()
        for index, glyph in enumerate(run.glyphs):
            origin_x = pen_x + glyph.x_offset * scale
            origin_y = y - glyph.y_offset * scale
            if glyph.glyph_name not in glyph_set:
                raise TextOutlineError(
                    f"resolved font no longer contains shaped glyph {glyph.glyph_name!r}"
                )
            glyph_object = glyph_set[glyph.glyph_name]
            pen = SVGPathPen(glyph_set)
            glyph_object.draw(pen)
            commands = pen.getCommands()
            if commands:
                attrs = {
                    "d": commands,
                    "transform": (
                        f"matrix({scale:.12g} 0 0 {-scale:.12g} "
                        f"{origin_x:.12g} {origin_y:.12g})"
                    ),
                }
                if element_id:
                    attrs["id"] = _unique_id(f"{element_id}-glyph-{index:04d}", used_ids)
                ET.SubElement(group, _q("path"), attrs)
            pen_x += glyph.x_advance * scale
            if index + 1 < glyph_count:
                pen_x += spacing_step
    finally:
        ttfont.close()

    return group, warnings


def outline_straight_text(
    root: ET.Element,
    *,
    font_path: str | Path | None = None,
    search_directories: Iterable[str | Path] | None = None,
) -> TextOutlineResult:
    """Replace supported horizontal `<text>` nodes with shaped path groups."""

    used_ids = {element_id for element in root.iter() if (element_id := element.get("id"))}
    converted = 0
    warnings: list[str] = []

    def visit(parent: ET.Element) -> None:
        nonlocal converted
        for position, child in list(enumerate(list(parent))):
            if _local_name(child.tag) != "text":
                visit(child)
                continue
            replacement, produced_warnings = _outline_one(
                child,
                explicit_font_path=font_path,
                search_directories=search_directories,
                used_ids=used_ids,
            )
            parent.remove(child)
            parent.insert(position, replacement)
            converted += 1
            warnings.extend(produced_warnings)

    visit(root)
    return TextOutlineResult(converted_count=converted, warnings=tuple(warnings))
