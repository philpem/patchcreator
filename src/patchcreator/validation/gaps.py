"""Minimum-clearance checks between visible filled SVG geometry."""

from __future__ import annotations

import itertools
import math
import xml.etree.ElementTree as ET

from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from .geometry import FilledGeometry, iter_visible_fills, polygon_components
from .model import Finding

_EPSILON = 1e-9


def _bounds_union(
    first: BaseGeometry,
    second: BaseGeometry,
) -> tuple[float, float, float, float]:
    first_bounds = first.bounds
    second_bounds = second.bounds
    return (
        min(first_bounds[0], second_bounds[0]),
        min(first_bounds[1], second_bounds[1]),
        max(first_bounds[2], second_bounds[2]),
        max(first_bounds[3], second_bounds[3]),
    )


def _gap_finding(
    first: FilledGeometry,
    second: FilledGeometry,
    *,
    first_geometry: BaseGeometry,
    second_geometry: BaseGeometry,
    minimum_mm: float,
    same_element_components: bool = False,
) -> Finding | None:
    distance = first_geometry.distance(second_geometry)
    # Touching/intersecting geometry belongs to the overlap validator. A gap is
    # intentionally a positive clearance.
    if distance <= _EPSILON or distance + _EPSILON >= minimum_mm:
        return None

    first_point, second_point = nearest_points(first_geometry, second_geometry)
    points = (
        (float(first_point.x), float(first_point.y)),
        (float(second_point.x), float(second_point.y)),
    )

    if same_element_components:
        message = (
            "disconnected filled parts of this element are separated by less "
            "than the selected minimum gap"
        )
        related_id = None
        related_tag = None
    else:
        message = "visible filled geometry is too close to another element"
        related_id = second.element_id
        related_tag = second.element_tag

    return Finding(
        code="gap-too-narrow",
        severity="warning",
        message=message,
        element_id=first.element_id,
        element_tag=first.element_tag,
        related_element_id=related_id,
        related_element_tag=related_tag,
        measured_mm=float(distance),
        threshold_mm=minimum_mm,
        bounds_mm=_bounds_union(first_geometry, second_geometry),
        points_mm=points,
    )


def validate_narrow_gaps(
    root: ET.Element,
    *,
    minimum_mm: float,
) -> list[Finding]:
    """Report positive edge-to-edge clearances smaller than ``minimum_mm``.

    Geometry is measured in physical millimetres using the same analysis-only
    fill extraction as the small-feature validator. Overlap/touching (distance
    zero) is deliberately left to the overlap validator so the two checks do
    not produce duplicate findings.

    In addition to gaps between SVG elements, disconnected polygon components
    belonging to one compound element are checked against each other. This can
    catch tiny channels between islands represented by a single SVG path.
    """
    if minimum_mm < 0:
        raise ValueError("minimum gap must not be negative")
    if minimum_mm <= _EPSILON:
        return []

    filled = tuple(iter_visible_fills(root))
    findings: list[Finding] = []

    # First check disconnected components inside one element. The outer
    # cross-element pass treats each FilledGeometry as one object and therefore
    # cannot see positive distances between its own components.
    for item in filled:
        components = polygon_components(item.geometry)
        for first_geometry, second_geometry in itertools.combinations(components, 2):
            finding = _gap_finding(
                item,
                item,
                first_geometry=first_geometry,
                second_geometry=second_geometry,
                minimum_mm=minimum_mm,
                same_element_components=True,
            )
            if finding is not None:
                findings.append(finding)

    # Then check distinct visible filled SVG elements. Shapely's distance is
    # exact for the flattened analysis geometry. A cheap bounds-distance reject
    # avoids expensive nearest-point work for obviously distant pairs.
    for first, second in itertools.combinations(filled, 2):
        first_box = first.geometry.envelope
        second_box = second.geometry.envelope
        if first_box.distance(second_box) + _EPSILON >= minimum_mm:
            continue
        finding = _gap_finding(
            first,
            second,
            first_geometry=first.geometry,
            second_geometry=second.geometry,
            minimum_mm=minimum_mm,
        )
        if finding is not None:
            findings.append(finding)

    findings.sort(
        key=lambda finding: (
            finding.measured_mm if finding.measured_mm is not None else math.inf,
            finding.element_id or "",
            finding.related_element_id or "",
            finding.element_tag or "",
            finding.related_element_tag or "",
        )
    )
    return findings
