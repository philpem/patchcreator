"""Outline ordinary single-subpath SVG textPath layouts into glyph paths.

PatchCreator circular construction baselines remain handled by text_path_outline;
this pass handles other internal SVG paths via geometry.svg_path_sampler().
"""

from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Iterable

from fontTools.pens.svgPathPen import SVGPathPen

from patchcreator.geometry import SvgPathSamplingError, svg_path_sampler
from patchcreator.text import FontRequest, FontResolutionError, open_ttfont, resolve_font, shape_text
from patchcreator.svg.text_outline import (
    TextOutlineError,
    TextOutlineResult,
    _copy_group_attrs,
    _family_request,
    _local_name,
    _number,
    _property,
    _q,
    _style,
    _unique_id,
)

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _start_offset(raw: str | None, path_length: float) -> float:
    if raw is None:
        return 0.0
    text = raw.strip()
    if text.endswith("%"):
        try:
            return path_length * float(text[:-1]) / 100.0
        except ValueError as exc:
            raise TextOutlineError(f"invalid textPath startOffset {raw!r}") from exc
    return _number(text, name="startOffset")


def _id_index(root: ET.Element) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for element in root.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        if element_id in result:
            raise TextOutlineError(f"duplicate SVG id {element_id!r} while resolving textPath")
        result[element_id] = element
    return result


def _patchcreator_baseline(path: ET.Element) -> bool:
    role = path.get(f"{{{PATCHCREATOR_NS}}}construction-role") or path.get(
        "data-patchcreator-construction-role"
    )
    return role == "text-baseline"


def _outline_node(
    text_node: ET.Element,
    text_path: ET.Element,
    *,
    index: dict[str, ET.Element],
    explicit_font_path: str | Path | None,
    search_directories: Iterable[str | Path] | None,
    used_ids: set[str],
) -> tuple[ET.Element, tuple[str, ...]]:
    if len(text_path):
        raise TextOutlineError("nested tspan/child content inside textPath is not supported yet")
    if text_node.text and text_node.text.strip():
        raise TextOutlineError("mixed direct text and textPath content is not supported")
    if text_path.tail and text_path.tail.strip():
        raise TextOutlineError("mixed content after textPath is not supported")
    if text_path.get("style"):
        raise TextOutlineError("per-textPath style overrides are not supported yet")
    if text_path.get("method", "align") != "align":
        raise TextOutlineError("textPath method other than 'align' is not supported")
    if text_path.get("spacing", "auto") not in {"auto", "exact"}:
        raise TextOutlineError("unsupported textPath spacing mode")

    href = text_path.get("href") or text_path.get(f"{{{XLINK_NS}}}href")
    if not href or not href.startswith("#"):
        raise TextOutlineError("textPath outlining requires an internal SVG path reference")
    baseline = index.get(href[1:])
    if baseline is None:
        raise TextOutlineError(f"textPath baseline {href!r} does not exist")
    if _local_name(baseline.tag) != "path":
        raise TextOutlineError("textPath baseline must reference an SVG path element")
    if baseline.get("transform"):
        raise TextOutlineError("transformed arbitrary textPath baselines are not supported yet")
    try:
        sampler = svg_path_sampler(baseline.get("d", ""))
    except SvgPathSamplingError as exc:
        raise TextOutlineError(f"cannot sample textPath baseline {href!r}: {exc}") from exc
    path_length = sampler.length()
    if path_length <= 0:
        raise TextOutlineError("textPath baseline has zero length")

    text = text_path.text or ""
    if not text:
        raise TextOutlineError("cannot outline an empty textPath")
    style = _style(text_node)
    writing_mode = (_property(text_node, style, "writing-mode", "horizontal-tb") or "horizontal-tb").lower()
    if writing_mode not in {"horizontal-tb", "lr", "lr-tb"}:
        raise TextOutlineError("vertical/non-horizontal textPath outlining is not supported")
    font_size = _number(_property(text_node, style, "font-size", "16"), name="font-size", default=16.0)
    if font_size <= 0:
        raise TextOutlineError("SVG text font-size must be positive")

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
        run = shape_text(text, resolved, direction=_property(text_node, style, "direction"))
    except FontResolutionError as exc:
        element_id = text_node.get("id") or "<text>"
        raise TextOutlineError(f"cannot outline textPath {element_id!r}: {exc}") from exc
    if run.y_advance != 0 or run.direction in {"ttb", "btt"}:
        raise TextOutlineError("vertical HarfBuzz runs are not supported on textPath")

    scale = font_size / run.units_per_em
    glyph_count = len(run.glyphs)
    spacing_step = _number(_property(text_node, style, "letter-spacing", "0"), name="letter-spacing")
    natural_advance = run.x_advance * scale + spacing_step * max(0, glyph_count - 1)
    raw_text_length = text_path.get("textLength")
    if raw_text_length is not None:
        if text_path.get("lengthAdjust", "spacing") != "spacing":
            raise TextOutlineError(
                "textPath outlining currently supports textLength only with lengthAdjust='spacing'"
            )
        target = _number(raw_text_length, name="textLength")
        if target <= 0:
            raise TextOutlineError("SVG textLength must be positive")
        if glyph_count <= 1:
            if abs(target - abs(natural_advance)) > 1e-9:
                raise TextOutlineError("cannot satisfy textLength=spacing for a single-glyph textPath run")
        else:
            spacing_step += (target - natural_advance) / (glyph_count - 1)
            natural_advance = target

    anchor = (_property(text_node, style, "text-anchor", "start") or "start").lower()
    if anchor not in {"start", "middle", "end"}:
        raise TextOutlineError(f"unsupported SVG text-anchor {anchor!r}")
    anchor_fraction = {"start": 0.0, "middle": 0.5, "end": 1.0}[anchor]
    pen_distance = _start_offset(text_path.get("startOffset"), path_length) - natural_advance * anchor_fraction
    baseline_shift = _number(text_node.get("dy"), name="dy")

    group = ET.Element(_q("g"), _copy_group_attrs(text_node))
    element_id = text_node.get("id")
    warnings = tuple(f"text {element_id or '<text>'}: {note}" for note in resolved.substitutions)

    ttfont = open_ttfont(resolved, lazy=False)
    try:
        glyph_set = ttfont.getGlyphSet()
        for glyph_index, glyph in enumerate(run.glyphs):
            distance = pen_distance + glyph.x_offset * scale
            if distance < -1e-7 or distance > path_length + 1e-7:
                raise TextOutlineError(
                    f"textPath glyph {glyph_index} falls outside its baseline; adjust startOffset/fit"
                )
            distance = min(max(distance, 0.0), path_length)
            sample = sampler.sample(distance / path_length)
            tx, ty = sample.tangent
            magnitude = math.hypot(tx, ty)
            if magnitude <= 1e-12:
                raise TextOutlineError("textPath sampler returned a zero tangent")
            tx, ty = tx / magnitude, ty / magnitude
            normal_x, normal_y = -ty, tx
            normal_offset = baseline_shift - glyph.y_offset * scale
            origin_x = sample.point[0] + normal_x * normal_offset
            origin_y = sample.point[1] + normal_y * normal_offset

            if glyph.glyph_name not in glyph_set:
                raise TextOutlineError(
                    f"resolved font no longer contains shaped glyph {glyph.glyph_name!r}"
                )
            pen = SVGPathPen(glyph_set)
            glyph_set[glyph.glyph_name].draw(pen)
            commands = pen.getCommands()
            if commands:
                attrs = {
                    "d": commands,
                    "transform": (
                        f"matrix({scale * tx:.12g} {scale * ty:.12g} "
                        f"{scale * ty:.12g} {-scale * tx:.12g} "
                        f"{origin_x:.12g} {origin_y:.12g})"
                    ),
                }
                if element_id:
                    attrs["id"] = _unique_id(
                        f"{element_id}-glyph-{glyph_index:04d}", used_ids
                    )
                ET.SubElement(group, _q("path"), attrs)
            pen_distance += glyph.x_advance * scale
            if glyph_index + 1 < glyph_count:
                pen_distance += spacing_step
    finally:
        ttfont.close()

    return group, warnings


def outline_general_text_paths(
    root: ET.Element,
    *,
    font_path: str | Path | None = None,
    search_directories: Iterable[str | Path] | None = None,
) -> TextOutlineResult:
    """Replace non-PatchCreator single-subpath `<textPath>` nodes with paths."""

    index = _id_index(root)
    used_ids = set(index)
    converted = 0
    warnings: list[str] = []

    def visit(parent: ET.Element) -> None:
        nonlocal converted
        for position, child in list(enumerate(list(parent))):
            if _local_name(child.tag) != "text":
                visit(child)
                continue
            text_paths = [item for item in child if _local_name(item.tag) == "textPath"]
            if not text_paths:
                continue
            if len(text_paths) != 1 or len(child) != 1:
                raise TextOutlineError("textPath outlining currently requires one direct textPath child")
            href = text_paths[0].get("href") or text_paths[0].get(f"{{{XLINK_NS}}}href")
            baseline = index.get(href[1:]) if href and href.startswith("#") else None
            if baseline is not None and _patchcreator_baseline(baseline):
                # Leave PatchCreator circular construction baselines for the
                # specialised arc pass, which retains its existing semantics.
                continue
            replacement, produced_warnings = _outline_node(
                child,
                text_paths[0],
                index=index,
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
