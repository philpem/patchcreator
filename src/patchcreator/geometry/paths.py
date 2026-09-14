"""Path sampling abstractions used by path-following placement.

Trajectory/orbit components will provide richer path implementations. Keeping
placement dependent on this small protocol avoids coupling it to any one path
representation or SVG parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .transform import Point


@dataclass(frozen=True)
class PathSample:
    point: Point
    tangent: Point


@runtime_checkable
class PathSampler(Protocol):
    def sample(self, fraction: float) -> PathSample:
        """Sample a path at a fraction from 0.0 to 1.0."""
        ...


@dataclass(frozen=True)
class LinePath:
    """Simple path sampler useful for tests and straight trajectories."""

    start: Point
    end: Point

    def sample(self, fraction: float) -> PathSample:
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("path fraction must be between 0 and 1")
        sx, sy = self.start
        ex, ey = self.end
        dx, dy = ex - sx, ey - sy
        if dx == 0.0 and dy == 0.0:
            raise ValueError("cannot sample the tangent of a zero-length path")
        return PathSample(
            point=(sx + dx * fraction, sy + dy * fraction),
            tangent=(dx, dy),
        )
