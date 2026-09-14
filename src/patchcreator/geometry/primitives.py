"""Basic geometry primitives shared by the compositor and validators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .transform import AffineTransform, Point


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned bounds in millimetres."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError("bounds minimum must not exceed maximum")

    @classmethod
    def from_points(cls, points: Iterable[Point]) -> "Bounds":
        points = tuple(points)
        if not points:
            raise ValueError("cannot construct bounds from no points")
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return cls(min(xs), min(ys), max(xs), max(ys))

    @classmethod
    def union(cls, *bounds: "Bounds | None") -> "Bounds | None":
        present = [item for item in bounds if item is not None]
        if not present:
            return None
        return cls(
            min(item.min_x for item in present),
            min(item.min_y for item in present),
            max(item.max_x for item in present),
            max(item.max_y for item in present),
        )

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def centre(self) -> Point:
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    @property
    def corners(self) -> tuple[Point, Point, Point, Point]:
        return (
            (self.min_x, self.min_y),
            (self.max_x, self.min_y),
            (self.max_x, self.max_y),
            (self.min_x, self.max_y),
        )

    def transformed(self, transform: AffineTransform) -> "Bounds":
        return Bounds.from_points(transform.apply(point) for point in self.corners)

    def anchor(self, name: str) -> Point:
        """Return a conventional anchor derived from the bounds.

        Component-supplied anchors can override these names at scene-resolution
        time. Both British ``centre`` and American ``center`` spellings are
        accepted because imported SVG assets may use either.
        """
        cx, cy = self.centre
        anchors: dict[str, Point] = {
            "centre": (cx, cy),
            "center": (cx, cy),
            "top": (cx, self.min_y),
            "north": (cx, self.min_y),
            "bottom": (cx, self.max_y),
            "south": (cx, self.max_y),
            "left": (self.min_x, cy),
            "west": (self.min_x, cy),
            "right": (self.max_x, cy),
            "east": (self.max_x, cy),
            "top-left": (self.min_x, self.min_y),
            "top-right": (self.max_x, self.min_y),
            "bottom-left": (self.min_x, self.max_y),
            "bottom-right": (self.max_x, self.max_y),
        }
        try:
            return anchors[name]
        except KeyError as exc:
            raise KeyError(f"unknown bounds anchor {name!r}") from exc

    def standard_anchors(self) -> dict[str, Point]:
        names = (
            "centre",
            "center",
            "top",
            "north",
            "bottom",
            "south",
            "left",
            "west",
            "right",
            "east",
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
        )
        return {name: self.anchor(name) for name in names}
