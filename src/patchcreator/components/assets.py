"""Reusable plain-SVG asset loading, anchors and semantic colour roles."""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from patchcreator.components.registry import ComponentResult
from patchcreator.geometry import AffineTransform, Bounds, parse_length_mm

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"

_TRANSFORM_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
_URL_REF_RE = re.compile(r"url\(\s*#([^)\s]+)\s*\)")
_NUMBER_SPLIT_RE = re.compile(r"[\s,]+")

# Presentation properties on the source root are inherited by its drawable
# descendants.  Once the root <svg> is replaced by an ordinary group, carry
# these properties onto that group so importing an asset does not silently
# change its appearance.  Structural viewport attributes (width, viewBox,
# preserveAspectRatio, ... ) intentionally stay out of this set.
_ROOT_PRESENTATION_ATTRIBUTES = frozenset(
    {
        "class",
        "color",
        "color-interpolation",
        "color-interpolation-filters",
        "color-rendering",
        "cursor",
        "display",
        "fill",
        "fill-opacity",
        "fill-rule",
        "filter",
        "clip-path",
        "clip-rule",
        "image-rendering",
        "isolation",
        "font-family",
        "font-size",
        "font-size-adjust",
        "font-stretch",
        "font-style",
        "font-variant",
        "font-weight",
        "letter-spacing",
        "word-spacing",
        "mix-blend-mode",
        "mask",
        "marker-end",
        "marker-mid",
        "marker-start",
        "opacity",
        "overflow",
        "paint-order",
        "shape-rendering",
        "stop-color",
        "stop-opacity",
        "stroke",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-opacity",
        "stroke-width",
        "text-anchor",
        "text-decoration",
        "text-rendering",
        "vector-effect",
        "visibility",
        "style",
    }
)


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _resolve_asset_path(source: Any, design: Any) -> Path:
    if source is None:
        raise ValueError("asset component requires source")
    path = Path(str(source)).expanduser()
    if not path.is_absolute():
        base = getattr(design, "source_dir", None) or Path.cwd()
        path = Path(base) / path
    return path.resolve()


def _parse_viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    raw = root.get("viewBox")
    if not raw:
        raise ValueError("reusable SVG asset requires a viewBox; run patchcreator normalize first")
    parts = [part for part in _NUMBER_SPLIT_RE.split(raw.strip()) if part]
    if len(parts) != 4:
        raise ValueError(f"invalid SVG asset viewBox {raw!r}")
    try:
        min_x, min_y, width, height = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"invalid SVG asset viewBox {raw!r}") from exc
    if width <= 0 or height <= 0:
        raise ValueError("SVG asset viewBox width/height must be positive")
    return min_x, min_y, width, height


def _physical_root_size(root: ET.Element) -> tuple[float | None, float | None]:
    def parse(raw: str | None) -> float | None:
        if raw is None:
            return None
        text = raw.strip().lower()
        conversions = {"mm": 1.0, "cm": 10.0, "in": 25.4, "px": 25.4 / 96.0}
        for suffix, scale in conversions.items():
            if text.endswith(suffix):
                try:
                    return float(text[: -len(suffix)].strip()) * scale
                except ValueError:
                    return None
        return None

    return parse(root.get("width")), parse(root.get("height"))


def _asset_dimensions(config: Mapping[str, Any], root: ET.Element, viewbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    _, _, vb_width, vb_height = viewbox
    width = parse_length_mm(config["width"]) if config.get("width") is not None else None
    height = parse_length_mm(config["height"]) if config.get("height") is not None else None
    preserve = bool(config.get("preserve_aspect", True))

    if width is None and height is None:
        width, height = _physical_root_size(root)
        if width is None or height is None:
            raise ValueError(
                "asset requires width or height in physical units when the source SVG has no physical mm/cm/in/px size"
            )

    if width is not None and width <= 0:
        raise ValueError("asset width must be positive")
    if height is not None and height <= 0:
        raise ValueError("asset height must be positive")

    if width is None:
        assert height is not None
        scale = height / vb_height
        width = vb_width * scale
        return width, height, scale, scale
    if height is None:
        scale = width / vb_width
        height = vb_height * scale
        return width, height, scale, scale

    scale_x = width / vb_width
    scale_y = height / vb_height
    if preserve:
        scale = min(scale_x, scale_y)
        actual_width = vb_width * scale
        actual_height = vb_height * scale
        return actual_width, actual_height, scale, scale
    return width, height, scale_x, scale_y


def _numbers(raw: str) -> list[float]:
    try:
        return [float(part) for part in _NUMBER_SPLIT_RE.split(raw.strip()) if part]
    except ValueError as exc:
        raise ValueError(f"invalid SVG transform {raw!r}") from exc


def _parse_transform(raw: str | None) -> AffineTransform:
    if not raw:
        return AffineTransform.identity()
    position = 0
    result = AffineTransform.identity()
    for match in _TRANSFORM_RE.finditer(raw):
        if raw[position : match.start()].strip(" ,\t\r\n"):
            raise ValueError(f"unsupported SVG transform syntax {raw!r}")
        name = match.group(1).lower()
        values = _numbers(match.group(2))
        if name == "matrix" and len(values) == 6:
            transform = AffineTransform(*values)
        elif name == "translate" and len(values) in {1, 2}:
            transform = AffineTransform.translation(values[0], values[1] if len(values) == 2 else 0.0)
        elif name == "scale" and len(values) in {1, 2}:
            transform = AffineTransform.scale(values[0], values[1] if len(values) == 2 else None)
        elif name == "rotate" and len(values) in {1, 3}:
            centre = (values[1], values[2]) if len(values) == 3 else None
            transform = AffineTransform.rotation(values[0], centre=centre)
        else:
            raise ValueError(
                f"unsupported SVG asset transform {name}({match.group(2)}); normalize skew/complex transforms first"
            )
        result = result @ transform
        position = match.end()
    if raw[position:].strip(" ,\t\r\n"):
        raise ValueError(f"unsupported SVG transform syntax {raw!r}")
    return result


def _anchor_local_point(element: ET.Element) -> tuple[float, float]:
    tag = _local_name(element.tag)
    def number(name: str, default: float = 0.0) -> float:
        raw = element.get(name)
        return default if raw is None else float(raw)

    if tag in {"circle", "ellipse"}:
        return number("cx"), number("cy")
    if tag == "rect":
        return number("x") + number("width") / 2.0, number("y") + number("height") / 2.0
    if tag == "line":
        return (number("x1") + number("x2")) / 2.0, (number("y1") + number("y2")) / 2.0
    if tag in {"text", "image", "use"}:
        return number("x"), number("y")
    # A group/path marker uses its transformed local origin. This makes an
    # Inkscape group translated to the desired point a convenient zero-size marker.
    return 0.0, 0.0


def _collect_anchors(root: ET.Element, asset_transform: AffineTransform) -> dict[str, tuple[float, float]]:
    anchors: dict[str, tuple[float, float]] = {}

    def visit(element: ET.Element, parent: AffineTransform) -> None:
        current = parent @ _parse_transform(element.get("transform"))
        name = element.get("data-patchcreator-anchor")
        if name:
            if name in anchors:
                raise ValueError(f"duplicate SVG asset anchor {name!r}")
            anchors[name] = asset_transform.apply(current.apply(_anchor_local_point(element)))
        for child in element:
            visit(child, current)

    for child in root:
        visit(child, AffineTransform.identity())
    return anchors


def _rewrite_ids(root: ET.Element, prefix: str) -> None:
    id_map: dict[str, str] = {}
    for element in root.iter():
        old = element.get("id")
        if not old:
            continue
        if old in id_map:
            raise ValueError(f"duplicate id {old!r} in reusable SVG asset")
        new = f"{prefix}-{old}"
        id_map[old] = new
        element.set("id", new)

    def rewrite(value: str) -> str:
        if value.startswith("#") and value[1:] in id_map:
            value = "#" + id_map[value[1:]]
        return _URL_REF_RE.sub(lambda match: f"url(#{id_map.get(match.group(1), match.group(1))})", value)

    for element in root.iter():
        for key, value in list(element.attrib.items()):
            element.set(key, rewrite(value))


def _validate_self_contained(root: ET.Element) -> None:
    for element in root.iter():
        if _local_name(element.tag) == "script":
            raise ValueError("reusable SVG assets may not contain script elements")
        for key, value in element.attrib.items():
            if _local_name(key) != "href":
                continue
            text = value.strip()
            if text and not text.startswith("#"):
                raise ValueError(
                    f"reusable SVG asset contains external reference {text!r}; embed or normalize it first"
                )


def _role_colour(design: Any, value: Any) -> str:
    name = str(value)
    resolved = design.palette.get(name, name)
    if not isinstance(resolved, str):
        raise ValueError(f"asset colour role {name!r} did not resolve to a colour string")
    return resolved


def _style_properties(element: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for declaration in element.get("style", "").split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        result[name.strip().lower()] = value.strip()
    return result


def _set_style_property(element: ET.Element, name: str, value: str) -> None:
    """Set one inline style declaration while retaining unrelated declarations."""

    declarations = [part.strip() for part in element.get("style", "").split(";") if part.strip()]
    output: list[str] = []
    replaced = False
    for declaration in declarations:
        if ":" not in declaration:
            output.append(declaration)
            continue
        raw_name, raw_value = declaration.split(":", 1)
        if raw_name.strip().lower() == name.lower():
            output.append(f"{raw_name.strip()}:{value}")
            replaced = True
        else:
            output.append(f"{raw_name.strip()}:{raw_value.strip()}")
    if not replaced:
        output.append(f"{name}:{value}")
    element.set("style", ";".join(output))


def _apply_colour_roles(root: ET.Element, roles: Mapping[str, Any], design: Any) -> None:
    for element in root.iter():
        generic = element.get("data-patchcreator-colour-role")
        fill_role = element.get("data-patchcreator-fill-role")
        stroke_role = element.get("data-patchcreator-stroke-role")
        style = _style_properties(element)

        if generic and generic in roles:
            colour = _role_colour(design, roles[generic])
            changed = False
            if style.get("fill", element.get("fill")) not in {None, "none"}:
                element.set("fill", colour)
                _set_style_property(element, "fill", colour)
                changed = True
            if style.get("stroke", element.get("stroke")) not in {None, "none"}:
                element.set("stroke", colour)
                _set_style_property(element, "stroke", colour)
                changed = True
            if not changed:
                element.set("fill", colour)
                _set_style_property(element, "fill", colour)
        if fill_role and fill_role in roles:
            colour = _role_colour(design, roles[fill_role])
            element.set("fill", colour)
            _set_style_property(element, "fill", colour)
        if stroke_role and stroke_role in roles:
            colour = _role_colour(design, roles[stroke_role])
            element.set("stroke", colour)
            _set_style_property(element, "stroke", colour)


def _hide_anchor_markers(root: ET.Element) -> None:
    for element in root.iter():
        if element.get("data-patchcreator-anchor"):
            style = element.get("style", "")
            if style and not style.rstrip().endswith(";"):
                style += ";"
            element.set("style", style + "display:none")
            element.set(_q(PATCHCREATOR_NS, "construction-role"), "asset-anchor-source")


def _append_anchor_guides(
    element: Any,
    context: Any,
    anchors: Mapping[str, tuple[float, float]],
) -> None:
    """Render semantic asset anchors as authoring-only construction markers."""

    if not context.design.settings.construction_guides or not anchors:
        return

    guide_group = ET.SubElement(
        context.target_group,
        _q(SVG_NS, "g"),
        {
            "id": f"{element.id}-anchor-guides",
            _q(PATCHCREATOR_NS, "construction-role"): "asset-anchors",
            "fill": "none",
            "stroke": "#00a6ff",
            "stroke-width": "0.2",
            "stroke-opacity": "0.75",
            "vector-effect": "non-scaling-stroke",
        },
    )
    for index, (name, (x, y)) in enumerate(sorted(anchors.items())):
        marker = ET.SubElement(
            guide_group,
            _q(SVG_NS, "g"),
            {
                "id": f"{element.id}-anchor-guide-{index:03d}",
                _q(PATCHCREATOR_NS, "construction-role"): "asset-anchor",
                _q(PATCHCREATOR_NS, "anchor-name"): name,
            },
        )
        ET.SubElement(
            marker,
            _q(SVG_NS, "circle"),
            {"cx": _fmt(x), "cy": _fmt(y), "r": "0.8"},
        )
        ET.SubElement(
            marker,
            _q(SVG_NS, "line"),
            {
                "x1": _fmt(x - 1.2),
                "y1": _fmt(y),
                "x2": _fmt(x + 1.2),
                "y2": _fmt(y),
            },
        )
        ET.SubElement(
            marker,
            _q(SVG_NS, "line"),
            {
                "x1": _fmt(x),
                "y1": _fmt(y - 1.2),
                "x2": _fmt(x),
                "y2": _fmt(y + 1.2),
            },
        )


def render_asset(element: Any, context: Any) -> ComponentResult:
    """Import one self-contained plain SVG as editable child geometry."""

    config = element.component_config()
    source = _resolve_asset_path(config.get("source", config.get("path")), context.design)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read SVG asset {source}: {exc}") from exc
    if "<!DOCTYPE" in text.upper():
        raise ValueError("reusable SVG assets may not contain a DOCTYPE")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"failed to parse SVG asset {source}: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise ValueError(f"reusable asset {source} is not an SVG document")

    _validate_self_contained(root)
    viewbox = _parse_viewbox(root)
    width, height, scale_x, scale_y = _asset_dimensions(config, root, viewbox)
    min_x, min_y, _, _ = viewbox
    asset_transform = (
        AffineTransform.translation(-width / 2.0, -height / 2.0)
        @ AffineTransform.scale(scale_x, scale_y)
        @ AffineTransform.translation(-min_x, -min_y)
    )
    # The source root is itself a transform/presentation context.  It is lost
    # when the source <svg> viewport is replaced by an ordinary group, so fold
    # its transform into both the wrapper and semantic anchor coordinates.
    root_style = _style_properties(root)
    # CSS declarations take precedence over presentation attributes.  Parse a
    # root style transform as well as transform="..." so it is represented in
    # anchors and the imported wrapper rather than silently discarded.
    root_transform = _parse_transform(root_style.get("transform", root.get("transform")))
    composed_asset_transform = asset_transform @ root_transform
    anchors = _collect_anchors(root, composed_asset_transform)

    imported = copy.deepcopy(root)
    _rewrite_ids(imported, f"asset-{element.id}")
    _hide_anchor_markers(imported)
    raw_roles = config.get("roles", config.get("colours", {}))
    if raw_roles is None:
        raw_roles = {}
    if not isinstance(raw_roles, Mapping):
        raise ValueError("asset roles must be a mapping from semantic role to palette colour")
    _apply_colour_roles(imported, raw_roles, context.design)

    wrapper = ET.SubElement(
        context.target_group,
        _q(SVG_NS, "g"),
        {
            "id": f"{element.id}-asset",
            "transform": composed_asset_transform.to_svg(),
            _q(PATCHCREATOR_NS, "asset-source"): str(source),
        },
    )
    # Use the transformed/role-resolved copy: URL references now point at the
    # instance-prefixed IDs and root-level semantic roles have been applied.
    for key, value in imported.attrib.items():
        if key in _ROOT_PRESENTATION_ATTRIBUTES:
            if key == "style":
                # ``transform`` is not inherited and has already been folded
                # into composed_asset_transform.  Copying it in the wrapper's
                # style would apply the root transform a second time.
                declarations = [
                    part.strip()
                    for part in value.split(";")
                    if part.strip()
                    and (
                        ":" not in part
                        or part.split(":", 1)[0].strip().lower() != "transform"
                    )
                ]
                value = ";".join(declarations)
            wrapper.set(key, value)
    # Preserve the source SVG's drawable/defs hierarchy without nesting another
    # outer <svg> viewport. IDs/references have already been made instance-safe.
    for child in imported:
        wrapper.append(child)

    context.target_group.set(_q(PATCHCREATOR_NS, "asset-width-mm"), _fmt(width))
    context.target_group.set(_q(PATCHCREATOR_NS, "asset-height-mm"), _fmt(height))
    if anchors:
        context.target_group.set(
            _q(PATCHCREATOR_NS, "asset-anchors"),
            " ".join(sorted(anchors)),
        )
    if raw_roles:
        context.target_group.set(
            _q(PATCHCREATOR_NS, "asset-colour-roles"),
            " ".join(sorted(str(role) for role in raw_roles)),
        )

    _append_anchor_guides(element, context, anchors)

    return ComponentResult(
        bounds=Bounds(-width / 2.0, -height / 2.0, width / 2.0, height / 2.0),
        anchors=anchors,
    )
