"""Physical-unit and artist-facing coordinate helpers."""

from __future__ import annotations

import math
import re

_LENGTH_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(mm)?\s*$", re.I)
_RADIUS_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*r\s*$", re.I)
_ANGLE_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(deg|°)?\s*$", re.I)


def parse_length_mm(value: float | int | str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = _LENGTH_RE.match(value)
    if not match:
        raise ValueError(f"invalid millimetre length: {value!r}")
    return float(match.group(1))


def parse_angle_degrees(value: float | int | str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = _ANGLE_RE.match(value)
    if not match:
        raise ValueError(f"invalid angle: {value!r}; use degrees, e.g. '45deg'")
    return float(match.group(1))


def parse_radius(value: float | int | str, reference_radius: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    relative = _RADIUS_RE.match(value)
    if relative:
        return float(relative.group(1)) * reference_radius
    return parse_length_mm(value)


def polar_to_cartesian(radius: float, angle_degrees: float) -> tuple[float, float]:
    """Convert artist-facing polar coordinates to x/y offsets.

    PatchCreator defines 0 degrees as up and positive angles clockwise. SVG's
    positive-y direction is downward, so this maps directly to x=r*sin(theta),
    y=-r*cos(theta) in a centre-origin artist coordinate system.
    """
    theta = math.radians(angle_degrees)
    return radius * math.sin(theta), -radius * math.cos(theta)
