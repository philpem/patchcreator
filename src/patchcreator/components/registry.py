"""Procedural component registration and render metadata.

The registry remains deliberately small and extensible. Component renderers
write their geometry in the node's local SVG coordinate system and return the
bounds/anchors/path samplers needed by the scene and placement passes.

Components whose final SVG depends on resolved scene geometry may also return a
post-placement finalizer. The prepare-time bounds/anchors remain authoritative
for placement; finalizers are deliberately unable to replace them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from patchcreator.geometry.paths import PathSampler
from patchcreator.geometry.primitives import Bounds
from patchcreator.geometry.transform import Point


@dataclass(frozen=True)
class ComponentFinalizeContext:
    """Context supplied to a component after scene placement is resolved.

    Fields are typed loosely here to keep the component registry independent of
    the SVG writer and scene modules. Components can inspect ``graph`` and
    ``scene_node`` and append final editable geometry to
    ``render_context.target_group``.
    """

    element: Any
    render_context: Any
    graph: Any
    scene_node: Any


ComponentFinalizer = Callable[[ComponentFinalizeContext], Iterable[str] | None]


@dataclass(frozen=True)
class ComponentResult:
    """Geometry metadata emitted alongside a component's editable SVG."""

    bounds: Bounds | None = None
    anchors: Mapping[str, Point] = field(default_factory=dict)
    paths: Mapping[str, PathSampler] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    finalize: ComponentFinalizer | None = None


ComponentRenderer = Callable[[Any, Any], ComponentResult | None]


class UnsupportedComponentError(ValueError):
    pass


class ComponentRegistry:
    def __init__(self, *, include_builtins: bool = True) -> None:
        self._renderers: dict[str, ComponentRenderer] = {}
        if include_builtins:
            # Delayed import avoids a module cycle: built-in component modules
            # use ComponentResult from this module. Third-party/test registries
            # can request an empty registry with include_builtins=False.
            from .stars import render_star, render_starfield

            self.register("star", render_star)
            self.register("starfield", render_starfield)

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
