"""Small filled-feature and detached-island embroidery validators."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .geometry import iter_visible_fills, polygon_components
from .model import Finding


def _bounds_tuple(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in bounds)  # type: ignore[return-value]


def validate_small_features(
    root: ET.Element,
    *,
    minimum_dimension_mm: float | None = None,
    minimum_island_area_mm2: float | None = None,
) -> tuple[Finding, ...]:
    """Report undersized filled objects and connected polygon islands.

    Dimension findings are per SVG painted element. Area findings are per
    connected polygon component, so a tiny detached subpath inside a larger
    compound object is still identified separately.
    """

    if minimum_dimension_mm is not None and minimum_dimension_mm < 0:
        raise ValueError("minimum feature dimension must not be negative")
    if minimum_island_area_mm2 is not None and minimum_island_area_mm2 < 0:
        raise ValueError("minimum island area must not be negative")

    findings: list[Finding] = []
    for item in iter_visible_fills(root):
        geometry = item.geometry
        min_x, min_y, max_x, max_y = geometry.bounds
        width = max_x - min_x
        height = max_y - min_y
        minimum_dimension = min(width, height)
        bounds = _bounds_tuple((min_x, min_y, max_x, max_y))

        if (
            minimum_dimension_mm is not None
            and minimum_dimension_mm > 0
            and minimum_dimension + 1e-9 < minimum_dimension_mm
        ):
            findings.append(
                Finding(
                    code="feature-too-small",
                    severity="warning",
                    message="filled feature has a physical dimension below the selected profile minimum",
                    element_id=item.element_id,
                    element_tag=item.element_tag,
                    measured_mm=minimum_dimension,
                    threshold_mm=minimum_dimension_mm,
                    bounds_mm=bounds,
                )
            )

        if minimum_island_area_mm2 is None or minimum_island_area_mm2 <= 0:
            continue
        components = polygon_components(geometry)
        for index, component in enumerate(components):
            if component.area + 1e-9 >= minimum_island_area_mm2:
                continue
            component_bounds = _bounds_tuple(component.bounds)
            suffix = f" (island {index + 1} of {len(components)})" if len(components) > 1 else ""
            findings.append(
                Finding(
                    code="island-too-small",
                    severity="warning",
                    message="filled connected island area is below the selected profile minimum" + suffix,
                    element_id=item.element_id,
                    element_tag=item.element_tag,
                    measured_mm2=float(component.area),
                    threshold_mm2=minimum_island_area_mm2,
                    bounds_mm=component_bounds,
                )
            )

    return tuple(findings)
