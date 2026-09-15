"""Procedural Earth globe/horizon SVG component."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Mapping

from patchcreator.components.registry import ComponentResult
from patchcreator.geography import (
    Viewpoint,
    default_simplification_tolerance,
    load_natural_earth_land_rings,
    visible_ring_polygons,
)
from patchcreator.geometry import Bounds, parse_angle_degrees, parse_length_mm

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


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"earth {name} must be a mapping")
    return value


def _viewpoint(config: Mapping[str, Any]) -> Viewpoint:
    raw = _mapping(config.get("viewpoint"), name="viewpoint")
    return Viewpoint(
        latitude=parse_angle_degrees(raw.get("latitude", 0.0)),
        longitude=parse_angle_degrees(raw.get("longitude", 0.0)),
    )


def _simplification_tolerance(config: Mapping[str, Any], context: Any, diameter: float) -> float:
    raw = config.get("simplify", "auto")
    if raw is False or (isinstance(raw, str) and raw.strip().lower() in {"none", "off"}):
        return 0.0
    if raw is None or (isinstance(raw, str) and raw.strip().lower() == "auto"):
        return default_simplification_tolerance(
            diameter,
            intent=context.design.profile.intent,
            embroidery_safety=context.design.settings.embroidery_safety,
        )
    tolerance = parse_length_mm(raw)
    if tolerance < 0:
        raise ValueError("earth simplification tolerance may not be negative")
    return tolerance


def _path_data(polygons: Iterable[Iterable[tuple[float, float]]]) -> str:
    commands: list[str] = []
    for polygon in polygons:
        points = list(polygon)
        if len(points) < 3:
            continue
        if points[0] == points[-1]:
            points.pop()
        if len(points) < 3:
            continue
        commands.append(f"M {_fmt(points[0][0])},{_fmt(points[0][1])}")
        for x, y in points[1:]:
            commands.append(f"L {_fmt(x)},{_fmt(y)}")
        commands.append("Z")
    return " ".join(commands)


def _stroke_attrs(design: Any, raw: Any, *, default_colour: str) -> dict[str, str]:
    if raw is None or raw is False:
        return {}
    if raw is True:
        config: Mapping[str, Any] = {}
    elif isinstance(raw, Mapping):
        config = raw
    else:
        config = {"colour": raw}
    colour = _colour(design, str(config.get("colour", default_colour)))
    width = parse_length_mm(config.get("width", 0.5))
    if width <= 0:
        return {}
    return {
        "stroke": colour,
        "stroke-width": _fmt(width),
        "stroke-linejoin": str(config.get("linejoin", "round")),
        "stroke-linecap": str(config.get("linecap", "round")),
        "vector-effect": "non-scaling-stroke",
    }


def _horizon_group(
    element: Any,
    context: Any,
    *,
    radius: float,
    visible_height: float,
) -> tuple[ET.Element, tuple[float, float], Bounds, dict[str, tuple[float, float]]]:
    if not 0 < visible_height <= radius:
        raise ValueError("earth horizon visible_height must be > 0 and <= half the diameter")

    # Local y=0 is the horizon baseline/reference. The visible top cap occupies
    # -visible_height <= y <= 0, making `horizon-centre` a useful placement anchor
    # for aligning the Earth with the bottom of a patch.
    globe_centre = (0.0, radius - visible_height)
    half_width = math.sqrt(max(0.0, radius * radius - globe_centre[1] ** 2))
    bounds = Bounds(-half_width, -visible_height, half_width, 0.0)
    anchors = {
        "horizon-centre": (0.0, 0.0),
        "apex": (0.0, -visible_height),
        "globe-centre": globe_centre,
        "horizon-left": (-half_width, 0.0),
        "horizon-right": (half_width, 0.0),
    }

    clip_id = f"earth-horizon-clip-{element.id}"
    clip = ET.SubElement(
        context.defs,
        _q(SVG_NS, "clipPath"),
        {"id": clip_id, "clipPathUnits": "userSpaceOnUse"},
    )
    ET.SubElement(
        clip,
        _q(SVG_NS, "rect"),
        {
            "x": _fmt(-radius),
            "y": _fmt(-visible_height),
            "width": _fmt(radius * 2.0),
            "height": _fmt(visible_height),
        },
    )
    artwork = ET.SubElement(
        context.target_group,
        _q(SVG_NS, "g"),
        {"id": f"{element.id}-artwork", "clip-path": f"url(#{clip_id})"},
    )
    return artwork, globe_centre, bounds, anchors


def render_earth(element: Any, context: Any) -> ComponentResult:
    """Render an accurate, patch-simplified orthographic Earth.

    ``render: globe`` produces a complete circular globe centred on the local
    origin. ``render: horizon`` produces a top cap whose local y=0 baseline can
    be aligned to the patch edge using the named ``horizon-centre`` anchor.

    Natural Earth data is read only from PatchCreator's explicit external-data
    cache. Missing data therefore raises the normal actionable
    ``patchcreator data fetch natural-earth-land-110m`` diagnostic rather than
    downloading as a rendering side effect.
    """
    config = element.component_config()
    diameter = parse_length_mm(config.get("diameter", 30.0))
    if diameter <= 0:
        raise ValueError("earth diameter must be positive")
    radius = diameter / 2.0
    render_mode = str(config.get("render", "globe")).lower()
    if render_mode not in {"globe", "horizon"}:
        raise ValueError("earth render must be 'globe' or 'horizon'")

    style = _mapping(config.get("style"), name="style")
    viewpoint = _viewpoint(config)
    tolerance = _simplification_tolerance(config, context, diameter)
    limb_step = parse_angle_degrees(config.get("limb_step", "4deg"))
    if not 0 < limb_step <= 180:
        raise ValueError("earth limb_step must be between 0 and 180 degrees")

    if render_mode == "horizon":
        visible_height = parse_length_mm(config.get("visible_height", radius * 0.35))
        artwork, centre, bounds, anchors = _horizon_group(
            element,
            context,
            radius=radius,
            visible_height=visible_height,
        )
    else:
        artwork = ET.SubElement(
            context.target_group,
            _q(SVG_NS, "g"),
            {"id": f"{element.id}-artwork"},
        )
        centre = (0.0, 0.0)
        bounds = Bounds(-radius, -radius, radius, radius)
        anchors = {"globe-centre": centre}

    sea_value = style.get("sea", "#1559a6")
    land_value = style.get("land", "#66b857")

    if sea_value is not None:
        ET.SubElement(
            artwork,
            _q(SVG_NS, "circle"),
            {
                "id": f"{element.id}-sea",
                "cx": _fmt(centre[0]),
                "cy": _fmt(centre[1]),
                "r": _fmt(radius),
                "fill": _colour(context.design, str(sea_value)),
            },
        )

    rings = load_natural_earth_land_rings()
    polygons: list[tuple[tuple[float, float], ...]] = []
    for ring in rings:
        polygons.extend(
            visible_ring_polygons(
                ring,
                viewpoint,
                radius=radius,
                centre=centre,
                simplify_tolerance=tolerance,
                limb_step_degrees=limb_step,
            )
        )

    land_path = _path_data(polygons)
    coastline_attrs = _stroke_attrs(
        context.design,
        style.get("coastline"),
        default_colour=str(style.get("coastline_colour", land_value or "#ffffff")),
    )
    if land_path and (land_value is not None or coastline_attrs):
        attrs = {
            "id": f"{element.id}-land",
            "d": land_path,
            "fill": _colour(context.design, str(land_value)) if land_value is not None else "none",
            "fill-rule": "evenodd",
        }
        attrs.update(coastline_attrs)
        ET.SubElement(artwork, _q(SVG_NS, "path"), attrs)

    outline_attrs = _stroke_attrs(
        context.design,
        style.get("outline"),
        default_colour=str(style.get("outline_colour", land_value or "#ffffff")),
    )
    if outline_attrs:
        ET.SubElement(
            artwork,
            _q(SVG_NS, "circle"),
            {
                "id": f"{element.id}-outline",
                "cx": _fmt(centre[0]),
                "cy": _fmt(centre[1]),
                "r": _fmt(radius),
                "fill": "none",
                **outline_attrs,
            },
        )

    atmosphere = style.get("atmosphere")
    if atmosphere is not None and atmosphere is not False:
        atmosphere_attrs = _stroke_attrs(
            context.design,
            atmosphere,
            default_colour="#ffffff",
        )
        if atmosphere_attrs:
            ET.SubElement(
                artwork,
                _q(SVG_NS, "circle"),
                {
                    "id": f"{element.id}-atmosphere",
                    "cx": _fmt(centre[0]),
                    "cy": _fmt(centre[1]),
                    "r": _fmt(radius),
                    "fill": "none",
                    **atmosphere_attrs,
                },
            )

    context.target_group.set(_q(PATCHCREATOR_NS, "earth-render"), render_mode)
    context.target_group.set(_q(PATCHCREATOR_NS, "earth-view-latitude"), _fmt(viewpoint.latitude))
    context.target_group.set(_q(PATCHCREATOR_NS, "earth-view-longitude"), _fmt(viewpoint.longitude))
    context.target_group.set(_q(PATCHCREATOR_NS, "earth-simplify-mm"), _fmt(tolerance))
    context.target_group.set(_q(PATCHCREATOR_NS, "earth-source"), "natural-earth-land-110m")

    return ComponentResult(bounds=bounds, anchors=anchors)
