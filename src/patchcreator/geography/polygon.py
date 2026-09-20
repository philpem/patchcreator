"""Filled-polygon reconstruction on an orthographic visible hemisphere.

``visible_polyline_parts`` is enough for coastlines, but a filled land polygon
which crosses the limb must be closed along the circular horizon rather than by
a straight chord. This module reconstructs those limb arcs using even-odd parity
and spherical containment.

The implementation intentionally works in projected physical units and does not
introduce a heavyweight GIS/boolean dependency. Natural Earth 1:110m rings are
sufficiently short-segmented for the same horizon-crossing approximation used by
the projection layer.
"""

from __future__ import annotations

import math
from typing import Sequence

from .projection import LonLat, Point, Vector3, Viewpoint, visible_polyline_parts

_EPSILON = 1e-9


def _signed_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for first, second in zip(points, points[1:]):
        total += first[0] * second[1] - second[0] * first[1]
    if points[0] != points[-1]:
        total += points[-1][0] * points[0][1] - points[0][0] * points[-1][1]
    return total / 2.0


def _unit_vector(point: LonLat) -> Vector3:
    longitude, latitude = (math.radians(value) for value in point)
    cos_latitude = math.cos(latitude)
    return (
        cos_latitude * math.cos(longitude),
        cos_latitude * math.sin(longitude),
        math.sin(latitude),
    )


def _dot(first: Vector3, second: Vector3) -> float:
    return sum(a * b for a, b in zip(first, second))


def _determinant(first: Vector3, second: Vector3, third: Vector3) -> float:
    return (
        first[0] * (second[1] * third[2] - second[2] * third[1])
        + first[1] * (second[2] * third[0] - second[0] * third[2])
        + first[2] * (second[0] * third[1] - second[1] * third[0])
    )


def _spherical_signed_area(vectors: Sequence[Vector3]) -> float:
    """Return the signed area of the smaller region bounded by a unit-sphere ring."""
    if len(vectors) < 3:
        return 0.0

    # Sum robust signed triangle areas about the first vertex.  Unlike a
    # longitude/latitude shoelace calculation this remains valid at both the
    # antimeridian and poles.  Normalising selects the smaller of the two regions
    # bounded by a spherical ring, which is the convention used by Natural Earth.
    anchor = vectors[0]
    area = 0.0
    for second, third in zip(vectors[1:], vectors[2:]):
        area += 2.0 * math.atan2(
            _determinant(anchor, second, third),
            1.0 + _dot(anchor, second) + _dot(second, third) + _dot(third, anchor),
        )
    while area > math.tau:
        area -= 2.0 * math.tau
    while area <= -math.tau:
        area += 2.0 * math.tau
    return area


def _spherical_contains(ring: Sequence[LonLat], point: LonLat) -> bool:
    """Return whether *point* lies in the ring's smaller spherical region."""
    geographic = list(ring)
    if len(geographic) > 1 and geographic[0] == geographic[-1]:
        geographic.pop()
    if len(geographic) < 3:
        return False

    vectors = [_unit_vector(item) for item in geographic]
    area = _spherical_signed_area(vectors)
    if abs(area) <= _EPSILON:
        return False

    query = _unit_vector(point)
    winding = 0.0
    for first, second in zip(vectors, vectors[1:] + vectors[:1]):
        winding += math.atan2(
            _determinant(query, first, second),
            _dot(first, second) - _dot(query, first) * _dot(query, second),
        )

    # The antipodal region has the opposite winding.  Comparing its sign with
    # the signed smaller-region area disambiguates the two sides of the sphere.
    return winding * area > _EPSILON


def _contains_point(polygon: Sequence[Point], point: Point) -> bool:
    """Return even-odd containment for one closed projected polygon."""
    x, y = point
    inside = False
    for first, second in zip(polygon, polygon[1:]):
        if (first[1] > y) == (second[1] > y):
            continue
        crossing_x = first[0] + (y - first[1]) * (second[0] - first[0]) / (
            second[1] - first[1]
        )
        if x < crossing_x:
            inside = not inside
    return inside


def _horizon_disc(
    *, centre: Point, radius: float, step_degrees: float
) -> tuple[Point, ...]:
    start = centre[0] + radius, centre[1]
    return tuple(
        _limb_arc(
            start,
            start,
            centre=centre,
            radius=radius,
            direction=1,
            step_degrees=step_degrees,
        )
    )


def _limb_arc(
    start: Point,
    end: Point,
    *,
    centre: Point,
    radius: float,
    direction: int,
    step_degrees: float,
) -> list[Point]:
    if direction not in {-1, 1}:
        raise ValueError("limb arc direction must be -1 or +1")
    if not 0 < step_degrees <= 180:
        raise ValueError("limb arc step must be between 0 and 180 degrees")

    start_angle = math.atan2(start[1] - centre[1], start[0] - centre[0])
    end_angle = math.atan2(end[1] - centre[1], end[0] - centre[0])
    full_turn = math.tau

    if direction > 0:
        delta = (end_angle - start_angle) % full_turn
        if delta <= _EPSILON:
            delta = full_turn
    else:
        delta = -((start_angle - end_angle) % full_turn)
        if abs(delta) <= _EPSILON:
            delta = -full_turn

    step = math.radians(step_degrees)
    segments = max(1, int(math.ceil(abs(delta) / step)))
    result: list[Point] = []
    for index in range(segments + 1):
        angle = start_angle + delta * index / segments
        result.append(
            (
                centre[0] + radius * math.cos(angle),
                centre[1] + radius * math.sin(angle),
            )
        )
    # Preserve the exact horizon intersections produced by the projection layer.
    result[0] = start
    result[-1] = end
    return result


def _closed_candidate(chain: Sequence[Point], arc: Sequence[Point]) -> tuple[Point, ...]:
    result = list(chain)
    result.extend(arc[1:])
    if result[-1] != result[0]:
        result.append(result[0])
    return tuple(result)


def visible_ring_polygons(
    ring: Sequence[LonLat],
    viewpoint: Viewpoint,
    *,
    radius: float = 1.0,
    centre: Point = (0.0, 0.0),
    simplify_tolerance: float = 0.0,
    limb_step_degrees: float = 4.0,
) -> tuple[tuple[Point, ...], ...]:
    """Project a geographic land ring into one or more filled visible polygons.

    Every returned polygon is closed. Rings crossing the camera horizon are split
    into visible coastline chains. Each chain is closed to the smaller projected
    region, then a whole-disc parity polygon is added when spherical containment
    shows that the camera lies inside the source ring. Callers combine the
    resulting subpaths with ``fill-rule: evenodd``.

    This parity construction handles polar rings, antimeridian crossings and
    rings with several independent visible coastline chains without relying on
    longitude/latitude orientation, which is ambiguous at the poles.
    """
    if radius <= 0:
        raise ValueError("orthographic radius must be positive")

    parts = visible_polyline_parts(
        ring,
        viewpoint,
        radius=radius,
        centre=centre,
        closed=True,
        simplify_tolerance=simplify_tolerance,
    )
    camera_inside = _spherical_contains(
        ring, (viewpoint.longitude, viewpoint.latitude)
    )
    if not parts:
        if camera_inside:
            return (
                _horizon_disc(
                    centre=centre,
                    radius=radius,
                    step_degrees=limb_step_degrees,
                ),
            )
        return ()

    polygons: list[tuple[Point, ...]] = []

    for part in parts:
        if len(part) < 3:
            continue
        if part[0] == part[-1]:
            polygons.append(tuple(part))
            continue

        positive_arc = _limb_arc(
            part[-1],
            part[0],
            centre=centre,
            radius=radius,
            direction=1,
            step_degrees=limb_step_degrees,
        )
        negative_arc = _limb_arc(
            part[-1],
            part[0],
            centre=centre,
            radius=radius,
            direction=-1,
            step_degrees=limb_step_degrees,
        )
        candidates = (
            _closed_candidate(part, positive_arc),
            _closed_candidate(part, negative_arc),
        )
        polygons.append(min(candidates, key=lambda item: abs(_signed_area(item))))

    projected_centre_inside = bool(
        sum(_contains_point(polygon, centre) for polygon in polygons) % 2
    )
    if projected_centre_inside != camera_inside:
        polygons.append(
            _horizon_disc(
                centre=centre,
                radius=radius,
                step_degrees=limb_step_degrees,
            )
        )

    return tuple(polygons)
