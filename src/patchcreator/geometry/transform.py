"""Small dependency-free 2D affine transform helpers.

The matrix layout matches SVG's ``matrix(a b c d e f)`` convention::

    x' = a*x + c*y + e
    y' = b*x + d*y + f

``left @ right`` composes transforms in the same order as matrix
multiplication: ``right`` is applied to a point first, followed by ``left``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin

Point = tuple[float, float]


@dataclass(frozen=True)
class AffineTransform:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @classmethod
    def identity(cls) -> "AffineTransform":
        return cls()

    @classmethod
    def translation(cls, x: float, y: float) -> "AffineTransform":
        return cls(e=float(x), f=float(y))

    @classmethod
    def scale(cls, x: float, y: float | None = None) -> "AffineTransform":
        if y is None:
            y = x
        return cls(a=float(x), d=float(y))

    @classmethod
    def rotation(
        cls,
        degrees: float,
        *,
        centre: Point | None = None,
    ) -> "AffineTransform":
        angle = radians(degrees)
        rotation = cls(a=cos(angle), b=sin(angle), c=-sin(angle), d=cos(angle))
        if centre is None:
            return rotation
        cx, cy = centre
        return cls.translation(cx, cy) @ rotation @ cls.translation(-cx, -cy)

    def apply(self, point: Point) -> Point:
        x, y = point
        return (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )

    def __matmul__(self, other: "AffineTransform") -> "AffineTransform":
        """Compose two transforms, applying ``other`` then ``self``."""
        return AffineTransform(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def to_svg(self) -> str:
        """Return an SVG ``matrix(...)`` transform value."""
        values = (self.a, self.b, self.c, self.d, self.e, self.f)
        formatted = " ".join(f"{value:.12g}" for value in values)
        return f"matrix({formatted})"
