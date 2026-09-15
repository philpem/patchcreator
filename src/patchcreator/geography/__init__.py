"""Geographic data and projection helpers for procedural celestial artwork."""

from .natural_earth import load_natural_earth_land_rings, load_shapefile_rings
from .polygon import visible_ring_polygons
from .projection import (
    Viewpoint,
    default_simplification_tolerance,
    orthographic_point,
    simplify_polyline,
    visible_polyline_parts,
)

__all__ = [
    "Viewpoint",
    "default_simplification_tolerance",
    "load_natural_earth_land_rings",
    "load_shapefile_rings",
    "orthographic_point",
    "simplify_polyline",
    "visible_polyline_parts",
    "visible_ring_polygons",
]
