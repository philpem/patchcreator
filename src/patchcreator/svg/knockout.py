"""Physical boolean knockout for compatibility SVG export.

The pass operates on ordinary visible filled SVG primitives after `<use>`
expansion. Geometry is measured in document millimetres, boolean differences
are computed there, and each changed fragment is transformed back into its
original local coordinate frame before being replaced by an editable SVG path.
"""

from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET

from shapely.geometry import GeometryCollection
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from patchcreator.components.assets import _parse_transform
from patchcreator.geometry import AffineTransform
from patchcreator.geometry.boolean import geometry_to_svg_path
from patchcreator.validation.geometry import (
    UnsupportedFilledGeometry,
    _primitive_geometry,
    _root_transform_mm,
    _shapely_transform,
)
from patchcreator.validation.svg import (
    _NON_RENDERED_CONTAINERS,
    _local_name,
    _parse_opacity,
    _property,
    _style,
)

_POLICY_ATTR = "data-patchcreator-overlap-policy"
_POLICIES = {"allow", "warn", "avoid", "knockout", "background"}
_EPSILON_AREA = 1e-9
_SUPPORTED_AREA_TAGS = {"path", "rect", "circle", "ellipse", "polygon", "polyline"}
_UNSUPPORTED_PAINT_TAGS = {"text", "image", "foreignObject", "use"}
_SHAPE_ATTRIBUTES = {
    "d",
    "x",
    "y",
    "width",
    "height",
    "rx",
    "ry",
    "cx",
    "cy",
    "r",
    "points",
}


@dataclass
class _Fragment:
    element: ET.Element
    parent: ET.Element
    owner_id: str | None
    policy: str
    geometry_mm: BaseGeometry
    local_to_mm: AffineTransform
    paint_index: int
    has_visible_stroke: bool


@dataclass(frozen=True)
class _Owner:
    owner_id: str | None
    policy: str
    geometry_mm: BaseGeometry
    paint_index: int
    fragments: tuple[_Fragment, ...]


@dataclass(frozen=True)
class KnockoutResult:
    changed_fragments: int
    removed_fragments: int
    warnings: tuple[str, ...] = ()


def _policy(raw: str | None, *, element_id: str | None) -> str:
    if raw is None:
        return "warn"
    value = raw.strip().lower()
    if value not in _POLICIES:
        where = f" on {element_id!r}" if element_id else ""
        raise ValueError(
            f"invalid PatchCreator overlap policy {raw!r}{where}; "
            f"expected one of {', '.join(sorted(_POLICIES))}"
        )
    return value


def _visible_stroke(
    element: ET.Element,
    style: dict[str, str],
    inherited_stroke: str | None,
    inherited_width: str | None,
    inherited_stroke_opacity: float,
) -> tuple[str | None, str | None, float, bool]:
    stroke = _property(element, style, "stroke", inherited_stroke)
    width = _property(element, style, "stroke-width", inherited_width)
    opacity = inherited_stroke_opacity * _parse_opacity(
        _property(element, style, "stroke-opacity", None)
    )
    visible = (
        opacity > 0.0
        and stroke is not None
        and stroke.strip().lower() not in {"none", "transparent"}
        and (width is None or width.strip() not in {"0", "0.0", "0px", "0mm"})
    )
    return stroke, width, opacity, visible


def _collect_fragments(root: ET.Element) -> tuple[tuple[_Fragment, ...], tuple[str, ...]]:
    root_transform = _root_transform_mm(root)
    fragments: list[_Fragment] = []
    unsupported_knockout: set[str] = set()
    unsupported_other: set[str] = set()
    paint_index = 0

    def walk(
        parent: ET.Element,
        element: ET.Element,
        transform: AffineTransform,
        inherited_fill: str,
        inherited_fill_rule: str,
        inherited_visibility: str,
        inherited_fill_opacity: float,
        inherited_stroke: str | None,
        inherited_stroke_width: str | None,
        inherited_stroke_opacity: float,
        ancestor_opacity: float,
        ancestor_hidden: bool,
        non_rendered: bool,
        owner_id: str | None,
        owner_policy: str | None,
    ) -> None:
        nonlocal paint_index
        tag = _local_name(element.tag)
        style = _style(element)
        display = _property(element, style, "display", None)
        hidden = ancestor_hidden or (display is not None and display.strip().lower() == "none")
        visibility = (
            _property(element, style, "visibility", inherited_visibility) or "visible"
        ).strip().lower()
        now_non_rendered = non_rendered or tag in _NON_RENDERED_CONTAINERS
        local_transform = transform @ _parse_transform(element.get("transform"))

        current_owner = owner_id
        current_policy = owner_policy
        element_id = element.get("id")
        raw_policy = element.get(_POLICY_ATTR)
        if element_id == "__canvas_background__":
            current_owner = element_id
            current_policy = "background"
        elif raw_policy is not None:
            current_owner = element_id or current_owner
            current_policy = _policy(raw_policy, element_id=element_id)

        fill = (_property(element, style, "fill", inherited_fill) or "black").strip()
        fill_rule = (
            _property(element, style, "fill-rule", inherited_fill_rule) or "nonzero"
        ).strip().lower()
        fill_opacity = inherited_fill_opacity * _parse_opacity(
            _property(element, style, "fill-opacity", None)
        )
        opacity = ancestor_opacity * _parse_opacity(_property(element, style, "opacity", None))
        stroke, stroke_width, stroke_opacity, has_visible_stroke = _visible_stroke(
            element,
            style,
            inherited_stroke,
            inherited_stroke_width,
            inherited_stroke_opacity,
        )

        visible = (
            not hidden
            and not now_non_rendered
            and visibility not in {"hidden", "collapse"}
            and opacity > 0.0
        )
        effective_owner = current_owner or element_id
        effective_policy = current_policy or _policy(raw_policy, element_id=element_id)

        if visible and tag in _UNSUPPORTED_PAINT_TAGS:
            name = effective_owner or element_id or f"<{tag}>"
            if effective_policy == "knockout":
                unsupported_knockout.add(name)
            else:
                unsupported_other.add(name)

        if (
            visible
            and fill_opacity > 0.0
            and fill.lower() not in {"none", "transparent"}
            and tag in _SUPPORTED_AREA_TAGS
        ):
            try:
                geometry = _primitive_geometry(element, fill_rule=fill_rule)
            except UnsupportedFilledGeometry as exc:
                name = effective_owner or element_id or f"<{tag}>"
                if effective_policy == "knockout":
                    raise ValueError(
                        f"cannot apply knockout to {name!r}: unsupported filled geometry: {exc}"
                    ) from exc
                unsupported_other.add(name)
                geometry = None
            if geometry is not None and not geometry.is_empty:
                local_to_mm = root_transform @ local_transform
                geometry = _shapely_transform(geometry, local_to_mm)
                if not geometry.is_empty:
                    fragments.append(
                        _Fragment(
                            element=element,
                            parent=parent,
                            owner_id=effective_owner,
                            policy=effective_policy,
                            geometry_mm=geometry,
                            local_to_mm=local_to_mm,
                            paint_index=paint_index,
                            has_visible_stroke=has_visible_stroke,
                        )
                    )
                    paint_index += 1

        for child in element:
            walk(
                element,
                child,
                local_transform,
                fill,
                fill_rule,
                visibility,
                fill_opacity,
                stroke,
                stroke_width,
                stroke_opacity,
                opacity,
                hidden,
                now_non_rendered,
                current_owner,
                current_policy,
            )

    for child in root:
        walk(
            root,
            child,
            AffineTransform.identity(),
            "black",
            "nonzero",
            "visible",
            1.0,
            None,
            None,
            1.0,
            1.0,
            False,
            False,
            None,
            None,
        )

    if unsupported_knockout:
        names = ", ".join(sorted(unsupported_knockout))
        raise ValueError(
            "knockout owners contain visible geometry that cannot yet be boolean-expanded: " + names
        )
    return tuple(fragments), tuple(sorted(unsupported_other))


def _owners(fragments: tuple[_Fragment, ...]) -> tuple[_Owner, ...]:
    groups: dict[tuple[str, object], list[_Fragment]] = {}
    order: list[tuple[str, object]] = []
    anonymous = 0
    for fragment in fragments:
        if fragment.owner_id is None:
            key: tuple[str, object] = ("anonymous", anonymous)
            anonymous += 1
        else:
            key = ("id", fragment.owner_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(fragment)

    owners: list[_Owner] = []
    for key in order:
        items = groups[key]
        policies = {item.policy for item in items}
        if len(policies) != 1:
            raise ValueError(
                f"SVG knockout owner {items[0].owner_id!r} contains conflicting policies: "
                + ", ".join(sorted(policies))
            )
        geometry = unary_union([item.geometry_mm for item in items])
        if geometry.is_empty:
            geometry = GeometryCollection()
        owners.append(
            _Owner(
                owner_id=items[0].owner_id,
                policy=items[0].policy,
                geometry_mm=geometry,
                paint_index=min(item.paint_index for item in items),
                fragments=tuple(items),
            )
        )
    owners.sort(key=lambda item: item.paint_index)
    return tuple(owners)


def _pair_uses_knockout(lower: _Owner, upper: _Owner) -> bool:
    policies = {lower.policy, upper.policy}
    if "background" in policies or "avoid" in policies or "warn" in policies:
        return False
    return "knockout" in policies


def _remove_shape_attributes(element: ET.Element) -> None:
    for name in _SHAPE_ATTRIBUTES:
        element.attrib.pop(name, None)
    style = _style(element)
    if "fill-rule" in style:
        del style["fill-rule"]
        element.set("style", ";".join(f"{name}:{value}" for name, value in style.items()))


def _replace_fragment_geometry(fragment: _Fragment, geometry_mm: BaseGeometry) -> bool:
    """Replace one primitive with the knocked-out geometry; return removed flag."""
    if fragment.has_visible_stroke:
        name = fragment.owner_id or fragment.element.get("id") or _local_name(fragment.element.tag)
        raise ValueError(
            f"cannot physically knockout stroked filled geometry in {name!r} yet; "
            "convert the stroke to a filled outline or remove it before export"
        )

    if geometry_mm.is_empty or geometry_mm.area <= _EPSILON_AREA:
        fragment.parent.remove(fragment.element)
        return True

    local_geometry = _shapely_transform(geometry_mm, fragment.local_to_mm.inverse())
    path_data = geometry_to_svg_path(local_geometry)
    _remove_shape_attributes(fragment.element)
    fragment.element.tag = f"{{http://www.w3.org/2000/svg}}path"
    fragment.element.set("d", path_data)
    fragment.element.set("fill-rule", "evenodd")
    return False


def apply_knockout(root: ET.Element) -> KnockoutResult:
    """Physically subtract knockout-qualified later fills from lower fragments."""
    fragments, unsupported_other = _collect_fragments(root)
    owners = _owners(fragments)
    changed = 0
    removed = 0

    for lower_index, lower in enumerate(owners):
        if lower.geometry_mm.is_empty:
            continue
        occluders: list[BaseGeometry] = []
        for upper in owners[lower_index + 1 :]:
            if upper.geometry_mm.is_empty or not _pair_uses_knockout(lower, upper):
                continue
            if not lower.geometry_mm.envelope.intersects(upper.geometry_mm.envelope):
                continue
            intersection = lower.geometry_mm.intersection(upper.geometry_mm)
            if intersection.is_empty or intersection.area <= _EPSILON_AREA:
                continue
            occluders.append(upper.geometry_mm)

        if not occluders:
            continue
        occluder = unary_union(occluders)
        for fragment in lower.fragments:
            if not fragment.geometry_mm.envelope.intersects(occluder.envelope):
                continue
            intersection = fragment.geometry_mm.intersection(occluder)
            if intersection.is_empty or intersection.area <= _EPSILON_AREA:
                continue
            difference = fragment.geometry_mm.difference(occluder)
            was_removed = _replace_fragment_geometry(fragment, difference)
            changed += 1
            removed += int(was_removed)

    warnings: list[str] = []
    if unsupported_other and any(owner.policy == "knockout" for owner in owners):
        warnings.append(
            "knockout left unsupported non-knockout painted content unchanged: "
            + ", ".join(unsupported_other)
        )
    return KnockoutResult(
        changed_fragments=changed,
        removed_fragments=removed,
        warnings=tuple(warnings),
    )
