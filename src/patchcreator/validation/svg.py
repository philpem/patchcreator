"""SVG inspection helpers for embroidery geometry validators."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Iterator

from patchcreator.components.assets import _parse_transform
from patchcreator.geometry import AffineTransform


_LENGTH_RE = re.compile(
    r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-z%]*)\s*$"
)
_STYLE_SPLIT_RE = re.compile(r"\s*;\s*")

_GEOMETRY_TAGS = {
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "use",
}
_NON_RENDERED_CONTAINERS = {"defs", "clipPath", "mask", "marker", "metadata", "title", "desc", "symbol"}
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _is_construction(element: ET.Element) -> bool:
    return (
        element.get(f"{{{PATCHCREATOR_NS}}}construction-role") is not None
        or element.get("data-patchcreator-construction-role") is not None
    )


class SvgInspectionError(ValueError):
    pass


@dataclass(frozen=True)
class StrokeGeometry:
    element_id: str | None
    element_tag: str
    width_mm: float


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _style(element: ET.Element) -> dict[str, str]:
    raw = element.get("style", "")
    result: dict[str, str] = {}
    for declaration in _STYLE_SPLIT_RE.split(raw.strip()):
        if not declaration or ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        result[name.strip().lower()] = value.strip()
    return result


def _property(
    element: ET.Element,
    style: dict[str, str],
    name: str,
    inherited: str | None,
) -> str | None:
    if name in style:
        return style[name]
    if element.get(name) is not None:
        return element.get(name)
    return inherited


def _parse_css_length_mm(raw: str, *, user_unit_mm: float) -> float:
    match = _LENGTH_RE.match(raw)
    if not match:
        raise SvgInspectionError(f"unsupported SVG length {raw!r}")
    value = float(match.group(1))
    unit = match.group(2).lower()
    if value < 0:
        raise SvgInspectionError(f"SVG stroke width must not be negative: {raw!r}")
    if unit == "":
        return value * user_unit_mm
    conversions = {
        "mm": 1.0,
        "cm": 10.0,
        "in": 25.4,
        "px": 25.4 / 96.0,
        "pt": 25.4 / 72.0,
        "pc": 25.4 / 6.0,
        "q": 0.25,
    }
    try:
        return value * conversions[unit]
    except KeyError as exc:
        raise SvgInspectionError(
            f"unsupported SVG stroke-width unit {unit!r}; percentages cannot yet be checked physically"
        ) from exc


def _parse_root_length_mm(raw: str | None, *, name: str) -> float:
    if raw is None:
        raise SvgInspectionError(
            f"SVG has no physical {name}; add width/height with mm, cm, in or px units before embroidery checking"
        )
    match = _LENGTH_RE.match(raw)
    if not match:
        raise SvgInspectionError(f"unsupported SVG root {name} {raw!r}")
    value = float(match.group(1))
    unit = match.group(2).lower()
    if value <= 0:
        raise SvgInspectionError(f"SVG root {name} must be positive")
    # Unitless root dimensions are CSS pixels per SVG/CSS sizing rules.
    if unit in {"", "px"}:
        return value * 25.4 / 96.0
    conversions = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72.0, "pc": 25.4 / 6.0, "q": 0.25}
    try:
        return value * conversions[unit]
    except KeyError as exc:
        raise SvgInspectionError(f"unsupported SVG root {name} unit {unit!r}") from exc


def _root_user_unit_mm(root: ET.Element) -> float:
    raw_viewbox = root.get("viewBox")
    if raw_viewbox is None:
        # Without a viewBox one SVG user unit is one CSS px.
        return 25.4 / 96.0

    parts = raw_viewbox.replace(",", " ").split()
    if len(parts) != 4:
        raise SvgInspectionError(f"invalid SVG viewBox {raw_viewbox!r}")
    try:
        _, _, view_width, view_height = (float(part) for part in parts)
    except ValueError as exc:
        raise SvgInspectionError(f"invalid SVG viewBox {raw_viewbox!r}") from exc
    if view_width <= 0 or view_height <= 0:
        raise SvgInspectionError("SVG viewBox width/height must be positive")

    width_mm = _parse_root_length_mm(root.get("width"), name="width")
    height_mm = _parse_root_length_mm(root.get("height"), name="height")
    # Default preserveAspectRatio uses a uniform 'meet' scale. For explicit
    # preserveAspectRatio=none this remains a conservative minimum physical
    # stroke scale, which is what embroidery-risk detection wants.
    return min(width_mm / view_width, height_mm / view_height)


def _minimum_linear_scale(transform: AffineTransform) -> float:
    """Smallest singular value of the affine transform's 2x2 linear part."""
    a, b, c, d = transform.a, transform.b, transform.c, transform.d
    trace = a * a + b * b + c * c + d * d
    determinant = a * d - b * c
    discriminant = max(0.0, trace * trace - 4.0 * determinant * determinant)
    eigen_min = max(0.0, (trace - math.sqrt(discriminant)) / 2.0)
    return math.sqrt(eigen_min)


def _parse_opacity(raw: str | None, default: float = 1.0) -> float:
    if raw is None:
        return default
    text = raw.strip()
    try:
        if text.endswith("%"):
            return max(0.0, min(1.0, float(text[:-1]) / 100.0))
        return max(0.0, min(1.0, float(text)))
    except ValueError:
        return default


def iter_visible_strokes(root: ET.Element) -> Iterator[StrokeGeometry]:
    """Yield physically measured visible strokes from presentation attributes.

    This first validator intentionally supports presentation attributes and
    inline `style=` only. External/embedded CSS stylesheets are outside the v0.3
    minimum-stroke slice and can be normalized to presentation attributes first.
    """

    user_unit_mm = _root_user_unit_mm(root)

    def walk(
        element: ET.Element,
        transform: AffineTransform,
        inherited_stroke: str | None,
        inherited_width: str | None,
        inherited_visibility: str,
        inherited_stroke_opacity: float,
        ancestor_hidden: bool,
        non_rendered: bool,
    ) -> Iterator[StrokeGeometry]:
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

        stroke = _property(element, style, "stroke", inherited_stroke)
        stroke_width = _property(element, style, "stroke-width", inherited_width)
        stroke_opacity_raw = _property(element, style, "stroke-opacity", None)
        stroke_opacity = inherited_stroke_opacity * _parse_opacity(stroke_opacity_raw)
        opacity = _parse_opacity(_property(element, style, "opacity", None))

        if (
            not hidden
            and not now_non_rendered
            and visibility not in {"hidden", "collapse"}
            and opacity > 0.0
            and stroke_opacity > 0.0
            and tag in _GEOMETRY_TAGS
            and stroke is not None
            and stroke.strip().lower() not in {"none", "transparent"}
        ):
            raw_width = stroke_width or "1"
            base_mm = _parse_css_length_mm(raw_width, user_unit_mm=user_unit_mm)
            vector_effect = (_property(element, style, "vector-effect", None) or "").strip().lower()
            scale = 1.0 if vector_effect == "non-scaling-stroke" else _minimum_linear_scale(local_transform)
            yield StrokeGeometry(
                element_id=element.get("id"),
                element_tag=tag,
                width_mm=base_mm * scale,
            )

        for child in element:
            yield from walk(
                child,
                local_transform,
                stroke,
                stroke_width,
                visibility,
                stroke_opacity,
                hidden,
                now_non_rendered,
            )

    for child in root:
        yield from walk(
            child,
            AffineTransform.identity(),
            None,
            None,
            "visible",
            1.0,
            False,
            False,
        )


def parse_svg_text(
    text: str,
    *,
    source: str | Path | None = None,
) -> ET.Element:
    """Parse SVG text with the same safety/shape checks used for file input."""

    label = str(source) if source is not None else "SVG text"
    if "<!DOCTYPE" in text.upper():
        raise SvgInspectionError("SVG files with a DOCTYPE are not accepted for validation")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SvgInspectionError(f"cannot parse SVG {label}: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise SvgInspectionError(f"{label} is not an SVG document")
    return root


def load_svg(path: str | Path) -> tuple[Path, ET.Element]:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise SvgInspectionError(f"cannot read SVG {source}: {exc}") from exc
    return source, parse_svg_text(text, source=source)
