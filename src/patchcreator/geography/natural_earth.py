"""Natural Earth input adapter.

Only source metadata lives in the PatchCreator repository. The actual Natural
Earth archive is acquired explicitly through ``patchcreator data fetch`` and
read from the external data cache.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import shapefile

from patchcreator.data import require_dataset

LonLat = tuple[float, float]
Ring = tuple[LonLat, ...]

NATURAL_EARTH_LAND_110M = "natural-earth-land-110m"
NATURAL_EARTH_LAND_SHAPEFILE = "ne_110m_land.shp"


def load_natural_earth_land_rings(
    *,
    data_root: str | Path | None = None,
) -> tuple[Ring, ...]:
    """Load 1:110m Natural Earth land rings from the explicit data cache."""
    dataset = require_dataset(NATURAL_EARTH_LAND_110M, root=data_root)
    return load_shapefile_rings(dataset / NATURAL_EARTH_LAND_SHAPEFILE)


def load_shapefile_rings(path: str | Path) -> tuple[Ring, ...]:
    """Read polygon parts as longitude/latitude rings using pyshp.

    Ring orientation and ordering are preserved. The later filled-land renderer
    can use that information for outer/hole handling; the projection/outline
    layer only needs the individual boundaries.
    """
    source = Path(path)
    try:
        reader = shapefile.Reader(str(source))
    except (OSError, shapefile.ShapefileException) as exc:
        raise ValueError(f"failed to open geographic shapefile {source}: {exc}") from exc

    rings: list[Ring] = []
    try:
        for shape in reader.iterShapes():
            points = shape.points
            part_starts = list(shape.parts) + [len(points)]
            for start, end in zip(part_starts, part_starts[1:]):
                if end - start < 3:
                    continue
                ring = tuple((float(lon), float(lat)) for lon, lat in points[start:end])
                if ring and ring[0] != ring[-1]:
                    ring = ring + (ring[0],)
                rings.append(ring)
    finally:
        reader.close()

    return tuple(rings)
