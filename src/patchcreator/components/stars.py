"""Mission-patch star glyphs and deterministic decorative starfields."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random
import secrets
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Sequence

from patchcreator.components.registry import ComponentFinalizeContext, ComponentResult
from patchcreator.geometry import Bounds, parse_angle_degrees, parse_length_mm, parse_radius

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


def _star_points(points: int, outer: float, inner: float, rotation_degrees: float = -90.0) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = math.radians(rotation_degrees + index * 180.0 / points)
        result.append((radius * math.cos(angle), radius * math.sin(angle)))
    return result


def _four_point_points(radius: float, inner_ratio: float, *, narrow: bool = False) -> list[tuple[float, float]]:
    inner = radius * inner_ratio
    x_outer = radius * (0.72 if narrow else 1.0)
    y_outer = radius
    return [
        (0.0, -y_outer),
        (inner, -inner),
        (x_outer, 0.0),
        (inner, inner),
        (0.0, y_outer),
        (-inner, inner),
        (-x_outer, 0.0),
        (-inner, -inner),
    ]


def _points_attr(points: Iterable[tuple[float, float]]) -> str:
    return " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)


def _draw_glyph(
    parent: ET.Element,
    *,
    glyph: str,
    size: float,
    fill: str,
    stroke: str | None = None,
    stroke_width: float = 0.0,
    element_id: str | None = None,
) -> None:
    if size <= 0:
        raise ValueError("star size must be positive")
    radius = size / 2.0
    attrs: dict[str, str] = {"fill": fill}
    if element_id:
        attrs["id"] = element_id
    if stroke is not None and stroke_width > 0:
        attrs["stroke"] = stroke
        attrs["stroke-width"] = _fmt(stroke_width)
        attrs["stroke-linejoin"] = "round"

    if glyph == "dot":
        ET.SubElement(
            parent,
            _q(SVG_NS, "circle"),
            {"cx": "0", "cy": "0", "r": _fmt(radius), **attrs},
        )
        return

    if glyph == "four-point":
        points = _four_point_points(radius, 0.25)
    elif glyph == "four-point-narrow":
        points = _four_point_points(radius, 0.20, narrow=True)
    elif glyph == "five-point":
        points = _star_points(5, radius, radius * 0.382)
    elif glyph == "eight-point":
        points = _star_points(8, radius, radius * 0.38)
    else:
        raise ValueError(
            f"unknown star glyph {glyph!r}; expected dot, four-point, "
            "four-point-narrow, five-point or eight-point"
        )
    ET.SubElement(parent, _q(SVG_NS, "polygon"), {"points": _points_attr(points), **attrs})


def render_star(element: Any, context: Any) -> ComponentResult:
    """Render one explicitly positioned/semantic star centred at local origin."""
    cfg = element.component_config()
    glyph = str(cfg.get("glyph", "four-point"))
    size = parse_length_mm(cfg.get("size", 2.0))
    fill = _colour(context.design, str(cfg.get("fill", "#ffffff")))
    stroke_cfg = cfg.get("stroke") or {}
    stroke = None
    stroke_width = 0.0
    if stroke_cfg:
        stroke = _colour(context.design, str(stroke_cfg.get("colour", fill)))
        stroke_width = parse_length_mm(stroke_cfg.get("width", 0.0))

    _draw_glyph(
        context.target_group,
        glyph=glyph,
        size=size,
        fill=fill,
        stroke=stroke,
        stroke_width=stroke_width,
        element_id=f"{element.id}-glyph",
    )
    half = size / 2.0 + stroke_width / 2.0
    return ComponentResult(bounds=Bounds(-half, -half, half, half))


@dataclass(frozen=True)
class _Avoidance:
    target: str
    clearance: float


@dataclass(frozen=True)
class _Region:
    kind: str
    data: dict[str, Any]


def _field_seed(raw: Any) -> tuple[int, bool]:
    if raw is None or (isinstance(raw, str) and raw.strip().lower() == "auto"):
        return secrets.randbits(64), True
    if isinstance(raw, int):
        return raw & ((1 << 64) - 1), False
    text = str(raw)
    try:
        return int(text, 0) & ((1 << 64) - 1), False
    except ValueError:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big"), False


def _parse_avoidance(raw: Any) -> tuple[_Avoidance, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("starfield avoidance must be a list")
    result: list[_Avoidance] = []
    for item in raw:
        if isinstance(item, str):
            result.append(_Avoidance(item, 0.0))
            continue
        if not isinstance(item, dict) or not item.get("target"):
            raise ValueError("each starfield avoidance entry requires a target")
        result.append(
            _Avoidance(
                str(item["target"]),
                parse_length_mm(item.get("clearance", 0.0)),
            )
        )
    return tuple(result)


def _parse_region(raw: Any) -> _Region:
    if not isinstance(raw, dict):
        raise ValueError("starfield region must be a mapping")
    kind = str(raw.get("type", "annular-sector"))
    if kind not in {"annular-sector", "rectangle", "polygon"}:
        raise ValueError("starfield region type must be annular-sector, rectangle or polygon")
    return _Region(kind, dict(raw))


def _size_range(cfg: dict[str, Any]) -> tuple[float, float]:
    if "size_range" in cfg:
        raw = cfg["size_range"]
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError("starfield size_range must contain [minimum, maximum]")
        low, high = parse_length_mm(raw[0]), parse_length_mm(raw[1])
    else:
        value = parse_length_mm(cfg.get("size", 1.5))
        low = high = value
    if low <= 0 or high <= 0 or low > high:
        raise ValueError("starfield sizes must be positive and minimum <= maximum")
    return low, high


def _glyph_choices(cfg: dict[str, Any]) -> tuple[str, ...]:
    raw = cfg.get("glyphs", cfg.get("glyph", "four-point"))
    if isinstance(raw, str):
        choices = (raw,)
    elif isinstance(raw, Sequence):
        choices = tuple(str(item) for item in raw)
    else:
        raise ValueError("starfield glyph/glyphs must be a string or list")
    if not choices:
        raise ValueError("starfield glyphs may not be empty")
    allowed = {"dot", "four-point", "four-point-narrow", "five-point", "eight-point"}
    invalid = [item for item in choices if item not in allowed]
    if invalid:
        raise ValueError(f"unknown starfield glyph(s): {', '.join(invalid)}")
    return choices


def _angle_span(start: float, end: float) -> float:
    span = (end - start) % 360.0
    return 360.0 if abs(span) < 1e-12 else span


def _sample_region(region: _Region, rng: random.Random, geometry: Any) -> tuple[float, float]:
    cx, cy = geometry.centre
    data = region.data
    if region.kind == "annular-sector":
        inner = parse_radius(data.get("inner_radius", 0.0), geometry.reference_radius)
        outer = parse_radius(data.get("outer_radius", "1r"), geometry.reference_radius)
        if inner < 0 or outer <= 0 or inner >= outer:
            raise ValueError("annular-sector requires 0 <= inner_radius < outer_radius")
        start = parse_angle_degrees(data.get("angle_start", 0.0))
        end = parse_angle_degrees(data.get("angle_end", 360.0))
        angle = start + rng.random() * _angle_span(start, end)
        radius = math.sqrt(inner * inner + rng.random() * (outer * outer - inner * inner))
        theta = math.radians(angle)
        return cx + radius * math.sin(theta), cy - radius * math.cos(theta)

    if region.kind == "rectangle":
        width = parse_length_mm(data.get("width", geometry.width))
        height = parse_length_mm(data.get("height", geometry.height))
        if width <= 0 or height <= 0:
            raise ValueError("starfield rectangle width/height must be positive")
        x = parse_length_mm(data.get("x", -width / 2.0))
        y = parse_length_mm(data.get("y", -height / 2.0))
        return cx + x + rng.random() * width, cy + y + rng.random() * height

    points = _polygon_points(data.get("points"), geometry)
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    for _ in range(1000):
        point = (rng.uniform(min_x, max_x), rng.uniform(min_y, max_y))
        if _point_in_polygon(point, points):
            return point
    raise ValueError("failed to sample starfield polygon; check that it has non-zero area")


def _polygon_points(raw: Any, geometry: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list) or len(raw) < 3:
        raise ValueError("starfield polygon requires at least three points")
    cx, cy = geometry.centre
    points: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("starfield polygon points must be [x, y] pairs")
        points.append((cx + parse_length_mm(item[0]), cy + parse_length_mm(item[1])))
    return tuple(points)


def _point_in_polygon(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            intersect_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersect_x:
                inside = not inside
        previous = current
    return inside


def _expanded(bounds: Bounds, amount: float) -> Bounds:
    return Bounds(
        bounds.min_x - amount,
        bounds.min_y - amount,
        bounds.max_x + amount,
        bounds.max_y + amount,
    )


def _point_in_bounds(point: tuple[float, float], bounds: Bounds) -> bool:
    return bounds.min_x <= point[0] <= bounds.max_x and bounds.min_y <= point[1] <= bounds.max_y


def _inside_safe_area(point: tuple[float, float], radius: float, geometry: Any) -> bool:
    cx, cy = geometry.centre
    safe_rx = geometry.safe_width / 2.0 - radius
    safe_ry = geometry.safe_height / 2.0 - radius
    if safe_rx <= 0 or safe_ry <= 0:
        return False
    dx = point[0] - cx
    dy = point[1] - cy
    return (dx * dx) / (safe_rx * safe_rx) + (dy * dy) / (safe_ry * safe_ry) <= 1.0


def _finalize_starfield(
    *,
    seed: int,
    generated_seed: bool,
    region: _Region,
    avoidance: tuple[_Avoidance, ...],
    count: int,
    glyphs: tuple[str, ...],
    size_range: tuple[float, float],
    fill_name: str,
    minimum_separation: float,
    max_attempts: int,
    respect_safe_area: bool,
):
    def finalize(finalize_context: ComponentFinalizeContext) -> Iterable[str] | None:
        context = finalize_context.render_context
        node = finalize_context.scene_node
        graph = finalize_context.graph
        field_id = finalize_context.element.id
        rng = random.Random(seed)
        fill = _colour(context.design, fill_name)
        world_to_local = node.world_transform.inverse()
        warnings: list[str] = []

        avoid_bounds: list[tuple[str, Bounds]] = []
        for item in avoidance:
            try:
                target = graph.find(item.target)
            except KeyError as exc:
                raise ValueError(
                    f"starfield {field_id!r} avoidance target {item.target!r} does not exist"
                ) from exc
            if target.resolved_bounds is None:
                if item.target in finalize_context.skipped_node_ids:
                    warnings.append(
                        f"starfield {field_id!r} could not apply avoidance target {item.target!r}: "
                        "target was skipped in this partial render"
                    )
                    continue
                raise ValueError(
                    f"starfield {field_id!r} avoidance target {item.target!r} has no resolved geometry"
                )
            avoid_bounds.append((item.target, _expanded(target.resolved_bounds, item.clearance)))

        placed: list[tuple[tuple[float, float], float]] = []
        attempts = 0
        while len(placed) < count and attempts < max_attempts:
            attempts += 1
            point = _sample_region(region, rng, context.geometry)
            size = rng.uniform(*size_range)
            radius = size / 2.0
            if respect_safe_area and not _inside_safe_area(point, radius, context.geometry):
                continue
            if any(_point_in_bounds(point, _expanded(bounds, radius)) for _, bounds in avoid_bounds):
                continue
            if any(
                math.hypot(point[0] - other[0][0], point[1] - other[0][1])
                < radius + other[1] + minimum_separation
                for other in placed
            ):
                continue

            glyph = rng.choice(glyphs)
            local = world_to_local.apply(point)
            star_group = ET.SubElement(
                context.target_group,
                _q(SVG_NS, "g"),
                {
                    "id": f"{field_id}-star-{len(placed):03d}",
                    "transform": f"translate({_fmt(local[0])} {_fmt(local[1])})",
                },
            )
            _draw_glyph(star_group, glyph=glyph, size=size, fill=fill)
            placed.append((point, radius))

        context.target_group.set(_q(PATCHCREATOR_NS, "seed"), str(seed))
        context.target_group.set(_q(PATCHCREATOR_NS, "requested-count"), str(count))
        context.target_group.set(_q(PATCHCREATOR_NS, "placed-count"), str(len(placed)))

        if generated_seed:
            warnings.append(
                f"starfield {field_id!r} generated seed {seed}; set seed: {seed} to reproduce this layout"
            )
        if len(placed) < count:
            warnings.append(
                f"starfield {field_id!r} placed {len(placed)} of {count} stars after {attempts} attempts; "
                "reduce count/clearance or enlarge the region"
            )
        return warnings

    return finalize


def render_starfield(element: Any, context: Any) -> ComponentResult:
    """Prepare a decorative starfield, finalized after scene placement.

    Region coordinates are patch/document based: rectangle and polygon x/y
    values are relative to patch centre, while annular-sector uses patch-centred
    polar coordinates. The generated points are transformed back into the
    starfield node's local SVG coordinates during finalization.
    """
    cfg = element.component_config()
    count = int(cfg.get("count", 12))
    if count < 0:
        raise ValueError("starfield count may not be negative")
    region = _parse_region(cfg.get("region", {"type": "annular-sector"}))
    avoidance = _parse_avoidance(cfg.get("avoidance"))
    glyphs = _glyph_choices(cfg)
    size_range = _size_range(cfg)
    fill_name = str(cfg.get("fill", "#ffffff"))
    minimum_separation = parse_length_mm(cfg.get("minimum_separation", 0.5))
    if minimum_separation < 0:
        raise ValueError("starfield minimum_separation may not be negative")
    max_attempts = int(cfg.get("max_attempts", max(500, count * 250)))
    if max_attempts <= 0:
        raise ValueError("starfield max_attempts must be positive")
    respect_safe_area = bool(cfg.get("respect_safe_area", True))
    seed, generated_seed = _field_seed(cfg.get("seed"))

    # Conservative prepare-time geometry: decorative starfields are patch-space
    # generators and may sample anywhere in their configured region. Exact
    # generated-star bounds are deliberately not fed back into placement after
    # finalization.
    bounds = Bounds(0.0, 0.0, context.geometry.width, context.geometry.height)
    return ComponentResult(
        bounds=bounds,
        finalize=_finalize_starfield(
            seed=seed,
            generated_seed=generated_seed,
            region=region,
            avoidance=avoidance,
            count=count,
            glyphs=glyphs,
            size_range=size_range,
            fill_name=fill_name,
            minimum_separation=minimum_separation,
            max_attempts=max_attempts,
            respect_safe_area=respect_safe_area,
        ),
    )
