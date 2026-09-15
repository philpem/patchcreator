"""Policy-aware overlap diagnostics for visible filled SVG geometry."""

from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET

from shapely.geometry import GeometryCollection
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from patchcreator.components.assets import _parse_transform
from patchcreator.geometry import AffineTransform

from .geometry import (
    UnsupportedFilledGeometry,
    _primitive_geometry,
    _root_transform_mm,
    _shapely_transform,
)
from .model import Finding
from .svg import (
    SvgInspectionError,
    _NON_RENDERED_CONTAINERS,
    _local_name,
    _parse_opacity,
    _property,
    _style,
)

_POLICY_ATTR = "data-patchcreator-overlap-policy"
_POLICIES = {"allow", "warn", "avoid", "knockout", "background"}
_EPSILON_AREA = 1e-9


@dataclass(frozen=True)
class _PaintFragment:
    owner_id: str | None
    policy: str
    element_tag: str
    geometry: BaseGeometry
    paint_index: int


@dataclass(frozen=True)
class _PaintedOwner:
    owner_id: str | None
    policy: str
    element_tag: str
    geometry: BaseGeometry
    paint_index: int


def _policy(raw: str | None, *, element_id: str | None) -> str:
    if raw is None:
        return "warn"
    value = raw.strip().lower()
    if value not in _POLICIES:
        where = f" on {element_id!r}" if element_id else ""
        raise SvgInspectionError(
            f"invalid PatchCreator overlap policy {raw!r}{where}; "
            f"expected one of {', '.join(sorted(_POLICIES))}"
        )
    return value


def _iter_painted_fragments(root: ET.Element):
    """Yield visible fill fragments with their nearest logical overlap owner."""
    root_transform = _root_transform_mm(root)
    paint_index = 0

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
        owner_id: str | None,
        owner_policy: str | None,
    ):
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
                    effective_owner = current_owner or element_id
                    effective_policy = current_policy or _policy(
                        element.get(_POLICY_ATTR), element_id=element_id
                    )
                    yield _PaintFragment(
                        owner_id=effective_owner,
                        policy=effective_policy,
                        element_tag=tag,
                        geometry=geometry,
                        paint_index=paint_index,
                    )
                    paint_index += 1

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
                current_owner,
                current_policy,
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
            None,
            None,
        )


def _painted_owners(root: ET.Element) -> tuple[_PaintedOwner, ...]:
    fragments = tuple(_iter_painted_fragments(root))
    groups: dict[tuple[str, object], list[_PaintFragment]] = {}
    order: list[tuple[str, object]] = []
    anonymous_counter = 0

    for fragment in fragments:
        if fragment.owner_id is None:
            key: tuple[str, object] = ("anonymous", anonymous_counter)
            anonymous_counter += 1
        else:
            key = ("id", fragment.owner_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(fragment)

    owners: list[_PaintedOwner] = []
    for key in order:
        items = groups[key]
        policies = {item.policy for item in items}
        if len(policies) != 1:
            owner = items[0].owner_id
            raise SvgInspectionError(
                f"SVG overlap owner {owner!r} contains conflicting policies: "
                + ", ".join(sorted(policies))
            )
        geometry = unary_union([item.geometry for item in items])
        if geometry.is_empty:
            geometry = GeometryCollection()
        owners.append(
            _PaintedOwner(
                owner_id=items[0].owner_id,
                policy=items[0].policy,
                element_tag=items[0].element_tag,
                geometry=geometry,
                paint_index=min(item.paint_index for item in items),
            )
        )
    owners.sort(key=lambda item: item.paint_index)
    return tuple(owners)


def _finding_for_overlap(
    lower: _PaintedOwner,
    upper: _PaintedOwner,
    intersection: BaseGeometry,
) -> Finding | None:
    policies = {lower.policy, upper.policy}
    if "background" in policies:
        # Background coverage is intentional by definition and would otherwise
        # generate one noisy finding for almost every foreground element.
        return None

    if "avoid" in policies:
        code = "overlap-avoid-violation"
        severity = "error"
        message = (
            "filled areas overlap even though at least one element declares "
            "overlap_policy=avoid"
        )
    elif "warn" in policies:
        code = "overlap-thread-buildup"
        severity = "warning"
        message = (
            "filled areas overlap; unless digitisation removes lower stitches, "
            "this may create excess thread buildup"
        )
    elif "knockout" in policies:
        code = "overlap-knockout-pending"
        severity = "info"
        message = (
            "filled areas overlap under a knockout policy; compatibility export "
            "must remove covered lower geometry"
        )
    else:
        # Both sides explicitly allow ordinary overlap.
        return None

    representative = intersection.representative_point()
    return Finding(
        code=code,
        severity=severity,
        message=message,
        element_id=lower.owner_id,
        element_tag=lower.element_tag,
        related_element_id=upper.owner_id,
        related_element_tag=upper.element_tag,
        element_policy=lower.policy,
        related_element_policy=upper.policy,
        measured_mm2=float(intersection.area),
        bounds_mm=tuple(float(value) for value in intersection.bounds),
        points_mm=((float(representative.x), float(representative.y)),),
    )


def validate_overlaps(root: ET.Element) -> list[Finding]:
    """Report policy-relevant positive-area overlaps between logical objects."""
    owners = _painted_owners(root)
    findings: list[Finding] = []

    for lower_index, lower in enumerate(owners):
        if lower.geometry.is_empty:
            continue
        for upper in owners[lower_index + 1 :]:
            if upper.geometry.is_empty:
                continue
            if "background" in {lower.policy, upper.policy}:
                continue
            if not lower.geometry.envelope.intersects(upper.geometry.envelope):
                continue
            intersection = lower.geometry.intersection(upper.geometry)
            if intersection.is_empty or intersection.area <= _EPSILON_AREA:
                continue
            finding = _finding_for_overlap(lower, upper, intersection)
            if finding is not None:
                findings.append(finding)

    findings.sort(
        key=lambda finding: (
            {"error": 0, "warning": 1, "info": 2}[finding.severity],
            -(finding.measured_mm2 or 0.0),
            finding.element_id or "",
            finding.related_element_id or "",
        )
    )
    return findings
