"""Procedural component registration and render metadata.

The registry remains deliberately small and extensible. Component renderers
write their geometry in the node's local SVG coordinate system and return the
bounds/anchors/path samplers needed by the scene and placement passes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from patchcreator.geometry.paths import PathSampler
from patchcreator.geometry.primitives import Bounds
from patchcreator.geometry.transform import Point


@dataclass(frozen=True)
class ComponentResult:
    """Geometry metadata emitted alongside a component's editable SVG."""

    bounds: Bounds | None = None
    anchors: Mapping[str, Point] = field(default_factory=dict)
    paths: Mapping[str, PathSampler] = field(default_factory=dict)


ComponentRenderer = Callable[[Any, Any], ComponentResult | None]


class UnsupportedComponentError(ValueError):
    pass


class ComponentRegistry:
    def __init__(self) -> None:
        self._renderers: dict[str, ComponentRenderer] = {}

    def register(self, component_type: str, renderer: ComponentRenderer) -> None:
        if component_type in self._renderers:
            raise ValueError(f"component type {component_type!r} is already registered")
        self._renderers[component_type] = renderer

    def renderer_for(self, component_type: str) -> ComponentRenderer:
        try:
            return self._renderers[component_type]
        except KeyError as exc:
            raise UnsupportedComponentError(
                f"unsupported component type {component_type!r}"
            ) from exc

    @property
    def component_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._renderers))
