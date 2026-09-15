"""Editable mission-patch trajectories and procedural orbit ellipses."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any

from patchcreator.components.registry import ComponentResult
from patchcreator.geometry import (
    Bounds,
    CompoundPath,
    CubicBezierPath,
    EllipsePath,
    LinePath,
    parse_angle_degrees,
    parse_length_mm,
)

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _colour(design: Any, name_or_colour: str) -> str:
    value = design.palette.get(name_or_colour, name_or_colour)
    if isinstance(value, str):
        return value
    raise ValueError(f"derived palette colour {name_or_colour!r} is not rendered yet")


def _point(value: Any, *, name: str) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError(f"{name} must be an [x, y] pair")
    return parse_length_mm(value[0]), parse_length_mm(value[1])


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _stroke_config(raw: Any, design: Any) -> tuple[dict[str, str], float]:
    if raw is None:
        config: Mapping[str, Any] = {}
    elif isinstance(raw, str):
        config = {"colour": raw}
    elif isinstance(raw, Mapping):
        config = raw
    else:
        raise ValueError("trajectory stroke must be a mapping or colour name")

    width = parse_length_mm(config.get("width", 0.8))
    if width <= 0:
        raise ValueError("trajectory stroke width must be positive")
    colour = _colour(design, str(config.get("colour", "#ffffff")))
    attrs = {
        "fill": "none",
        "stroke": colour,
        "stroke-width": _fmt(width),
        "stroke-linecap": str(config.get("linecap", "round")),
        "stroke-linejoin": str(config.get("linejoin", "round")),
        "vector-effect": "non-scaling-stroke",
    }

    dash = config.get("dash", config.get("dasharray"))
    if dash is not None:
        if isinstance(dash, str):
            values = [part.strip() for part in dash.replace(",", " ").split() if part.strip()]
        elif isinstance(dash, Sequence):
            values = list(dash)
        else:
            raise ValueError("trajectory dash pattern must be a string or list")
        parsed = [parse_length_mm(value) for value in values]
        if not parsed or any(value <= 0 for value in parsed):
            raise ValueError("trajectory dash lengths must be positive")
        attrs["stroke-dasharray"] = " ".join(_fmt(value) for value in parsed)

    return attrs, width


def _halo_config(
    raw: Any,
    design: Any,
    *,
    main_attrs: Mapping[str, str],
    main_width: float,
) -> tuple[dict[str, str] | None, float]:
    if raw is None or raw is False:
        return None, main_width
    if raw is True:
        config: Mapping[str, Any] = {}
    elif isinstance(raw, str):
        config = {"colour": raw}
    elif isinstance(raw, Mapping):
        config = raw
    else:
        raise ValueError("trajectory halo must be false, a mapping, or a colour name")

    width = parse_length_mm(config.get("width", main_width + 1.0))
    if width <= main_width:
        raise ValueError("trajectory halo width must exceed the main stroke width")
    colour = _colour(design, str(config.get("colour", "#000000")))
    attrs = {
        "fill": "none",
        "stroke": colour,
        "stroke-width": _fmt(width),
        "stroke-linecap": str(config.get("linecap", main_attrs.get("stroke-linecap", "round"))),
        "stroke-linejoin": str(config.get("linejoin", main_attrs.get("stroke-linejoin", "round"))),
        "vector-effect": "non-scaling-stroke",
    }
    if "stroke-dasharray" in main_attrs:
        attrs["stroke-dasharray"] = main_attrs["stroke-dasharray"]
    return attrs, width


def _expanded(bounds: Bounds, amount: float) -> Bounds:
    return Bounds(
        bounds.min_x - amount,
        bounds.min_y - amount,
        bounds.max_x + amount,
        bounds.max_y + amount,
    )


def _arrow_attrs(element: Any, context: Any, main_attrs: Mapping[str, str]) -> dict[str, str]:
    config = element.component_config()
    raw = str(config.get("arrowheads", config.get("arrow", "none"))).lower()
    if raw in {"none", "false", "off"}:
        return {}
    if raw not in {"start", "end", "both"}:
        raise ValueError("trajectory arrowheads must be none, start, end or both")

    marker_id = f"trajectory-arrow-{element.id}"
    marker = ET.SubElement(
        context.defs,
        _q(SVG_NS, "marker"),
        {
            "id": marker_id,
            "viewBox": "0 0 10 10",
            "refX": "9",
            "refY": "5",
            "markerWidth": "4",
            "markerHeight": "4",
            "markerUnits": "strokeWidth",
            "orient": "auto-start-reverse",
        },
    )
    ET.SubElement(
        marker,
        _q(SVG_NS, "path"),
        {
            "d": "M 0 0 L 10 5 L 0 10 Z",
            "fill": main_attrs["stroke"],
        },
    )
    result: dict[str, str] = {}
    if raw in {"start", "both"}:
        result["marker-start"] = f"url(#{marker_id})"
    if raw in {"end", "both"}:
        result["marker-end"] = f"url(#{marker_id})"
    return result


def _trajectory_geometry(config: Mapping[str, Any]) -> tuple[CompoundPath, str]:
    start = _point(config.get("start", (0.0, 0.0)), name="trajectory start")
    raw_segments = config.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("trajectory requires a non-empty segments list")

    current = start
    segments: list[LinePath | CubicBezierPath] = []
    commands = [f"M {_fmt(start[0])},{_fmt(start[1])}"]

    for index, raw_segment in enumerate(raw_segments):
        segment = _mapping(raw_segment, name=f"trajectory segment {index}")
        if set(segment) == {"line"}:
            target = _point(segment["line"], name=f"trajectory segment {index} line")
            segments.append(LinePath(current, target))
            commands.append(f"L {_fmt(target[0])},{_fmt(target[1])}")
            current = target
            continue

        if set(segment) == {"cubic"}:
            cubic = segment["cubic"]
            if isinstance(cubic, Mapping):
                c1 = _point(cubic.get("control1"), name=f"trajectory segment {index} control1")
                c2 = _point(cubic.get("control2"), name=f"trajectory segment {index} control2")
                target = _point(cubic.get("to"), name=f"trajectory segment {index} to")
            elif isinstance(cubic, Sequence) and not isinstance(cubic, (str, bytes)) and len(cubic) == 6:
                c1 = parse_length_mm(cubic[0]), parse_length_mm(cubic[1])
                c2 = parse_length_mm(cubic[2]), parse_length_mm(cubic[3])
                target = parse_length_mm(cubic[4]), parse_length_mm(cubic[5])
            else:
                raise ValueError(
                    f"trajectory segment {index} cubic must be a mapping or six-value list"
                )
            segments.append(CubicBezierPath(current, c1, c2, target))
            commands.append(
                "C "
                f"{_fmt(c1[0])},{_fmt(c1[1])} "
                f"{_fmt(c2[0])},{_fmt(c2[1])} "
                f"{_fmt(target[0])},{_fmt(target[1])}"
            )
            current = target
            continue

        raise ValueError(
            f"trajectory segment {index} must contain exactly one of 'line' or 'cubic'"
        )

    return CompoundPath(tuple(segments)), " ".join(commands)


def _append_path_pair(
    element: Any,
    context: Any,
    *,
    d: str,
    main_attrs: dict[str, str],
    halo_attrs: dict[str, str] | None,
    arrow_attrs: dict[str, str] | None = None,
) -> None:
    if halo_attrs:
        ET.SubElement(
            context.target_group,
            _q(SVG_NS, "path"),
            {"id": f"{element.id}-halo", "d": d, **halo_attrs},
        )
    attrs = {"id": f"{element.id}-path", "d": d, **main_attrs}
    if arrow_attrs:
        attrs.update(arrow_attrs)
    ET.SubElement(context.target_group, _q(SVG_NS, "path"), attrs)


def render_trajectory(element: Any, context: Any) -> ComponentResult:
    config = element.component_config()
    path, d = _trajectory_geometry(config)
    main_attrs, main_width = _stroke_config(config.get("stroke"), context.design)
    halo_attrs, overall_width = _halo_config(
        config.get("halo"),
        context.design,
        main_attrs=main_attrs,
        main_width=main_width,
    )
    arrows = _arrow_attrs(element, context, main_attrs)
    _append_path_pair(
        element,
        context,
        d=d,
        main_attrs=main_attrs,
        halo_attrs=halo_attrs,
        arrow_attrs=arrows,
    )
    context.target_group.set(_q(PATCHCREATOR_NS, "path-kind"), "trajectory")
    context.target_group.set(_q(PATCHCREATOR_NS, "path-length-mm"), _fmt(path.length()))
    return ComponentResult(
        bounds=_expanded(path.bounds, overall_width / 2.0),
        paths={element.id: path},
    )


def _ellipse_path_d(radius_x: float, radius_y: float) -> str:
    # Begin at the artist-facing 0-degree point (top), then trace clockwise.
    return (
        f"M 0,{_fmt(-radius_y)} "
        f"A {_fmt(radius_x)},{_fmt(radius_y)} 0 1 1 0,{_fmt(radius_y)} "
        f"A {_fmt(radius_x)},{_fmt(radius_y)} 0 1 1 0,{_fmt(-radius_y)} Z"
    )


def render_orbit(element: Any, context: Any) -> ComponentResult:
    config = element.component_config()
    radius_x = parse_length_mm(config.get("radius_x"))
    radius_y = parse_length_mm(config.get("radius_y"))
    if radius_x <= 0 or radius_y <= 0:
        raise ValueError("orbit radius_x and radius_y must be positive")
    rotation = parse_angle_degrees(config.get("rotation", 0.0))
    phase = parse_angle_degrees(config.get("phase", 0.0))
    path = EllipsePath(
        radius_x=radius_x,
        radius_y=radius_y,
        rotation_degrees=rotation,
        phase_degrees=phase,
    )

    main_attrs, main_width = _stroke_config(config.get("stroke"), context.design)
    halo_attrs, overall_width = _halo_config(
        config.get("halo"),
        context.design,
        main_attrs=main_attrs,
        main_width=main_width,
    )
    d = _ellipse_path_d(radius_x, radius_y)
    transform = None if abs(rotation) < 1e-12 else f"rotate({_fmt(rotation)})"

    if halo_attrs:
        attrs = {"id": f"{element.id}-halo", "d": d, **halo_attrs}
        if transform:
            attrs["transform"] = transform
        ET.SubElement(context.target_group, _q(SVG_NS, "path"), attrs)
    attrs = {"id": f"{element.id}-path", "d": d, **main_attrs}
    if transform:
        attrs["transform"] = transform
    ET.SubElement(context.target_group, _q(SVG_NS, "path"), attrs)

    context.target_group.set(_q(PATCHCREATOR_NS, "path-kind"), "orbit")
    context.target_group.set(_q(PATCHCREATOR_NS, "path-length-mm"), _fmt(path.length()))
    context.target_group.set(_q(PATCHCREATOR_NS, "orbit-phase-deg"), _fmt(phase))
    return ComponentResult(
        bounds=_expanded(path.bounds, overall_width / 2.0),
        paths={element.id: path},
        anchors={"orbit-centre": (0.0, 0.0)},
    )
