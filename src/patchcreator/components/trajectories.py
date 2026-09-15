"""Editable mission-patch trajectories and procedural orbit ellipses.

Ordinary paths stay as their native SVG line/Bezier/ellipse geometry. When an
occlusion policy is requested, a post-placement finalizer retains that source
geometry as a hidden construction path and emits physically split visible
polylines. This avoids relying on an SVG mask for geometry which downstream
embroidery software might still stitch.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from patchcreator.components.registry import ComponentFinalizeContext, ComponentResult
from patchcreator.geometry import (
    Bounds,
    CompoundPath,
    CubicBezierPath,
    EllipsePath,
    LinePath,
    PathSampler,
    parse_angle_degrees,
    parse_length_mm,
)

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"
_EPSILON = 1e-9


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


@dataclass(frozen=True)
class _OccluderSpec:
    target: str
    gap: float
    shape: str


@dataclass(frozen=True)
class _ResolvedOccluder:
    target: str
    bounds: Bounds
    shape: str

    def contains(self, point: tuple[float, float]) -> bool:
        if self.shape == "bounds":
            return (
                self.bounds.min_x <= point[0] <= self.bounds.max_x
                and self.bounds.min_y <= point[1] <= self.bounds.max_y
            )

        cx, cy = self.bounds.centre
        rx = self.bounds.width / 2.0
        ry = self.bounds.height / 2.0
        if rx <= _EPSILON or ry <= _EPSILON:
            return False
        dx = (point[0] - cx) / rx
        dy = (point[1] - cy) / ry
        return dx * dx + dy * dy <= 1.0 + _EPSILON


@dataclass(frozen=True)
class _VisiblePart:
    start_fraction: float
    end_fraction: float
    points: tuple[tuple[float, float], ...]


def _parse_occlusion(raw: Any) -> tuple[tuple[_OccluderSpec, ...], int, float | None] | None:
    if raw is None or raw is False:
        return None
    config = _mapping(raw, name="trajectory occlusion")
    behind = config.get("behind")
    if isinstance(behind, str):
        items: list[Any] = [behind]
    elif isinstance(behind, Sequence) and not isinstance(behind, (str, bytes)):
        items = list(behind)
    else:
        raise ValueError("trajectory occlusion requires 'behind' as an object ID or list")
    if not items:
        raise ValueError("trajectory occlusion behind list may not be empty")

    default_gap = parse_length_mm(config.get("gap", 0.0))
    if default_gap < 0:
        raise ValueError("trajectory occlusion gap may not be negative")
    default_shape = str(config.get("shape", "auto")).lower()
    if default_shape not in {"auto", "ellipse", "bounds"}:
        raise ValueError("trajectory occlusion shape must be auto, ellipse or bounds")

    specs: list[_OccluderSpec] = []
    for item in items:
        if isinstance(item, str):
            specs.append(_OccluderSpec(item, default_gap, default_shape))
            continue
        entry = _mapping(item, name="trajectory occlusion entry")
        if not entry.get("target"):
            raise ValueError("trajectory occlusion entries require a target")
        gap = parse_length_mm(entry.get("gap", default_gap))
        if gap < 0:
            raise ValueError("trajectory occlusion gap may not be negative")
        shape = str(entry.get("shape", default_shape)).lower()
        if shape not in {"auto", "ellipse", "bounds"}:
            raise ValueError("trajectory occlusion shape must be auto, ellipse or bounds")
        specs.append(_OccluderSpec(str(entry["target"]), gap, shape))

    samples = int(config.get("samples", 256))
    if not 32 <= samples <= 8192:
        raise ValueError("trajectory occlusion samples must be between 32 and 8192")

    near_side_raw = config.get("near_side")
    near_side: float | None = None
    if near_side_raw is not None:
        names = {"top": 0.0, "right": 90.0, "bottom": 180.0, "left": 270.0}
        if isinstance(near_side_raw, str) and near_side_raw.lower() in names:
            near_side = names[near_side_raw.lower()]
        else:
            near_side = parse_angle_degrees(near_side_raw)
        near_side %= 360.0

    return tuple(specs), samples, near_side


def _resolve_occluders(
    finalize_context: ComponentFinalizeContext,
    specs: tuple[_OccluderSpec, ...],
) -> tuple[list[_ResolvedOccluder], list[str]]:
    resolved: list[_ResolvedOccluder] = []
    warnings: list[str] = []
    graph = finalize_context.graph
    owner_id = finalize_context.element.id

    for spec in specs:
        try:
            target = graph.find(spec.target)
        except KeyError as exc:
            raise ValueError(
                f"trajectory {owner_id!r} occlusion target {spec.target!r} does not exist"
            ) from exc
        if target.resolved_bounds is None:
            if spec.target in finalize_context.skipped_node_ids:
                warnings.append(
                    f"trajectory {owner_id!r} could not apply occlusion target {spec.target!r}: "
                    "target was skipped in this partial render"
                )
                continue
            raise ValueError(
                f"trajectory {owner_id!r} occlusion target {spec.target!r} has no resolved geometry"
            )

        shape = spec.shape
        if shape == "auto":
            component_type = getattr(target.config, "type", None)
            shape = "ellipse" if component_type == "earth" else "bounds"
        resolved.append(
            _ResolvedOccluder(
                spec.target,
                _expanded(target.resolved_bounds, spec.gap),
                shape,
            )
        )
    return resolved, warnings


def _orbit_near_predicate(
    path: EllipsePath,
    near_side_angle: float | None,
) -> Callable[[tuple[float, float]], bool] | None:
    if near_side_angle is None:
        return None
    rotation = math.radians(-path.rotation_degrees)
    cos_a, sin_a = math.cos(rotation), math.sin(rotation)

    def is_near(point: tuple[float, float]) -> bool:
        dx = point[0] - path.centre[0]
        dy = point[1] - path.centre[1]
        x = dx * cos_a - dy * sin_a
        y = dx * sin_a + dy * cos_a
        theta = math.degrees(
            math.atan2(x / path.radius_x, -y / path.radius_y)
        ) % 360.0
        return math.cos(math.radians(theta - near_side_angle)) >= 0.0

    return is_near


def _split_visible_parts(
    path: PathSampler,
    *,
    world_transform: Any,
    occluders: Sequence[_ResolvedOccluder],
    samples: int,
    closed: bool,
    is_near: Callable[[tuple[float, float]], bool] | None = None,
) -> tuple[_VisiblePart, ...]:
    def hidden(fraction: float) -> bool:
        local = path.sample(fraction).point
        world = world_transform.apply(local)
        inside = any(occluder.contains(world) for occluder in occluders)
        if not inside:
            return False
        if is_near is not None and is_near(local):
            return False
        return True

    def boundary(a: float, b: float, state_a: bool) -> tuple[float, tuple[float, float]]:
        lo, hi = a, b
        for _ in range(24):
            mid = (lo + hi) / 2.0
            if hidden(mid) == state_a:
                lo = mid
            else:
                hi = mid
        fraction = (lo + hi) / 2.0
        return fraction, path.sample(fraction).point

    parts: list[_VisiblePart] = []
    start_fraction = 0.0
    previous_fraction = 0.0
    previous_hidden = hidden(0.0)
    current: list[tuple[float, float]] | None = None
    if not previous_hidden:
        current = [path.sample(0.0).point]

    for index in range(1, samples + 1):
        fraction = index / samples
        current_hidden = hidden(fraction)
        point = path.sample(fraction).point

        if current_hidden == previous_hidden:
            if not current_hidden and current is not None:
                current.append(point)
        elif not previous_hidden and current_hidden:
            edge_fraction, edge_point = boundary(
                previous_fraction, fraction, previous_hidden
            )
            assert current is not None
            current.append(edge_point)
            if len(current) >= 2:
                parts.append(
                    _VisiblePart(start_fraction, edge_fraction, tuple(current))
                )
            current = None
        else:
            edge_fraction, edge_point = boundary(
                previous_fraction, fraction, previous_hidden
            )
            start_fraction = edge_fraction
            current = [edge_point, point]

        previous_fraction = fraction
        previous_hidden = current_hidden

    if current is not None and len(current) >= 2:
        parts.append(_VisiblePart(start_fraction, 1.0, tuple(current)))

    if closed and len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        if first.start_fraction <= _EPSILON and last.end_fraction >= 1.0 - _EPSILON:
            merged_points = last.points + first.points[1:]
            merged = _VisiblePart(last.start_fraction, first.end_fraction, merged_points)
            parts = [merged] + parts[1:-1]

    return tuple(parts)


def _polyline_d(points: Sequence[tuple[float, float]]) -> str:
    if len(points) < 2:
        raise ValueError("visible trajectory part requires at least two points")
    commands = [f"M {_fmt(points[0][0])},{_fmt(points[0][1])}"]
    commands.extend(f"L {_fmt(x)},{_fmt(y)}" for x, y in points[1:])
    return " ".join(commands)


def _hide_construction_paths(group: ET.Element, element_id: str) -> None:
    for suffix in ("halo", "path"):
        child = group.find(f"{{{SVG_NS}}}path[@id='{element_id}-{suffix}']")
        if child is not None:
            existing = child.get("style")
            child.set("style", "display:none" if not existing else f"{existing};display:none")
            child.set(_q(PATCHCREATOR_NS, "construction-source"), "true")


def _render_visible_parts(
    element: Any,
    context: Any,
    parts: Sequence[_VisiblePart],
    *,
    main_attrs: Mapping[str, str],
    halo_attrs: Mapping[str, str] | None,
    arrow_attrs: Mapping[str, str] | None,
    closed: bool,
) -> None:
    visible = ET.SubElement(
        context.target_group,
        _q(SVG_NS, "g"),
        {"id": f"{element.id}-visible"},
    )
    for index, part in enumerate(parts):
        d = _polyline_d(part.points)
        if halo_attrs:
            ET.SubElement(
                visible,
                _q(SVG_NS, "path"),
                {
                    "id": f"{element.id}-visible-{index:03d}-halo",
                    "d": d,
                    **dict(halo_attrs),
                },
            )
        attrs = {
            "id": f"{element.id}-visible-{index:03d}",
            "d": d,
            **dict(main_attrs),
        }
        if not closed and arrow_attrs:
            if part.start_fraction <= _EPSILON and "marker-start" in arrow_attrs:
                attrs["marker-start"] = arrow_attrs["marker-start"]
            if part.end_fraction >= 1.0 - _EPSILON and "marker-end" in arrow_attrs:
                attrs["marker-end"] = arrow_attrs["marker-end"]
        ET.SubElement(visible, _q(SVG_NS, "path"), attrs)


def _occlusion_finalizer(
    *,
    path: PathSampler,
    specs: tuple[_OccluderSpec, ...],
    samples: int,
    near_side_angle: float | None,
    main_attrs: Mapping[str, str],
    halo_attrs: Mapping[str, str] | None,
    arrow_attrs: Mapping[str, str] | None,
    closed: bool,
):
    def finalize(finalize_context: ComponentFinalizeContext):
        resolved, warnings = _resolve_occluders(finalize_context, specs)
        if not resolved:
            return warnings

        is_near = (
            _orbit_near_predicate(path, near_side_angle)
            if isinstance(path, EllipsePath)
            else None
        )
        parts = _split_visible_parts(
            path,
            world_transform=finalize_context.scene_node.world_transform,
            occluders=resolved,
            samples=samples,
            closed=closed,
            is_near=is_near,
        )
        context = finalize_context.render_context
        element = finalize_context.element
        _hide_construction_paths(context.target_group, element.id)
        _render_visible_parts(
            element,
            context,
            parts,
            main_attrs=main_attrs,
            halo_attrs=halo_attrs,
            arrow_attrs=arrow_attrs,
            closed=closed,
        )
        context.target_group.set(
            _q(PATCHCREATOR_NS, "occlusion-targets"),
            " ".join(item.target for item in resolved),
        )
        context.target_group.set(_q(PATCHCREATOR_NS, "occlusion-mode"), "geometry-split")
        if near_side_angle is not None and isinstance(path, EllipsePath):
            context.target_group.set(
                _q(PATCHCREATOR_NS, "orbit-near-side-deg"),
                _fmt(near_side_angle),
            )
        return warnings

    return finalize


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
    occlusion = _parse_occlusion(config.get("occlusion"))
    finalizer = None
    if occlusion is not None:
        specs, samples, near_side = occlusion
        if near_side is not None:
            raise ValueError("near_side is only meaningful for procedural orbit occlusion")
        finalizer = _occlusion_finalizer(
            path=path,
            specs=specs,
            samples=samples,
            near_side_angle=None,
            main_attrs=main_attrs,
            halo_attrs=halo_attrs,
            arrow_attrs=arrows,
            closed=False,
        )

    context.target_group.set(_q(PATCHCREATOR_NS, "path-kind"), "trajectory")
    context.target_group.set(_q(PATCHCREATOR_NS, "path-length-mm"), _fmt(path.length()))
    return ComponentResult(
        bounds=_expanded(path.bounds, overall_width / 2.0),
        paths={element.id: path},
        finalize=finalizer,
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
    if config.get("radius_x") is None or config.get("radius_y") is None:
        raise ValueError("orbit requires radius_x and radius_y")
    radius_x = parse_length_mm(config["radius_x"])
    radius_y = parse_length_mm(config["radius_y"])
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

    occlusion = _parse_occlusion(config.get("occlusion"))
    finalizer = None
    if occlusion is not None:
        specs, samples, near_side = occlusion
        finalizer = _occlusion_finalizer(
            path=path,
            specs=specs,
            samples=samples,
            near_side_angle=near_side,
            main_attrs=main_attrs,
            halo_attrs=halo_attrs,
            arrow_attrs=None,
            closed=True,
        )

    context.target_group.set(_q(PATCHCREATOR_NS, "path-kind"), "orbit")
    context.target_group.set(_q(PATCHCREATOR_NS, "path-length-mm"), _fmt(path.length()))
    context.target_group.set(_q(PATCHCREATOR_NS, "orbit-phase-deg"), _fmt(phase))
    return ComponentResult(
        bounds=_expanded(path.bounds, overall_width / 2.0),
        paths={element.id: path},
        anchors={"orbit-centre": (0.0, 0.0)},
        finalize=finalizer,
    )
