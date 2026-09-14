"""Filled-polygon reconstruction on an orthographic visible hemisphere.

``visible_polyline_parts`` is enough for coastlines, but a filled land polygon
which crosses the limb must be closed along the circular horizon rather than by
a straight chord. This module reconstructs those limb arcs while preserving the
source ring's orientation.

The implementation intentionally works in projected physical units and does not
introduce a heavyweight GIS/boolean dependency. Natural Earth 1:110m rings are
sufficiently short-segmented for the same horizon-crossing approximation used by
the projection layer.
"""

from __future__ import annotations

import math
from typing import Sequence

from .projection import LonLat, Point, Viewpoint, visible_polyline_parts

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


def _geographic_orientation(ring: Sequence[LonLat]) -> int:
    """Return source ring orientation after unwrapping the antimeridian.

    ESRI/Natural Earth rings carry meaningful orientation. A naive shoelace area
    can invert for rings crossing +/-180 degrees, so longitudes are unwrapped to
    follow the shortest step from each previous vertex first.
    """
    points = list(ring)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        return 0

    unwrapped: list[Point] = []
    previous = points[0][0]
    unwrapped.append((previous, points[0][1]))
    for lon, lat in points[1:]:
        value = lon
        while value - previous > 180.0:
            value -= 360.0
        while value - previous < -180.0:
            value += 360.0
        unwrapped.append((value, lat))
        previous = value
    unwrapped.append(unwrapped[0])
    area = _signed_area(unwrapped)
    if area > _EPSILON:
        return 1
    if area < -_EPSILON:
        return -1
    return 0


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

    Every returned polygon is closed. Rings wholly on the visible hemisphere are
    passed through directly. Rings crossing the camera horizon are split into
    visible coastline chains and each chain is closed using the appropriate limb
    arc. The arc direction is chosen to preserve the source ring orientation.

    SVG's screen-down Y axis reverses orientation relative to longitude/latitude,
    so the expected projected sign is the inverse of the unwrapped source sign.
    This works for both outer rings and holes; callers can combine all subpaths
    with ``fill-rule: evenodd``.
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
    if not parts:
        return ()

    expected_orientation = -_geographic_orientation(ring)
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
        areas = tuple(_signed_area(candidate) for candidate in candidates)

        chosen: tuple[Point, ...] | None = None
        if expected_orientation:
            for candidate, area in zip(candidates, areas):
                sign = 1 if area > _EPSILON else -1 if area < -_EPSILON else 0
                if sign == expected_orientation:
                    if chosen is None or abs(area) < abs(_signed_area(chosen)):
                        chosen = candidate
        if chosen is None:
            # Degenerate/ambiguous source orientation: prefer the smaller region
            # rather than accidentally filling almost the entire globe.
            chosen = min(zip(candidates, areas), key=lambda item: abs(item[1]))[0]
        polygons.append(chosen)

    return tuple(polygons)
