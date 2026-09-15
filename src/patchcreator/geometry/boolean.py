"""Shapely-backed boolean/offset helpers shared by clip/export operations.

These functions operate on analysis geometry only. They never mutate the
editable source SVG. Distances are expressed in the same physical millimetre
coordinate system used by PatchCreator's scene graph.
"""

from __future__ import annotations

from collections.abc import Iterable

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


def offset_geometry(
    geometry: BaseGeometry,
    *,
    inset_mm: float,
    mitre_limit: float = 5.0,
) -> BaseGeometry:
    """Offset polygonal geometry by a physical inset/outset.

    PatchCreator's author-facing convention is positive=inward and
    negative=outward, hence the sign inversion passed to Shapely ``buffer``.
    Mitred joins preserve straight-edged artwork instead of silently rounding
    every convex corner. Shapely still bevels pathological mitres beyond
    ``mitre_limit``.
    """
    if geometry.is_empty or inset_mm == 0:
        return geometry
    result = geometry.buffer(
        -float(inset_mm),
        join_style="mitre",
        mitre_limit=float(mitre_limit),
    )
    if result.is_empty:
        raise ValueError("custom clip inset consumes the entire clipping silhouette")
    if not result.is_valid:
        result = result.buffer(0)
    if result.is_empty:
        raise ValueError("custom clip offset produced empty geometry")
    return result


def polygon_components(geometry: BaseGeometry) -> tuple[Polygon, ...]:
    """Return polygon components recursively, ignoring non-area fragments."""
    if geometry.is_empty:
        return ()
    if isinstance(geometry, Polygon):
        return (geometry,)
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        result: list[Polygon] = []
        for child in geometry.geoms:
            result.extend(polygon_components(child))
        return tuple(result)
    return ()


def _fmt(value: float) -> str:
    return f"{value:.9f}".rstrip("0").rstrip(".") or "0"


def _ring_path(points: Iterable[tuple[float, float]]) -> str:
    coords = list(points)
    if len(coords) < 3:
        return ""
    if coords[0] == coords[-1]:
        coords.pop()
    if len(coords) < 3:
        return ""
    chunks = [f"M {_fmt(coords[0][0])},{_fmt(coords[0][1])}"]
    chunks.extend(f"L {_fmt(x)},{_fmt(y)}" for x, y in coords[1:])
    chunks.append("Z")
    return " ".join(chunks)


def geometry_to_svg_path(geometry: BaseGeometry) -> str:
    """Serialize polygonal geometry as one even-odd SVG path string."""
    chunks: list[str] = []
    for polygon in polygon_components(geometry):
        exterior = _ring_path(polygon.exterior.coords)
        if exterior:
            chunks.append(exterior)
        for interior in polygon.interiors:
            hole = _ring_path(interior.coords)
            if hole:
                chunks.append(hole)
    if not chunks:
        raise ValueError("custom clip geometry contains no polygonal area")
    return " ".join(chunks)
