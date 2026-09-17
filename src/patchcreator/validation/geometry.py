"""Physical filled-geometry extraction for embroidery validators.

This is intentionally an analysis representation: source SVG curves remain
untouched. Curves are flattened only here, into physical-millimetre Shapely
geometry suitable for feature, gap and overlap measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import xml.etree.ElementTree as ET
from typing import Iterator, Sequence

from shapely import affinity
from shapely.geometry import GeometryCollection, Point as ShapelyPoint, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from patchcreator.components.assets import _parse_transform
from patchcreator.geometry import AffineTransform

from .svg import (
    SvgInspectionError,
    _NON_RENDERED_CONTAINERS,
    _is_construction,
    _local_name,
    _parse_opacity,
    _parse_root_length_mm,
    _property,
    _style,
)

_PATH_TOKEN_RE = re.compile(
    r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
)
_POINTS_SPLIT_RE = re.compile(r"[\s,]+")
_EPSILON = 1e-12


@dataclass(frozen=True)
class FilledGeometry:
    element_id: str | None
    element_tag: str
    geometry: BaseGeometry


class UnsupportedFilledGeometry(ValueError):
    pass


def _root_transform_mm(root: ET.Element) -> AffineTransform:
    raw_viewbox = root.get("viewBox")
    if raw_viewbox is None:
        scale = 25.4 / 96.0
        return AffineTransform.scale(scale)

    parts = raw_viewbox.replace(",", " ").split()
    if len(parts) != 4:
        raise SvgInspectionError(f"invalid SVG viewBox {raw_viewbox!r}")
    try:
        min_x, min_y, view_width, view_height = (float(part) for part in parts)
    except ValueError as exc:
        raise SvgInspectionError(f"invalid SVG viewBox {raw_viewbox!r}") from exc
    if view_width <= 0 or view_height <= 0:
        raise SvgInspectionError("SVG viewBox width/height must be positive")

    width_mm = _parse_root_length_mm(root.get("width"), name="width")
    height_mm = _parse_root_length_mm(root.get("height"), name="height")
    preserve = (root.get("preserveAspectRatio") or "xMidYMid meet").strip()
    if preserve.lower() == "none":
        return (
            AffineTransform.scale(width_mm / view_width, height_mm / view_height)
            @ AffineTransform.translation(-min_x, -min_y)
        )

    fields = preserve.split()
    align = fields[0] if fields else "xMidYMid"
    mode = fields[1].lower() if len(fields) > 1 else "meet"
    if mode not in {"meet", "slice"}:
        mode = "meet"
    scale_x = width_mm / view_width
    scale_y = height_mm / view_height
    scale = min(scale_x, scale_y) if mode == "meet" else max(scale_x, scale_y)
    content_width = view_width * scale
    content_height = view_height * scale
    extra_x = width_mm - content_width
    extra_y = height_mm - content_height
    offset_x = 0.0 if "xMin" in align else extra_x if "xMax" in align else extra_x / 2.0
    offset_y = 0.0 if "YMin" in align else extra_y if "YMax" in align else extra_y / 2.0
    return (
        AffineTransform.translation(offset_x, offset_y)
        @ AffineTransform.scale(scale)
        @ AffineTransform.translation(-min_x, -min_y)
    )


def _shapely_transform(geometry: BaseGeometry, transform: AffineTransform) -> BaseGeometry:
    # Shapely uses [a, b, d, e, xoff, yoff] for
    # x'=a*x+b*y+xoff; y'=d*x+e*y+yoff.
    return affinity.affine_transform(
        geometry,
        [
            transform.a,
            transform.c,
            transform.b,
            transform.d,
            transform.e,
            transform.f,
        ],
    )


def _number(raw: str | None, default: float = 0.0) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise UnsupportedFilledGeometry(f"unsupported SVG numeric value {raw!r}") from exc


def _polygon(points: Sequence[tuple[float, float]]) -> BaseGeometry:
    if len(points) < 3:
        return GeometryCollection()
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon


def _points_geometry(raw: str) -> BaseGeometry:
    values = [part for part in _POINTS_SPLIT_RE.split(raw.strip()) if part]
    if len(values) < 6 or len(values) % 2:
        raise UnsupportedFilledGeometry("invalid polygon/polyline points")
    try:
        points = [
            (float(values[index]), float(values[index + 1]))
            for index in range(0, len(values), 2)
        ]
    except ValueError as exc:
        raise UnsupportedFilledGeometry("invalid polygon/polyline coordinate") from exc
    return _polygon(points)


def _primitive_geometry(element: ET.Element, *, fill_rule: str) -> BaseGeometry | None:
    tag = _local_name(element.tag)
    if tag == "rect":
        x, y = _number(element.get("x")), _number(element.get("y"))
        width, height = _number(element.get("width")), _number(element.get("height"))
        if width <= 0 or height <= 0:
            return GeometryCollection()
        # Rounded corners only reduce area; the bounding rectangle is a
        # conservative feature-size representation until exact rounded-rect
        # flattening is needed by the gap validator.
        return box(x, y, x + width, y + height)
    if tag == "circle":
        radius = _number(element.get("r"))
        if radius <= 0:
            return GeometryCollection()
        return ShapelyPoint(_number(element.get("cx")), _number(element.get("cy"))).buffer(
            radius, quad_segs=32
        )
    if tag == "ellipse":
        rx, ry = _number(element.get("rx")), _number(element.get("ry"))
        if rx <= 0 or ry <= 0:
            return GeometryCollection()
        geometry = ShapelyPoint(0, 0).buffer(1.0, quad_segs=32)
        geometry = affinity.scale(geometry, xfact=rx, yfact=ry, origin=(0, 0))
        return affinity.translate(
            geometry,
            xoff=_number(element.get("cx")),
            yoff=_number(element.get("cy")),
        )
    if tag in {"polygon", "polyline"}:
        return _points_geometry(element.get("points", ""))
    if tag == "path":
        return _path_fill_geometry(element.get("d", ""), fill_rule=fill_rule)
    return None


def _sample_cubic(
    start: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    end: tuple[float, float],
    *,
    steps: int = 24,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(1, steps + 1):
        t = index / steps
        u = 1.0 - t
        points.append(
            (
                u**3 * start[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
                u**3 * start[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1],
            )
        )
    return points


def _sample_quadratic(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    *,
    steps: int = 16,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(1, steps + 1):
        t = index / steps
        u = 1.0 - t
        points.append(
            (
                u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
                u * u * start[1] + 2 * u * t * control[1] + t * t * end[1],
            )
        )
    return points


def _vector_angle(u: tuple[float, float], v: tuple[float, float]) -> float:
    dot = u[0] * v[0] + u[1] * v[1]
    cross = u[0] * v[1] - u[1] * v[0]
    return math.atan2(cross, dot)


def _sample_arc(
    start: tuple[float, float],
    rx: float,
    ry: float,
    rotation_degrees: float,
    large_arc: bool,
    sweep: bool,
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    """Flatten an SVG endpoint-parameterized elliptical arc."""
    rx, ry = abs(rx), abs(ry)
    if rx <= _EPSILON or ry <= _EPSILON or (
        abs(start[0] - end[0]) <= _EPSILON and abs(start[1] - end[1]) <= _EPSILON
    ):
        return [end]

    phi = math.radians(rotation_degrees % 360.0)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx = (start[0] - end[0]) / 2.0
    dy = (start[1] - end[1]) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    radii_scale = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if radii_scale > 1.0:
        factor = math.sqrt(radii_scale)
        rx *= factor
        ry *= factor

    numerator = max(
        0.0,
        rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p,
    )
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coefficient = 0.0 if denominator <= _EPSILON else math.sqrt(numerator / denominator)
    if large_arc == sweep:
        coefficient = -coefficient
    cxp = coefficient * (rx * y1p / ry)
    cyp = coefficient * (-ry * x1p / rx)

    cx = cos_phi * cxp - sin_phi * cyp + (start[0] + end[0]) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (start[1] + end[1]) / 2.0

    start_vector = ((x1p - cxp) / rx, (y1p - cyp) / ry)
    end_vector = ((-x1p - cxp) / rx, (-y1p - cyp) / ry)
    theta1 = _vector_angle((1.0, 0.0), start_vector)
    delta = _vector_angle(start_vector, end_vector)
    if not sweep and delta > 0:
        delta -= math.tau
    elif sweep and delta < 0:
        delta += math.tau

    steps = max(2, min(256, int(math.ceil(abs(delta) / math.radians(5.0)))))
    points: list[tuple[float, float]] = []
    for index in range(1, steps + 1):
        theta = theta1 + delta * index / steps
        x = cos_phi * rx * math.cos(theta) - sin_phi * ry * math.sin(theta) + cx
        y = sin_phi * rx * math.cos(theta) + cos_phi * ry * math.sin(theta) + cy
        points.append((x, y))
    points[-1] = end
    return points


def _path_subpaths(d: str) -> list[list[tuple[float, float]]]:
    tokens = _PATH_TOKEN_RE.findall(d)
    if not tokens:
        return []
    index = 0
    command: str | None = None
    current = (0.0, 0.0)
    start = current
    subpath: list[tuple[float, float]] = []
    subpaths: list[list[tuple[float, float]]] = []
    previous_cubic: tuple[float, float] | None = None
    previous_quad: tuple[float, float] | None = None

    def is_command(token: str) -> bool:
        return len(token) == 1 and token.isalpha()

    def take(count: int) -> list[float]:
        nonlocal index
        if index + count > len(tokens) or any(is_command(token) for token in tokens[index : index + count]):
            raise UnsupportedFilledGeometry("malformed SVG path data")
        result = [float(token) for token in tokens[index : index + count]]
        index += count
        return result

    def resolve(x: float, y: float, relative: bool) -> tuple[float, float]:
        return (current[0] + x, current[1] + y) if relative else (x, y)

    def finish() -> None:
        nonlocal subpath
        if len(subpath) >= 3:
            subpaths.append(subpath)
        subpath = []

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if command is None:
            raise UnsupportedFilledGeometry("SVG path must begin with a command")
        relative = command.islower()
        op = command.upper()

        if op == "Z":
            if subpath and subpath[-1] != start:
                subpath.append(start)
            current = start
            finish()
            previous_cubic = previous_quad = None
            command = None
            continue

        if op == "M":
            values = take(2)
            if subpath:
                finish()
            current = resolve(values[0], values[1], relative)
            start = current
            subpath = [current]
            command = "l" if relative else "L"
            previous_cubic = previous_quad = None
            continue

        if not subpath:
            subpath = [current]
            start = current

        if op == "L":
            values = take(2)
            current = resolve(values[0], values[1], relative)
            subpath.append(current)
            previous_cubic = previous_quad = None
            continue
        if op == "H":
            value = take(1)[0]
            current = (current[0] + value if relative else value, current[1])
            subpath.append(current)
            previous_cubic = previous_quad = None
            continue
        if op == "V":
            value = take(1)[0]
            current = (current[0], current[1] + value if relative else value)
            subpath.append(current)
            previous_cubic = previous_quad = None
            continue
        if op == "C":
            values = take(6)
            c1 = resolve(values[0], values[1], relative)
            c2 = resolve(values[2], values[3], relative)
            end = resolve(values[4], values[5], relative)
            subpath.extend(_sample_cubic(current, c1, c2, end))
            current, previous_cubic, previous_quad = end, c2, None
            continue
        if op == "S":
            values = take(4)
            c1 = (
                (2 * current[0] - previous_cubic[0], 2 * current[1] - previous_cubic[1])
                if previous_cubic is not None
                else current
            )
            c2 = resolve(values[0], values[1], relative)
            end = resolve(values[2], values[3], relative)
            subpath.extend(_sample_cubic(current, c1, c2, end))
            current, previous_cubic, previous_quad = end, c2, None
            continue
        if op == "Q":
            values = take(4)
            control = resolve(values[0], values[1], relative)
            end = resolve(values[2], values[3], relative)
            subpath.extend(_sample_quadratic(current, control, end))
            current, previous_quad, previous_cubic = end, control, None
            continue
        if op == "T":
            values = take(2)
            control = (
                (2 * current[0] - previous_quad[0], 2 * current[1] - previous_quad[1])
                if previous_quad is not None
                else current
            )
            end = resolve(values[0], values[1], relative)
            subpath.extend(_sample_quadratic(current, control, end))
            current, previous_quad, previous_cubic = end, control, None
            continue
        if op == "A":
            values = take(7)
            end = resolve(values[5], values[6], relative)
            subpath.extend(
                _sample_arc(
                    current,
                    values[0],
                    values[1],
                    values[2],
                    bool(int(values[3])),
                    bool(int(values[4])),
                    end,
                )
            )
            current = end
            previous_cubic = previous_quad = None
            continue
        raise UnsupportedFilledGeometry(f"unsupported SVG path command {command!r}")

    if subpath:
        finish()
    return subpaths


def _path_fill_geometry(d: str, *, fill_rule: str) -> BaseGeometry:
    polygons: list[BaseGeometry] = []
    for subpath in _path_subpaths(d):
        polygon = _polygon(subpath)
        if not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        return GeometryCollection()

    if fill_rule == "evenodd":
        geometry: BaseGeometry = GeometryCollection()
        for polygon in polygons:
            geometry = geometry.symmetric_difference(polygon)
        return geometry
    # Non-zero winding is usually represented by oppositely oriented nested
    # rings. `unary_union` is conservative for feature-size detection: it can
    # overestimate area when such holes are present, but it will not invent a
    # tiny island finding. Exact winding reconstruction can be added once gap
    # and overlap validation need it.
    return unary_union(polygons)


def iter_visible_fills(root: ET.Element) -> Iterator[FilledGeometry]:
    """Yield visible fill geometry transformed into document millimetres."""

    root_transform = _root_transform_mm(root)

    def walk(
        element: ET.Element,
        transform: AffineTransform,
        inherited_fill: str,
        inherited_fill_rule: str,
        inherited_visibility: str,
        inherited_fill_opacity: float,
        ancestor_opacity: float,
        ancestor_hidden: bool,
        non_rendered: bool,
    ) -> Iterator[FilledGeometry]:
        tag = _local_name(element.tag)
        style = _style(element)
        display = _property(element, style, "display", None)
        hidden = ancestor_hidden or (display is not None and display.strip().lower() == "none")
        visibility = (_property(element, style, "visibility", inherited_visibility) or "visible").strip().lower()
        now_non_rendered = (
            non_rendered
            or tag in _NON_RENDERED_CONTAINERS
            or _is_construction(element)
        )
        local_transform = transform @ _parse_transform(element.get("transform"))

        fill = (_property(element, style, "fill", inherited_fill) or "black").strip()
        fill_rule = (_property(element, style, "fill-rule", inherited_fill_rule) or "nonzero").strip().lower()
        fill_opacity = inherited_fill_opacity * _parse_opacity(_property(element, style, "fill-opacity", None))
        opacity = ancestor_opacity * _parse_opacity(_property(element, style, "opacity", None))

        if (
            not hidden
            and not now_non_rendered
            and visibility not in {"hidden", "collapse"}
            and opacity > 0.0
            and fill_opacity > 0.0
            and fill.lower() not in {"none", "transparent"}
        ):
            try:
                geometry = _primitive_geometry(element, fill_rule=fill_rule)
            except UnsupportedFilledGeometry:
                geometry = None
            if geometry is not None and not geometry.is_empty:
                geometry = _shapely_transform(geometry, root_transform @ local_transform)
                if not geometry.is_empty:
                    yield FilledGeometry(element.get("id"), tag, geometry)

        for child in element:
            yield from walk(
                child,
                local_transform,
                fill,
                fill_rule,
                visibility,
                fill_opacity,
                opacity,
                hidden,
                now_non_rendered,
            )

    for child in root:
        yield from walk(
            child,
            AffineTransform.identity(),
            "black",
            "nonzero",
            "visible",
            1.0,
            1.0,
            False,
            False,
        )


def polygon_components(geometry: BaseGeometry) -> tuple[Polygon, ...]:
    """Return all connected polygon components from a Shapely geometry."""
    if geometry.is_empty:
        return ()
    if isinstance(geometry, Polygon):
        return (geometry,)
    result: list[Polygon] = []
    for item in getattr(geometry, "geoms", ()):
        result.extend(polygon_components(item))
    return tuple(result)
