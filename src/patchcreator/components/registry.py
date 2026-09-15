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
from functools import wraps
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

    ``skipped_node_ids`` identifies nodes deliberately omitted from placement in
    a partial render, either because their component type is unsupported or
    because their placement depends on another skipped node/path. Finalizers may
    use this to degrade gracefully without masking genuine invalid geometry in
    strict renders.
    """

    element: Any
    render_context: Any
    graph: Any
    scene_node: Any
    skipped_node_ids: frozenset[str] = frozenset()


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
            # Delayed imports avoid module cycles: built-in component modules
            # use ComponentResult from this module. Third-party/test registries
            # can request an empty registry with include_builtins=False.
            from .assets import render_asset
            from .earth import render_earth
            from .stars import render_star, render_starfield
            from .text import render_text
            from .trajectories import render_orbit, render_trajectory

            self.register("asset", render_asset)
            self.register("earth", render_earth)
            self.register("orbit", render_orbit)
            self.register("star", render_star)
            self.register("starfield", render_starfield)
            self.register("text", render_text)
            self.register("trajectory", render_trajectory)

    def register(self, component_type: str, renderer: ComponentRenderer) -> None:
        if component_type in self._renderers:
            raise ValueError(f"component type {component_type!r} is already registered")
        self._renderers[component_type] = renderer

    def renderer_for(self, component_type: str) -> ComponentRenderer:
        try:
            renderer = self._renderers[component_type]
        except KeyError as exc:
            raise UnsupportedComponentError(
                f"unsupported component type {component_type!r}"
            ) from exc

        @wraps(renderer)
        def render_with_metadata(element: Any, context: Any) -> ComponentResult | None:
            # Keep the authoring overlap policy with the generated SVG so the
            # independent validator can still reason about it after an Inkscape
            # round-trip. A plain data-* attribute avoids coupling this registry
            # module to the SVG writer's namespace helpers.
            target_group = getattr(context, "target_group", None)
            overlap_policy = getattr(element, "overlap_policy", None)
            if target_group is not None and overlap_policy is not None:
                target_group.set("data-patchcreator-overlap-policy", str(overlap_policy))
            return renderer(element, context)

        return render_with_metadata

    @property
    def component_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._renderers))
