"""Dependency-light orthographic globe projection helpers.

The projection core is intentionally separate from SVG rendering so it can be
tested against synthetic geometry and reused by future globe, horizon, grid and
terminator components.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

LonLat = tuple[float, float]
Point = tuple[float, float]
Vector3 = tuple[float, float, float]

_EPSILON = 1e-12


@dataclass(frozen=True)
class Viewpoint:
    """Orthographic camera centre in geographic degrees."""

    latitude: float = 0.0
    longitude: float = 0.0

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError("viewpoint latitude must be between -90 and +90 degrees")


def _view_vector(lon_deg: float, lat_deg: float, viewpoint: Viewpoint) -> Vector3:
    """Return screen-right, screen-down, camera-depth coordinates on unit sphere."""
    lat = math.radians(lat_deg)
    lat0 = math.radians(viewpoint.latitude)
    dlon = math.radians(lon_deg - viewpoint.longitude)

    cos_lat = math.cos(lat)
    sin_lat = math.sin(lat)
    cos_lat0 = math.cos(lat0)
    sin_lat0 = math.sin(lat0)
    cos_dlon = math.cos(dlon)

    x = cos_lat * math.sin(dlon)
    # Negated conventional projected Y so positive values follow SVG screen-down.
    y = sin_lat0 * cos_lat * cos_dlon - cos_lat0 * sin_lat
    z = cos_lat0 * cos_lat * cos_dlon + sin_lat0 * sin_lat
    return x, y, z


def orthographic_point(
    lon_deg: float,
    lat_deg: float,
    viewpoint: Viewpoint,
    *,
    radius: float = 1.0,
    centre: Point = (0.0, 0.0),
) -> tuple[Point, bool]:
    """Project one point and report whether it lies on the visible hemisphere."""
    if radius <= 0:
        raise ValueError("orthographic radius must be positive")
    x, y, z = _view_vector(lon_deg, lat_deg, viewpoint)
    return (centre[0] + radius * x, centre[1] + radius * y), z >= -_EPSILON


def _limb_intersection(a: Vector3, b: Vector3, radius: float, centre: Point) -> Point:
    """Intersect a short spherical edge with the camera horizon.

    Natural Earth line segments are short. Interpolating their unit vectors and
    renormalising at z=0 provides a stable, deterministic approximation of the
    corresponding great-circle horizon crossing without requiring GIS/projection
    dependencies in this layer.
    """
    denominator = a[2] - b[2]
    if abs(denominator) <= _EPSILON:
        t = 0.5
    else:
        t = a[2] / denominator
    t = max(0.0, min(1.0, t))
    x = a[0] + (b[0] - a[0]) * t
    y = a[1] + (b[1] - a[1]) * t
    norm = math.hypot(x, y)
    if norm <= _EPSILON:
        # Degenerate antipodal edge: choose a deterministic point on the limb.
        x, y, norm = 1.0, 0.0, 1.0
    return centre[0] + radius * x / norm, centre[1] + radius * y / norm


def _project_vector(vector: Vector3, radius: float, centre: Point) -> Point:
    return centre[0] + radius * vector[0], centre[1] + radius * vector[1]


def visible_polyline_parts(
    points: Sequence[LonLat],
    viewpoint: Viewpoint,
    *,
    radius: float = 1.0,
    centre: Point = (0.0, 0.0),
    closed: bool = False,
    simplify_tolerance: float = 0.0,
) -> tuple[tuple[Point, ...], ...]:
    """Project the visible portions of a geographic line/ring.

    The back hemisphere is removed explicitly rather than merely clipping the
    2D projection to a circle (back-side orthographic points also project inside
    that circle). Horizon crossings are inserted on the exact projected limb.

    For closed rings containing both front- and back-side vertices, each visible
    chain is returned separately. This representation is directly suitable for
    coastline/outline rendering; filled land clipping is intentionally a later
    layer because it must also reconstruct the appropriate limb arc.
    """
    if radius <= 0:
        raise ValueError("orthographic radius must be positive")
    if simplify_tolerance < 0:
        raise ValueError("simplification tolerance must not be negative")
    if len(points) < 2:
        return ()

    geographic = list(points)
    if closed and len(geographic) > 1 and geographic[0] == geographic[-1]:
        geographic.pop()
    if len(geographic) < 2:
        return ()

    vectors = [_view_vector(lon, lat, viewpoint) for lon, lat in geographic]
    visible = [vector[2] >= -_EPSILON for vector in vectors]

    if closed and all(visible):
        projected = [_project_vector(vector, radius, centre) for vector in vectors]
        projected.append(projected[0])
        return (tuple(simplify_polyline(projected, simplify_tolerance, closed=True)),)
    if closed and not any(visible):
        return ()

    if closed:
        # Rotate so the ring starts on the hidden hemisphere. This prevents one
        # visible chain from being split at the arbitrary source-ring start.
        hidden_index = next(index for index, flag in enumerate(visible) if not flag)
        geographic = geographic[hidden_index:] + geographic[:hidden_index]
        vectors = vectors[hidden_index:] + vectors[:hidden_index]
        visible = visible[hidden_index:] + visible[:hidden_index]
        edge_count = len(vectors)
        endpoints = [(index, (index + 1) % len(vectors)) for index in range(edge_count)]
    else:
        endpoints = [(index, index + 1) for index in range(len(vectors) - 1)]

    parts: list[list[Point]] = []
    current: list[Point] | None = None

    for start_index, end_index in endpoints:
        start = vectors[start_index]
        end = vectors[end_index]
        start_visible = start[2] >= -_EPSILON
        end_visible = end[2] >= -_EPSILON

        if start_visible and end_visible:
            if current is None:
                current = [_project_vector(start, radius, centre)]
            current.append(_project_vector(end, radius, centre))
            continue

        if start_visible and not end_visible:
            if current is None:
                current = [_project_vector(start, radius, centre)]
            current.append(_limb_intersection(start, end, radius, centre))
            if len(current) >= 2:
                parts.append(current)
            current = None
            continue

        if not start_visible and end_visible:
            current = [
                _limb_intersection(start, end, radius, centre),
                _project_vector(end, radius, centre),
            ]
            continue

        # Both endpoints hidden. Nothing is visible for this short edge.

    if current is not None and len(current) >= 2:
        parts.append(current)

    simplified: list[tuple[Point, ...]] = []
    for part in parts:
        candidate = simplify_polyline(part, simplify_tolerance)
        if len(candidate) >= 2:
            simplified.append(tuple(candidate))
    return tuple(simplified)


def simplify_polyline(
    points: Sequence[Point],
    tolerance: float,
    *,
    closed: bool = False,
) -> list[Point]:
    """Simplify projected geometry in physical/output units using Douglas-Peucker."""
    if tolerance < 0:
        raise ValueError("simplification tolerance must not be negative")
    if len(points) <= 2 or tolerance == 0:
        return list(points)

    if closed:
        ring = list(points)
        if ring[0] == ring[-1]:
            ring.pop()
        if len(ring) <= 3:
            return ring + [ring[0]]

        first = ring[0]
        split_index = max(
            range(1, len(ring)),
            key=lambda index: (ring[index][0] - first[0]) ** 2 + (ring[index][1] - first[1]) ** 2,
        )
        first_half = _douglas_peucker(ring[: split_index + 1], tolerance)
        second_half = _douglas_peucker(ring[split_index:] + [ring[0]], tolerance)
        combined = first_half[:-1] + second_half
        if combined[-1] != combined[0]:
            combined.append(combined[0])
        return combined

    return _douglas_peucker(list(points), tolerance)


def _douglas_peucker(points: list[Point], tolerance: float) -> list[Point]:
    if len(points) <= 2:
        return points

    start = points[0]
    end = points[-1]
    max_distance = -1.0
    max_index = -1
    for index in range(1, len(points) - 1):
        distance = _distance_to_segment(points[index], start, end)
        if distance > max_distance:
            max_distance = distance
            max_index = index

    if max_distance > tolerance:
        left = _douglas_peucker(points[: max_index + 1], tolerance)
        right = _douglas_peucker(points[max_index:], tolerance)
        return left[:-1] + right
    return [start, end]


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= _EPSILON:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    nearest = start[0] + t * dx, start[1] + t * dy
    return math.hypot(point[0] - nearest[0], point[1] - nearest[1])


def default_simplification_tolerance(
    diameter_mm: float,
    *,
    intent: str | None = None,
    embroidery_safety: bool = True,
) -> float:
    """Return an initial physical simplification tolerance for globe linework.

    These are deliberately conservative rendering defaults, not universal
    embroidery limits. The explicit component option will override them, and a
    later validation pass remains authoritative for actual stitchability.
    """
    if diameter_mm <= 0:
        raise ValueError("globe diameter must be positive")
    if not embroidery_safety or intent == "display-art":
        return max(0.02, diameter_mm / 1500.0)
    if intent == "small-patch":
        return max(0.20, diameter_mm / 180.0)
    # standard-patch and unspecified intents favour slightly more detail.
    return max(0.10, diameter_mm / 260.0)
