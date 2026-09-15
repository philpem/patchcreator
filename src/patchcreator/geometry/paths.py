"""Path sampling abstractions used by path-following placement.

Procedural trajectories and orbits expose the same small sampler interface as
simple test paths. Richer samplers additionally expose physical length and
bounds so path-following placement can accept distances as well as fractions.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from .primitives import Bounds
from .transform import Point

_EPSILON = 1e-12


@dataclass(frozen=True)
class PathSample:
    point: Point
    tangent: Point


@runtime_checkable
class PathSampler(Protocol):
    def sample(self, fraction: float) -> PathSample:
        """Sample a path at an arc-length fraction from 0.0 to 1.0."""
        ...


@runtime_checkable
class MeasurablePathSampler(PathSampler, Protocol):
    def length(self) -> float:
        """Return approximate/analytic physical path length in local SVG units."""
        ...


@dataclass(frozen=True)
class LinePath:
    """Straight path with exact length, bounds and sampling."""

    start: Point
    end: Point

    def length(self) -> float:
        return math.hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    @property
    def bounds(self) -> Bounds:
        return Bounds(
            min(self.start[0], self.end[0]),
            min(self.start[1], self.end[1]),
            max(self.start[0], self.end[0]),
            max(self.start[1], self.end[1]),
        )

    def sample(self, fraction: float) -> PathSample:
        _validate_fraction(fraction)
        sx, sy = self.start
        ex, ey = self.end
        dx, dy = ex - sx, ey - sy
        if abs(dx) <= _EPSILON and abs(dy) <= _EPSILON:
            raise ValueError("cannot sample the tangent of a zero-length path")
        return PathSample(
            point=(sx + dx * fraction, sy + dy * fraction),
            tangent=(dx, dy),
        )


@dataclass(frozen=True)
class CubicBezierPath:
    """One cubic Bezier segment sampled by approximate arc length."""

    start: Point
    control1: Point
    control2: Point
    end: Point
    length_subdivisions: int = 128

    def __post_init__(self) -> None:
        if self.length_subdivisions < 8:
            raise ValueError("Bezier length_subdivisions must be at least 8")

    def point_at_parameter(self, t: float) -> Point:
        _validate_fraction(t)
        u = 1.0 - t
        p0, p1, p2, p3 = self.start, self.control1, self.control2, self.end
        return (
            u**3 * p0[0]
            + 3.0 * u * u * t * p1[0]
            + 3.0 * u * t * t * p2[0]
            + t**3 * p3[0],
            u**3 * p0[1]
            + 3.0 * u * u * t * p1[1]
            + 3.0 * u * t * t * p2[1]
            + t**3 * p3[1],
        )

    def tangent_at_parameter(self, t: float) -> Point:
        _validate_fraction(t)
        u = 1.0 - t
        p0, p1, p2, p3 = self.start, self.control1, self.control2, self.end
        return (
            3.0 * u * u * (p1[0] - p0[0])
            + 6.0 * u * t * (p2[0] - p1[0])
            + 3.0 * t * t * (p3[0] - p2[0]),
            3.0 * u * u * (p1[1] - p0[1])
            + 6.0 * u * t * (p2[1] - p1[1])
            + 3.0 * t * t * (p3[1] - p2[1]),
        )

    def length(self) -> float:
        return _arc_length_table(self.point_at_parameter, self.length_subdivisions)[1][-1]

    @property
    def bounds(self) -> Bounds:
        ts = {0.0, 1.0}
        ts.update(
            _cubic_extrema_parameters(
                self.start[0], self.control1[0], self.control2[0], self.end[0]
            )
        )
        ts.update(
            _cubic_extrema_parameters(
                self.start[1], self.control1[1], self.control2[1], self.end[1]
            )
        )
        points = [self.point_at_parameter(t) for t in ts]
        return Bounds(
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )

    def sample(self, fraction: float) -> PathSample:
        _validate_fraction(fraction)
        parameters, lengths = _arc_length_table(
            self.point_at_parameter,
            self.length_subdivisions,
        )
        t = _parameter_for_length_fraction(parameters, lengths, fraction)
        tangent = self.tangent_at_parameter(t)
        if math.hypot(*tangent) <= _EPSILON:
            raise ValueError("cannot sample the tangent of a degenerate Bezier path")
        return PathSample(self.point_at_parameter(t), tangent)


@dataclass(frozen=True)
class EllipsePath:
    """Rotatable full ellipse with artist-facing 0 degrees at top, clockwise."""

    radius_x: float
    radius_y: float
    centre: Point = (0.0, 0.0)
    rotation_degrees: float = 0.0
    phase_degrees: float = 0.0
    length_subdivisions: int = 256

    def __post_init__(self) -> None:
        if self.radius_x <= 0 or self.radius_y <= 0:
            raise ValueError("ellipse radii must be positive")
        if self.length_subdivisions < 16:
            raise ValueError("ellipse length_subdivisions must be at least 16")

    def point_at_parameter(self, t: float) -> Point:
        _validate_fraction(t)
        theta = math.radians(self.phase_degrees) + math.tau * t
        # Artist convention: theta=0 is top and increases clockwise.
        x = self.radius_x * math.sin(theta)
        y = -self.radius_y * math.cos(theta)
        return _rotate_translate((x, y), self.centre, self.rotation_degrees)

    def tangent_at_parameter(self, t: float) -> Point:
        _validate_fraction(t)
        theta = math.radians(self.phase_degrees) + math.tau * t
        tangent = (
            self.radius_x * math.cos(theta),
            self.radius_y * math.sin(theta),
        )
        return _rotate_vector(tangent, self.rotation_degrees)

    def length(self) -> float:
        return _arc_length_table(self.point_at_parameter, self.length_subdivisions)[1][-1]

    @property
    def bounds(self) -> Bounds:
        angle = math.radians(self.rotation_degrees)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        half_width = math.sqrt(
            (self.radius_x * cos_a) ** 2 + (self.radius_y * sin_a) ** 2
        )
        half_height = math.sqrt(
            (self.radius_x * sin_a) ** 2 + (self.radius_y * cos_a) ** 2
        )
        return Bounds(
            self.centre[0] - half_width,
            self.centre[1] - half_height,
            self.centre[0] + half_width,
            self.centre[1] + half_height,
        )

    def sample(self, fraction: float) -> PathSample:
        _validate_fraction(fraction)
        parameters, lengths = _arc_length_table(
            self.point_at_parameter,
            self.length_subdivisions,
        )
        t = _parameter_for_length_fraction(parameters, lengths, fraction)
        return PathSample(self.point_at_parameter(t), self.tangent_at_parameter(t))


@dataclass(frozen=True)
class CompoundPath:
    """Ordered measurable segments treated as one continuous path."""

    segments: tuple[MeasurablePathSampler, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("compound path requires at least one segment")
        for first, second in zip(self.segments, self.segments[1:]):
            first_end = first.sample(1.0).point
            second_start = second.sample(0.0).point
            if math.hypot(
                first_end[0] - second_start[0],
                first_end[1] - second_start[1],
            ) > 1e-8:
                raise ValueError("compound path segments are not contiguous")

    def length(self) -> float:
        return sum(segment.length() for segment in self.segments)

    @property
    def bounds(self) -> Bounds:
        bounds: Bounds | None = None
        for segment in self.segments:
            current = getattr(segment, "bounds", None)
            if current is None:
                # Conservative fallback for third-party measurable segments.
                points = [segment.sample(index / 32.0).point for index in range(33)]
                current = Bounds(
                    min(point[0] for point in points),
                    min(point[1] for point in points),
                    max(point[0] for point in points),
                    max(point[1] for point in points),
                )
            combined = Bounds.union(bounds, current)
            assert combined is not None
            bounds = combined
        assert bounds is not None
        return bounds

    def sample(self, fraction: float) -> PathSample:
        _validate_fraction(fraction)
        lengths = [segment.length() for segment in self.segments]
        total = sum(lengths)
        if total <= _EPSILON:
            raise ValueError("cannot sample a zero-length compound path")
        target = fraction * total
        elapsed = 0.0
        for index, (segment, length) in enumerate(zip(self.segments, lengths)):
            if index == len(self.segments) - 1 or target <= elapsed + length:
                local = 0.0 if length <= _EPSILON else (target - elapsed) / length
                return segment.sample(max(0.0, min(1.0, local)))
            elapsed += length
        return self.segments[-1].sample(1.0)  # pragma: no cover


def _validate_fraction(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("path fraction must be between 0 and 1")


def _arc_length_table(
    point_at: Callable[[float], Point],
    subdivisions: int,
) -> tuple[list[float], list[float]]:
    parameters = [index / subdivisions for index in range(subdivisions + 1)]
    lengths = [0.0]
    previous = point_at(0.0)
    total = 0.0
    for parameter in parameters[1:]:
        point = point_at(parameter)
        total += math.hypot(point[0] - previous[0], point[1] - previous[1])
        lengths.append(total)
        previous = point
    return parameters, lengths


def _parameter_for_length_fraction(
    parameters: list[float],
    lengths: list[float],
    fraction: float,
) -> float:
    total = lengths[-1]
    if total <= _EPSILON:
        raise ValueError("cannot sample a zero-length path")
    target = fraction * total
    index = bisect_left(lengths, target)
    if index <= 0:
        return parameters[0]
    if index >= len(lengths):
        return parameters[-1]
    previous_length, next_length = lengths[index - 1], lengths[index]
    span = next_length - previous_length
    if span <= _EPSILON:
        return parameters[index]
    ratio = (target - previous_length) / span
    return parameters[index - 1] + ratio * (parameters[index] - parameters[index - 1])


def _cubic_extrema_parameters(
    p0: float,
    p1: float,
    p2: float,
    p3: float,
) -> set[float]:
    # Cubic power coefficients; derivative is 3a*t^2 + 2b*t + c.
    a = -p0 + 3.0 * p1 - 3.0 * p2 + p3
    b = 3.0 * p0 - 6.0 * p1 + 3.0 * p2
    c = -3.0 * p0 + 3.0 * p1
    qa, qb, qc = 3.0 * a, 2.0 * b, c

    roots: set[float] = set()
    if abs(qa) <= _EPSILON:
        if abs(qb) > _EPSILON:
            root = -qc / qb
            if 0.0 < root < 1.0:
                roots.add(root)
        return roots

    discriminant = qb * qb - 4.0 * qa * qc
    if discriminant < 0:
        return roots
    sqrt_d = math.sqrt(max(0.0, discriminant))
    for root in (
        (-qb - sqrt_d) / (2.0 * qa),
        (-qb + sqrt_d) / (2.0 * qa),
    ):
        if 0.0 < root < 1.0:
            roots.add(root)
    return roots


def _rotate_vector(vector: Point, degrees: float) -> Point:
    angle = math.radians(degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (
        vector[0] * cos_a - vector[1] * sin_a,
        vector[0] * sin_a + vector[1] * cos_a,
    )


def _rotate_translate(point: Point, centre: Point, degrees: float) -> Point:
    rotated = _rotate_vector(point, degrees)
    return centre[0] + rotated[0], centre[1] + rotated[1]
