"""Procedural component registration.

The registry is intentionally small now, but its API is designed so Python
entry points can populate it later without adding type-switch statements to the
core renderer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


ComponentRenderer = Callable[[Any, Any], None]


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
