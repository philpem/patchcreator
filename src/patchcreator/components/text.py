"""Live, Inkscape-editable mission-patch text and text-on-path layouts."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any

from patchcreator.components.registry import ComponentResult
from patchcreator.geometry import Bounds, parse_angle_degrees, parse_length_mm, polar_to_cartesian

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"text {name} must be a mapping")
    return value


def _colour(design: Any, name_or_colour: str) -> str:
    value = design.palette.get(name_or_colour, name_or_colour)
    if isinstance(value, str):
        return value
    raise ValueError(f"derived palette colour {name_or_colour!r} is not rendered yet")


def _fraction(value: Any, *, name: str, default: float = 1.0) -> float:
    if value is None:
        result = default
    elif isinstance(value, str) and value.strip().endswith("%"):
        try:
            result = float(value.strip()[:-1]) / 100.0
        except ValueError as exc:
            raise ValueError(f"invalid text {name} {value!r}") from exc
    else:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid text {name} {value!r}") from exc
    if not 0.0 < result <= 1.5:
        raise ValueError(f"text {name} must be greater than 0 and no more than 150%")
    return result


def _font_attrs(config: Mapping[str, Any], design: Any) -> tuple[dict[str, str], float, Any]:
    font = _mapping(config.get("font"), name="font")
    size = parse_length_mm(font.get("size", 5.0))
    if size <= 0:
        raise ValueError("text font size must be positive")

    attrs: dict[str, str] = {
        "font-family": str(font.get("family", "sans-serif")),
        "font-size": _fmt(size),
        "font-weight": str(font.get("weight", "normal")),
        "font-style": str(font.get("style", "normal")),
        "fill": _colour(design, str(config.get("fill", "#ffffff"))),
    }
    if font.get("stretch") is not None:
        attrs["font-stretch"] = str(font["stretch"])

    stroke = config.get("stroke")
    if stroke is not None and stroke is not False:
        stroke_config = _mapping(stroke, name="stroke") if isinstance(stroke, Mapping) else {"colour": stroke}
        width = parse_length_mm(stroke_config.get("width", 0.3))
        if width <= 0:
            raise ValueError("text stroke width must be positive")
        attrs.update(
            {
                "stroke": _colour(design, str(stroke_config.get("colour", config.get("fill", "#ffffff")))),
                "stroke-width": _fmt(width),
                "stroke-linejoin": str(stroke_config.get("linejoin", "round")),
                "paint-order": "stroke fill",
            }
        )

    return attrs, size, font.get("tracking", "auto")


def _direction(layout_type: str, raw: Any, start: float, end: float) -> tuple[bool, float]:
    """Return (clockwise, positive span in degrees)."""
    if raw is None:
        if layout_type == "top-arc":
            raw = "clockwise"
        elif layout_type == "bottom-arc":
            raw = "counterclockwise"
        else:
            raw = "shortest"
    direction = str(raw).lower()
    clockwise_span = (end - start) % 360.0
    counter_span = (start - end) % 360.0
    if abs(clockwise_span) < 1e-12:
        clockwise_span = 360.0
    if abs(counter_span) < 1e-12:
        counter_span = 360.0

    if direction in {"clockwise", "cw"}:
        return True, clockwise_span
    if direction in {"counterclockwise", "anticlockwise", "ccw"}:
        return False, counter_span
    if direction == "shortest":
        return (True, clockwise_span) if clockwise_span <= counter_span else (False, counter_span)
    if direction == "longest":
        return (True, clockwise_span) if clockwise_span >= counter_span else (False, counter_span)
    raise ValueError("text arc direction must be clockwise, counterclockwise, shortest or longest")


def _arc_geometry(layout_type: str, layout: Mapping[str, Any]) -> tuple[str, float, Bounds]:
    radius = parse_length_mm(layout.get("radius"))
    if radius <= 0:
        raise ValueError("text arc radius must be positive")

    if layout_type == "top-arc":
        default_start, default_end = 300.0, 60.0
    elif layout_type == "bottom-arc":
        default_start, default_end = 240.0, 120.0
    else:
        default_start, default_end = 300.0, 60.0

    start = parse_angle_degrees(layout.get("start_angle", default_start)) % 360.0
    end = parse_angle_degrees(layout.get("end_angle", default_end)) % 360.0
    clockwise, span = _direction(layout_type, layout.get("direction"), start, end)
    start_point = polar_to_cartesian(radius, start)
    end_point = polar_to_cartesian(radius, end)
    large = "1" if span > 180.0 else "0"
    sweep = "1" if clockwise else "0"
    d = (
        f"M {_fmt(start_point[0])},{_fmt(start_point[1])} "
        f"A {_fmt(radius)},{_fmt(radius)} 0 {large} {sweep} "
        f"{_fmt(end_point[0])},{_fmt(end_point[1])}"
    )

    samples = []
    for index in range(65):
        amount = span * index / 64.0
        angle = start + amount if clockwise else start - amount
        samples.append(polar_to_cartesian(radius, angle))
    bounds = Bounds.from_points(samples)
    return d, radius * math.radians(span), bounds


def _tracking_attrs(
    tracking: Any,
    *,
    available_length: float | None,
    fit: float,
) -> dict[str, str]:
    if tracking is None or (isinstance(tracking, str) and tracking.lower() in {"normal", "none"}):
        return {}
    if isinstance(tracking, str) and tracking.lower() == "auto":
        if available_length is None:
            return {}
        target = available_length * fit
        if target <= 0:
            raise ValueError("automatic text fitting produced a non-positive target length")
        return {
            "textLength": _fmt(target),
            "lengthAdjust": "spacing",
        }
    spacing = parse_length_mm(tracking)
    return {"letter-spacing": _fmt(spacing)}


def _parse_explicit_bounds(raw: Any) -> Bounds | None:
    if raw is None:
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 4:
        raise ValueError("text path bounds must be [min_x, min_y, max_x, max_y]")
    return Bounds(*(parse_length_mm(value) for value in raw))


def _expanded(bounds: Bounds, amount: float) -> Bounds:
    return Bounds(
        bounds.min_x - amount,
        bounds.min_y - amount,
        bounds.max_x + amount,
        bounds.max_y + amount,
    )


def _text_width_estimate(text: str, size: float, tracking: Any) -> float:
    # Used only for conservative scene bounds; actual rendering remains live text.
    base = max(1, len(text)) * size * 0.62
    if not isinstance(tracking, str) and tracking is not None:
        base += max(0, len(text) - 1) * parse_length_mm(tracking)
    return max(size, base)


def _baseline_construction_attrs(context: Any) -> dict[str, str]:
    attrs = {
        "fill": "none",
        _q(PATCHCREATOR_NS, "construction-role"): "text-baseline",
    }
    if context.design.settings.construction_guides:
        attrs.update(
            {
                "stroke": "#00a6ff",
                "stroke-width": "0.2",
                "stroke-opacity": "0.75",
                "stroke-dasharray": "1 1",
                "vector-effect": "non-scaling-stroke",
            }
        )
    else:
        attrs["stroke"] = "none"
    return attrs


def _validate_future_conversion_hooks(config: Mapping[str, Any], group: ET.Element) -> None:
    warp = config.get("warp")
    warp_is_disabled = (
        warp is None
        or warp is False
        or (isinstance(warp, str) and warp.strip().lower() == "none")
    )
    if not warp_is_disabled:
        raise ValueError(
            "text warp is reserved for the future text-to-path/warp export hook; "
            "keep warp unset/none for live SVG text"
        )
    if bool(config.get("convert_to_path", False)):
        raise ValueError(
            "text convert_to_path is not a render-time operation; keep live text in the master "
            "and use 'patchcreator export --text paths' for compatibility output"
        )
    group.set(_q(PATCHCREATOR_NS, "text-conversion"), "live")
    group.set(_q(PATCHCREATOR_NS, "warp-hook"), "future-text-to-path")


def render_text(element: Any, context: Any) -> ComponentResult:
    config = element.component_config()
    text = str(config.get("text", ""))
    if not text:
        raise ValueError("text component requires non-empty text")
    layout = _mapping(config.get("layout"), name="layout")
    layout_type = str(layout.get("type", "straight")).lower()
    aliases = {
        "top-band": "upper-band",
        "bottom-band": "lower-band",
        "banner": "band",
    }
    layout_type = aliases.get(layout_type, layout_type)
    allowed = {
        "top-arc",
        "bottom-arc",
        "arc",
        "path",
        "straight",
        "band",
        "upper-band",
        "lower-band",
    }
    if layout_type not in allowed:
        raise ValueError(f"unsupported text layout {layout_type!r}")

    _validate_future_conversion_hooks(config, context.target_group)
    font_attrs, font_size, tracking = _font_attrs(config, context.design)
    fit = _fraction(layout.get("fit"), name="fit", default=0.90)
    baseline_shift = parse_length_mm(layout.get("baseline_shift", 0.0))

    text_attrs = {
        "id": f"{element.id}-text",
        **font_attrs,
        _q(XML_NS, "space"): "preserve",
    }
    anchors: dict[str, tuple[float, float]] = {}
    warnings: list[str] = []

    if layout_type in {"top-arc", "bottom-arc", "arc"}:
        d, path_length, path_bounds = _arc_geometry(layout_type, layout)
        baseline_id = f"{element.id}-baseline"
        ET.SubElement(
            context.target_group,
            _q(SVG_NS, "path"),
            {
                "id": baseline_id,
                "d": d,
                **_baseline_construction_attrs(context),
            },
        )
        text_node = ET.SubElement(
            context.target_group,
            _q(SVG_NS, "text"),
            {**text_attrs, "text-anchor": "middle", "dy": _fmt(baseline_shift)},
        )
        tracking_attrs = _tracking_attrs(tracking, available_length=path_length, fit=fit)
        text_path = ET.SubElement(
            text_node,
            _q(SVG_NS, "textPath"),
            {
                "href": f"#{baseline_id}",
                "startOffset": str(layout.get("start_offset", "50%")),
                "method": "align",
                "spacing": "auto",
                **tracking_attrs,
            },
        )
        text_path.text = text
        bounds = _expanded(path_bounds, font_size + abs(baseline_shift))
        anchors["baseline-centre"] = path_bounds.centre

    elif layout_type == "path":
        reference = layout.get("href")
        if reference is None:
            path_name = layout.get("path")
            if not path_name:
                raise ValueError("text path layout requires href or path")
            reference = str(path_name)
            if not reference.startswith("#"):
                reference = f"#{reference}-path"
        reference = str(reference)
        if not reference.startswith("#"):
            reference = f"#{reference}"

        path_length = None
        if layout.get("length") is not None:
            path_length = parse_length_mm(layout["length"])
            if path_length <= 0:
                raise ValueError("text path length must be positive")
        tracking_attrs = _tracking_attrs(tracking, available_length=path_length, fit=fit)
        if isinstance(tracking, str) and tracking.lower() == "auto" and path_length is None:
            warnings.append(
                f"text {element.id!r} uses tracking:auto on an external path without layout.length; "
                "leaving natural font spacing"
            )
        text_node = ET.SubElement(
            context.target_group,
            _q(SVG_NS, "text"),
            {**text_attrs, "text-anchor": "middle", "dy": _fmt(baseline_shift)},
        )
        text_path = ET.SubElement(
            text_node,
            _q(SVG_NS, "textPath"),
            {
                "href": reference,
                "startOffset": str(layout.get("start_offset", "50%")),
                "method": "align",
                "spacing": "auto",
                **tracking_attrs,
            },
        )
        text_path.text = text
        explicit_bounds = _parse_explicit_bounds(layout.get("bounds"))
        bounds = _expanded(explicit_bounds, font_size) if explicit_bounds else None
        if explicit_bounds:
            anchors["baseline-centre"] = explicit_bounds.centre

    else:
        x = parse_length_mm(layout.get("x", 0.0))
        if layout_type == "upper-band":
            y = -abs(parse_length_mm(layout.get("offset", layout.get("y", 0.0))))
        elif layout_type == "lower-band":
            y = abs(parse_length_mm(layout.get("offset", layout.get("y", 0.0))))
        else:
            y = parse_length_mm(layout.get("y", 0.0))
        width = None
        if layout.get("width") is not None:
            width = parse_length_mm(layout["width"])
            if width <= 0:
                raise ValueError("text band width must be positive")
        tracking_attrs = _tracking_attrs(tracking, available_length=width, fit=fit)
        text_node = ET.SubElement(
            context.target_group,
            _q(SVG_NS, "text"),
            {
                **text_attrs,
                "x": _fmt(x),
                "y": _fmt(y + baseline_shift),
                "text-anchor": str(layout.get("anchor", "middle")),
                **tracking_attrs,
            },
        )
        text_node.text = text
        target_width = width * fit if width is not None and tracking_attrs.get("textLength") else _text_width_estimate(text, font_size, tracking)
        bounds = Bounds(
            x - target_width / 2.0,
            y + baseline_shift - font_size,
            x + target_width / 2.0,
            y + baseline_shift + font_size * 0.35,
        )
        anchors["baseline-centre"] = (x, y + baseline_shift)

    context.target_group.set(_q(PATCHCREATOR_NS, "text-layout"), layout_type)
    context.target_group.set(_q(PATCHCREATOR_NS, "text-live"), "true")
    return ComponentResult(bounds=bounds, anchors=anchors, warnings=tuple(warnings))
