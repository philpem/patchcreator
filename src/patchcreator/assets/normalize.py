"""Inspect and conservatively normalise reusable SVG assets.

The normaliser deliberately avoids becoming a general SVG renderer. Geometry
bounds are exact for common primitive shapes and conservative for path curves,
which is appropriate when fixing a missing/incorrect viewBox: a slightly loose
viewBox is preferable to clipping artwork.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Iterable

from patchcreator.components.assets import _parse_transform
from patchcreator.geometry import AffineTransform, Bounds

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)

_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_PATH_TOKEN_RE = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_POINTS_SPLIT_RE = re.compile(r"[\s,]+")

_NON_RENDERED_CONTAINERS = {
    "defs",
    "clipPath",
    "mask",
    "marker",
    "metadata",
    "title",
    "desc",
    "symbol",
}


@dataclass(frozen=True)
class AssetReport:
    source: Path
    viewbox: tuple[float, float, float, float] | None
    physical_size_mm: tuple[float | None, float | None]
    bounds: Bounds | None
    anchors: tuple[str, ...]
    colour_roles: tuple[str, ...]
    transform_count: int
    flattened_transform_count: int = 0
    unsupported_geometry: tuple[str, ...] = ()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = _NUMBER_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"unsupported SVG numeric value {value!r}")
    return float(value)


def _physical_length_mm(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().lower()
    conversions = {
        "mm": 1.0,
        "cm": 10.0,
        "in": 25.4,
        "px": 25.4 / 96.0,
        "pt": 25.4 / 72.0,
    }
    for suffix, scale in conversions.items():
        if text.endswith(suffix):
            try:
                return float(text[: -len(suffix)].strip()) * scale
            except ValueError:
                return None
    return None


def _parse_viewbox(root: ET.Element) -> tuple[float, float, float, float] | None:
    raw = root.get("viewBox")
    if not raw:
        return None
    parts = [part for part in _POINTS_SPLIT_RE.split(raw.strip()) if part]
    if len(parts) != 4:
        raise ValueError(f"invalid SVG viewBox {raw!r}")
    try:
        result = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"invalid SVG viewBox {raw!r}") from exc
    if result[2] <= 0 or result[3] <= 0:
        raise ValueError("SVG viewBox width/height must be positive")
    return result  # type: ignore[return-value]


def _parse_style(style: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if not style:
        return result
    for declaration in style.split(";"):
        if ":" not in declaration:
            continue
        key, value = declaration.split(":", 1)
        result[key.strip().lower()] = value.strip()
    return result


def _hidden(element: ET.Element) -> bool:
    if element.get("display", "").strip().lower() == "none":
        return True
    style = _parse_style(element.get("style"))
    return style.get("display", "").lower() == "none"


def _transform_bounds(bounds: Bounds, transform: AffineTransform) -> Bounds:
    return Bounds.from_points(transform.apply(point) for point in bounds.corners)


def _primitive_bounds(element: ET.Element) -> Bounds | None:
    tag = _local_name(element.tag)
    if tag == "rect":
        x = _number(element.get("x"))
        y = _number(element.get("y"))
        width = _number(element.get("width"))
        height = _number(element.get("height"))
        if width < 0 or height < 0:
            raise ValueError("SVG rect width/height must not be negative")
        return Bounds(x, y, x + width, y + height)
    if tag == "circle":
        cx, cy, radius = _number(element.get("cx")), _number(element.get("cy")), _number(element.get("r"))
        if radius < 0:
            raise ValueError("SVG circle radius must not be negative")
        return Bounds(cx - radius, cy - radius, cx + radius, cy + radius)
    if tag == "ellipse":
        cx, cy = _number(element.get("cx")), _number(element.get("cy"))
        rx, ry = _number(element.get("rx")), _number(element.get("ry"))
        if rx < 0 or ry < 0:
            raise ValueError("SVG ellipse radii must not be negative")
        return Bounds(cx - rx, cy - ry, cx + rx, cy + ry)
    if tag == "line":
        return Bounds.from_points(
            [
                (_number(element.get("x1")), _number(element.get("y1"))),
                (_number(element.get("x2")), _number(element.get("y2"))),
            ]
        )
    if tag in {"polyline", "polygon"}:
        raw = element.get("points", "")
        values = [part for part in _POINTS_SPLIT_RE.split(raw.strip()) if part]
        if len(values) < 2 or len(values) % 2:
            raise ValueError(f"invalid SVG {tag} points")
        points = [(float(values[index]), float(values[index + 1])) for index in range(0, len(values), 2)]
        return Bounds.from_points(points)
    if tag == "path":
        return _path_conservative_bounds(element.get("d", ""))
    return None


def _path_conservative_bounds(d: str) -> Bounds | None:
    """Return conservative path bounds from endpoints/control points.

    Cubic/quadratic curves lie inside their control polygon, so including every
    control point is a safe over-bound. Arc commands add generous endpoint/radius
    boxes; this may be loose but will not intentionally tighten a viewBox around
    unparsed arc extrema.
    """

    tokens = _PATH_TOKEN_RE.findall(d)
    if not tokens:
        return None
    index = 0
    command: str | None = None
    current = (0.0, 0.0)
    subpath_start = current
    points: list[tuple[float, float]] = []

    def is_command(token: str) -> bool:
        return len(token) == 1 and token.isalpha()

    def take(count: int) -> list[float]:
        nonlocal index
        if index + count > len(tokens) or any(is_command(token) for token in tokens[index : index + count]):
            raise ValueError("malformed SVG path data")
        values = [float(token) for token in tokens[index : index + count]]
        index += count
        return values

    def point(x: float, y: float, relative: bool) -> tuple[float, float]:
        return (current[0] + x, current[1] + y) if relative else (x, y)

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if command is None:
            raise ValueError("SVG path data must begin with a command")
        relative = command.islower()
        op = command.upper()

        if op == "Z":
            current = subpath_start
            points.append(current)
            command = None
            continue
        if op in {"M", "L", "T"}:
            values = take(2)
            current = point(values[0], values[1], relative)
            points.append(current)
            if op == "M":
                subpath_start = current
                command = "l" if relative else "L"
            continue
        if op == "H":
            value = take(1)[0]
            current = (current[0] + value if relative else value, current[1])
            points.append(current)
            continue
        if op == "V":
            value = take(1)[0]
            current = (current[0], current[1] + value if relative else value)
            points.append(current)
            continue
        if op == "C":
            values = take(6)
            c1 = point(values[0], values[1], relative)
            c2 = point(values[2], values[3], relative)
            end = point(values[4], values[5], relative)
            points.extend((c1, c2, end))
            current = end
            continue
        if op in {"S", "Q"}:
            values = take(4)
            control = point(values[0], values[1], relative)
            end = point(values[2], values[3], relative)
            points.extend((control, end))
            current = end
            continue
        if op == "A":
            values = take(7)
            rx, ry = abs(values[0]), abs(values[1])
            end = point(values[5], values[6], relative)
            # Conservative boxes around both arc endpoints. SVG may scale radii
            # upward for impossible endpoint/radius combinations, so double the
            # nominal radius to remain deliberately loose rather than clipping.
            reach = max(rx, ry) * 2.0
            for px, py in (current, end):
                points.extend(((px - reach, py - reach), (px + reach, py + reach)))
            points.append(end)
            current = end
            continue
        raise ValueError(f"unsupported SVG path command {command!r}")

    return Bounds.from_points(points) if points else None


def _stroke_expansion(element: ET.Element) -> float:
    style = _parse_style(element.get("style"))
    stroke = element.get("stroke", style.get("stroke"))
    if stroke is None or stroke.strip().lower() == "none":
        return 0.0
    raw = element.get("stroke-width", style.get("stroke-width", "1"))
    try:
        return max(0.0, _number(raw) / 2.0)
    except ValueError:
        return 0.0


def _expanded(bounds: Bounds, amount: float) -> Bounds:
    return Bounds(bounds.min_x - amount, bounds.min_y - amount, bounds.max_x + amount, bounds.max_y + amount)


def _collect_geometry(root: ET.Element) -> tuple[Bounds | None, set[str]]:
    result: Bounds | None = None
    unsupported: set[str] = set()

    def visit(element: ET.Element, parent_transform: AffineTransform, hidden: bool, non_rendered: bool) -> None:
        nonlocal result
        tag = _local_name(element.tag)
        now_hidden = hidden or _hidden(element)
        now_non_rendered = non_rendered or tag in _NON_RENDERED_CONTAINERS
        transform = parent_transform @ _parse_transform(element.get("transform"))

        if not now_hidden and not now_non_rendered:
            bounds = _primitive_bounds(element)
            if bounds is not None:
                bounds = _expanded(bounds, _stroke_expansion(element))
                bounds = _transform_bounds(bounds, transform)
                result = bounds if result is None else Bounds.union(result, bounds)
            elif tag not in {"svg", "g", "a", "style"} and len(element) == 0:
                unsupported.add(tag)

        for child in element:
            visit(child, transform, now_hidden, now_non_rendered)

    for child in root:
        visit(child, AffineTransform.identity(), False, False)
    return result, unsupported


def _metadata(root: ET.Element) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    anchors: set[str] = set()
    roles: set[str] = set()
    transforms = 0
    for element in root.iter():
        if element.get("transform"):
            transforms += 1
        anchor = element.get("data-patchcreator-anchor")
        if anchor:
            anchors.add(anchor)
        for attr in (
            "data-patchcreator-colour-role",
            "data-patchcreator-fill-role",
            "data-patchcreator-stroke-role",
        ):
            role = element.get(attr)
            if role:
                roles.add(role)
    return tuple(sorted(anchors)), tuple(sorted(roles)), transforms


def _safe_uniform_transform(transform: AffineTransform) -> tuple[float, float, float] | None:
    if abs(transform.b) > 1e-12 or abs(transform.c) > 1e-12:
        return None
    if transform.a <= 0 or transform.d <= 0 or abs(transform.a - transform.d) > 1e-12:
        return None
    return transform.a, transform.e, transform.f


def _set_number(element: ET.Element, name: str, value: float) -> None:
    element.set(name, f"{value:.12g}")


def _flatten_leaf_transform(element: ET.Element) -> bool:
    raw = element.get("transform")
    if not raw or len(element):
        return False
    transform = _parse_transform(raw)
    safe = _safe_uniform_transform(transform)
    if safe is None:
        return False
    scale, tx, ty = safe
    tag = _local_name(element.tag)

    if tag == "rect":
        _set_number(element, "x", _number(element.get("x")) * scale + tx)
        _set_number(element, "y", _number(element.get("y")) * scale + ty)
        _set_number(element, "width", _number(element.get("width")) * scale)
        _set_number(element, "height", _number(element.get("height")) * scale)
        for attr in ("rx", "ry"):
            if element.get(attr) is not None:
                _set_number(element, attr, _number(element.get(attr)) * scale)
    elif tag == "circle":
        _set_number(element, "cx", _number(element.get("cx")) * scale + tx)
        _set_number(element, "cy", _number(element.get("cy")) * scale + ty)
        _set_number(element, "r", _number(element.get("r")) * scale)
    elif tag == "ellipse":
        _set_number(element, "cx", _number(element.get("cx")) * scale + tx)
        _set_number(element, "cy", _number(element.get("cy")) * scale + ty)
        _set_number(element, "rx", _number(element.get("rx")) * scale)
        _set_number(element, "ry", _number(element.get("ry")) * scale)
    elif tag == "line":
        for xattr in ("x1", "x2"):
            _set_number(element, xattr, _number(element.get(xattr)) * scale + tx)
        for yattr in ("y1", "y2"):
            _set_number(element, yattr, _number(element.get(yattr)) * scale + ty)
    elif tag in {"polyline", "polygon"}:
        raw_points = [part for part in _POINTS_SPLIT_RE.split(element.get("points", "").strip()) if part]
        if len(raw_points) < 2 or len(raw_points) % 2:
            return False
        values = [float(value) for value in raw_points]
        converted: list[str] = []
        for index in range(0, len(values), 2):
            converted.append(f"{values[index] * scale + tx:.12g},{values[index + 1] * scale + ty:.12g}")
        element.set("points", " ".join(converted))
    else:
        return False

    # Scaling an ordinary stroke with the geometry matches SVG transform
    # semantics unless vector-effect explicitly requests non-scaling stroke.
    if element.get("vector-effect") != "non-scaling-stroke":
        style = _parse_style(element.get("style"))
        if element.get("stroke-width") is not None:
            _set_number(element, "stroke-width", _number(element.get("stroke-width")) * scale)
        elif "stroke-width" in style:
            try:
                width = _number(style["stroke-width"]) * scale
            except ValueError:
                pass
            else:
                style["stroke-width"] = f"{width:.12g}"
                element.set("style", ";".join(f"{key}:{value}" for key, value in style.items()))

    element.attrib.pop("transform", None)
    return True


def _flatten_safe_leaf_transforms(root: ET.Element) -> int:
    count = 0
    for element in root.iter():
        if _flatten_leaf_transform(element):
            count += 1
    return count


def _load(path: str | Path) -> tuple[Path, ET.ElementTree, ET.Element]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if "<!DOCTYPE" in text.upper():
        raise ValueError("SVG assets with a DOCTYPE are not supported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"failed to parse SVG asset {source}: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise ValueError(f"asset {source} is not an SVG document")
    return source, ET.ElementTree(root), root


def _report(source: Path, root: ET.Element, *, flattened: int = 0) -> AssetReport:
    viewbox = _parse_viewbox(root)
    bounds, unsupported = _collect_geometry(root)
    anchors, roles, transforms = _metadata(root)
    return AssetReport(
        source=source,
        viewbox=viewbox,
        physical_size_mm=(
            _physical_length_mm(root.get("width")),
            _physical_length_mm(root.get("height")),
        ),
        bounds=bounds,
        anchors=anchors,
        colour_roles=roles,
        transform_count=transforms,
        flattened_transform_count=flattened,
        unsupported_geometry=tuple(sorted(unsupported)),
    )


def inspect_asset(path: str | Path) -> AssetReport:
    """Inspect a reusable SVG without modifying it."""
    source, _, root = _load(path)
    return _report(source, root)


def normalize_asset(
    path: str | Path,
    *,
    output: str | Path,
    fix_viewbox: bool = False,
    padding: float = 0.0,
    flatten_safe_transforms: bool = False,
) -> AssetReport:
    """Write a conservatively normalised copy and return its final report."""
    if padding < 0:
        raise ValueError("normalizer padding must not be negative")
    source, tree, root = _load(path)
    flattened = _flatten_safe_leaf_transforms(root) if flatten_safe_transforms else 0

    if fix_viewbox:
        bounds, unsupported = _collect_geometry(root)
        if bounds is None:
            raise ValueError("cannot fix viewBox: no supported visible geometry was found")
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(
                "cannot safely fix viewBox while unsupported visible geometry is present: " + names
            )
        bounds = _expanded(bounds, padding)
        root.set(
            "viewBox",
            f"{bounds.min_x:.12g} {bounds.min_y:.12g} {bounds.width:.12g} {bounds.height:.12g}",
        )

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(destination, encoding="unicode", xml_declaration=True)
    report = _report(destination, root, flattened=flattened)
    return report
