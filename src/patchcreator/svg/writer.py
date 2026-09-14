"""Editable SVG writer and scene/component integration.

Components render geometry in their node-local coordinate systems, return scene
metadata, and are then placed in one shared pass before transforms and clips are
written to the SVG. This keeps the output hierarchy editable instead of
flattening document-space geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from patchcreator.components.registry import (
    ComponentFinalizeContext,
    ComponentFinalizer,
    ComponentRegistry,
    ComponentResult,
    UnsupportedComponentError,
)
from patchcreator.config.schema import DesignSpec, ElementSpec, PathPosition, RelativePosition
from patchcreator.geometry.patch import CanvasGeometry
from patchcreator.geometry.primitives import Bounds
from patchcreator.geometry.transform import AffineTransform
from patchcreator.scene.graph import SceneGraph
from patchcreator.scene.placement import PlacementResolver, ScenePathBinding

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)
ET.register_namespace("patchcreator", PATCHCREATOR_NS)


def q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _palette_colour(design: DesignSpec, name_or_colour: str) -> str:
    value = design.palette.get(name_or_colour, name_or_colour)
    if isinstance(value, str):
        return value
    raise ValueError(f"derived palette colour {name_or_colour!r} is not rendered yet")


@dataclass(frozen=True)
class RenderResult:
    svg: str
    warnings: tuple[str, ...]


@dataclass
class RenderContext:
    design: DesignSpec
    geometry: CanvasGeometry
    svg_root: ET.Element
    defs: ET.Element
    target_group: ET.Element


DeferredFinalizer = tuple[ComponentFinalizer, ElementSpec, RenderContext]


def _shape_element(
    parent: ET.Element,
    geometry: CanvasGeometry,
    *,
    inset: float = 0.0,
    **attrs: str,
) -> ET.Element:
    if geometry.shape == "circle":
        radius = geometry.width / 2.0 - inset
        if radius <= 0:
            raise ValueError("inset consumes the circular patch boundary")
        cx, cy = geometry.centre
        return ET.SubElement(
            parent,
            q(SVG_NS, "circle"),
            {"cx": _fmt(cx), "cy": _fmt(cy), "r": _fmt(radius), **attrs},
        )

    rx = geometry.width / 2.0 - inset
    ry = geometry.height / 2.0 - inset
    if rx <= 0 or ry <= 0:
        raise ValueError("inset consumes the elliptical patch boundary")
    cx, cy = geometry.centre
    return ET.SubElement(
        parent,
        q(SVG_NS, "ellipse"),
        {"cx": _fmt(cx), "cy": _fmt(cy), "rx": _fmt(rx), "ry": _fmt(ry), **attrs},
    )


def _shape_bounds(geometry: CanvasGeometry, inset: float = 0.0) -> Bounds:
    if geometry.width / 2.0 - inset <= 0 or geometry.height / 2.0 - inset <= 0:
        raise ValueError("inset consumes the patch boundary")
    return Bounds(inset, inset, geometry.width - inset, geometry.height - inset)


def _add_shape_clip(
    defs: ET.Element,
    clip_id: str,
    geometry: CanvasGeometry,
    *,
    inset: float,
    transform: AffineTransform | None = None,
) -> None:
    if defs.find(f"{{{SVG_NS}}}clipPath[@id='{clip_id}']") is not None:
        return
    clip = ET.SubElement(
        defs,
        q(SVG_NS, "clipPath"),
        {"id": clip_id, "clipPathUnits": "userSpaceOnUse"},
    )
    attrs: dict[str, str] = {}
    if transform is not None and transform != AffineTransform.identity():
        attrs["transform"] = transform.to_svg()
    _shape_element(clip, geometry, inset=inset, **attrs)


def _add_clip_paths(defs: ET.Element, geometry: CanvasGeometry) -> None:
    _add_shape_clip(defs, "clip-patch", geometry, inset=0.0)
    _add_shape_clip(defs, "clip-safe-area", geometry, inset=geometry.safe_margin)


def _effective_clip(element: ElementSpec, design: DesignSpec) -> tuple[str, bool, float]:
    clip = element.clip
    if clip is None:
        target = design.settings.default_clip
        enabled = True
        inset = 0.0
    else:
        target = clip.target
        enabled = clip.enabled
        inset = float(clip.inset)

    if target == "inherit":
        target = design.settings.default_clip
    if target == "inherit":
        raise ValueError("design default clip may not itself be 'inherit'")
    return target, enabled, inset


def _clip_id_for_element(
    element: ElementSpec,
    design: DesignSpec,
    geometry: CanvasGeometry,
    defs: ET.Element,
    graph: SceneGraph,
) -> str | None:
    target, enabled, inset = _effective_clip(element, design)
    if not enabled or target == "none":
        return None

    node = graph.find(element.id)
    world = node.world_transform
    world_inverse = world.inverse()
    transformed = world != AffineTransform.identity()

    if target == "patch":
        if inset == 0.0 and not transformed:
            return "clip-patch"
        clip_id = f"clip-element-{element.id}"
        _add_shape_clip(
            defs,
            clip_id,
            geometry,
            inset=inset,
            transform=world_inverse if transformed else None,
        )
        return clip_id

    if target in {"safe-area", "safe_area"}:
        if inset == 0.0 and not transformed:
            return "clip-safe-area"
        clip_id = f"clip-element-{element.id}"
        _add_shape_clip(
            defs,
            clip_id,
            geometry,
            inset=geometry.safe_margin + inset,
            transform=world_inverse if transformed else None,
        )
        return clip_id

    if target.startswith("custom:"):
        target_id = target.split(":", 1)[1]
        if not target_id:
            raise ValueError(f"empty custom clip target on element {element.id!r}")
        if target_id == element.id:
            raise ValueError(f"element {element.id!r} cannot clip itself")
        if target_id not in graph.by_id:
            raise ValueError(
                f"unknown custom clip target {target_id!r} on element {element.id!r}"
            )
        if inset != 0.0:
            raise ValueError(
                f"custom clip {target!r} on element {element.id!r} cannot use inset/outset yet; "
                "arbitrary-shape offsetting belongs to the geometry/boolean subsystem"
            )

        target_node = graph.find(target_id)
        if target_node.parent is None:
            raise ValueError(f"custom clip target {target_id!r} has no scene parent")

        relative = world_inverse @ target_node.parent.world_transform
        clip_id = f"clip-element-{element.id}"
        if defs.find(f"{{{SVG_NS}}}clipPath[@id='{clip_id}']") is None:
            clip = ET.SubElement(
                defs,
                q(SVG_NS, "clipPath"),
                {"id": clip_id, "clipPathUnits": "userSpaceOnUse"},
            )
            attrs = {"href": f"#{target_id}"}
            if relative != AffineTransform.identity():
                attrs["transform"] = relative.to_svg()
            ET.SubElement(clip, q(SVG_NS, "use"), attrs)
        return clip_id

    raise ValueError(f"unknown clip target {target!r} on element {element.id!r}")


def _render_border(element: ElementSpec, context: RenderContext) -> ComponentResult:
    cfg = element.component_config()
    stroke = cfg.get("stroke") or {}
    colour = _palette_colour(context.design, str(stroke.get("colour", "#000000")))
    width = float(stroke.get("width", 1.0))
    inset = float(cfg.get("inset", 0.0))
    _shape_element(
        context.target_group,
        context.geometry,
        inset=inset,
        fill="none",
        stroke=colour,
        **{"stroke-width": _fmt(width), "vector-effect": "non-scaling-stroke"},
    )
    return ComponentResult(bounds=_shape_bounds(context.geometry, inset))


def _render_group(element: ElementSpec, context: RenderContext) -> ComponentResult:
    return ComponentResult()


def _default_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register("border", _render_border)
    registry.register("group", _render_group)
    return registry


def _render_element(
    element: ElementSpec,
    group: ET.Element,
    base_context: RenderContext,
    registry: ComponentRegistry,
    graph: SceneGraph,
    svg_groups: dict[str, ET.Element],
    scene_paths: dict[str, ScenePathBinding],
    finalizers: list[DeferredFinalizer],
    unsupported: set[str],
    warnings: list[str],
    allow_unsupported: bool,
) -> None:
    attrs = {"id": element.id}
    if element.label and base_context.design.settings.inkscape_metadata:
        attrs[q(INKSCAPE_NS, "label")] = element.label
    attrs[q(PATCHCREATOR_NS, "component")] = element.type

    _, enabled, inset = _effective_clip(element, base_context.design)
    if element.clip is not None:
        attrs[q(PATCHCREATOR_NS, "clip-target")] = element.clip.target
        attrs[q(PATCHCREATOR_NS, "clip-enabled")] = str(enabled).lower()
        attrs[q(PATCHCREATOR_NS, "clip-inset-mm")] = _fmt(inset)

    element_group = ET.SubElement(group, q(SVG_NS, "g"), attrs)
    svg_groups[element.id] = element_group
    if not element.visible:
        element_group.set("style", "display:none")

    context = RenderContext(
        design=base_context.design,
        geometry=base_context.geometry,
        svg_root=base_context.svg_root,
        defs=base_context.defs,
        target_group=element_group,
    )

    try:
        renderer = registry.renderer_for(element.type)
    except UnsupportedComponentError:
        message = f"skipping unsupported component {element.id!r} of type {element.type!r}"
        if not allow_unsupported:
            raise UnsupportedComponentError(message)
        unsupported.add(element.id)
        warnings.append(message)
    else:
        result = renderer(element, context) or ComponentResult()
        warnings.extend(result.warnings)
        node = graph.find(element.id)
        node.set_geometry(result.bounds, anchors=dict(result.anchors))
        for path_id, sampler in result.paths.items():
            if path_id in scene_paths:
                raise ValueError(f"duplicate scene path id {path_id!r}")
            scene_paths[path_id] = ScenePathBinding(element.id, sampler)
        if result.finalize is not None:
            finalizers.append((result.finalize, element, context))

    for child in element.elements:
        _render_element(
            child,
            element_group,
            context,
            registry,
            graph,
            svg_groups,
            scene_paths,
            finalizers,
            unsupported,
            warnings,
            allow_unsupported,
        )


def _expand_partial_skip_set(
    graph: SceneGraph,
    scene_paths: dict[str, ScenePathBinding],
    unsupported: set[str],
    svg_groups: dict[str, ET.Element],
    warnings: list[str],
) -> set[str]:
    """Skip placement nodes whose dependencies were skipped in a partial render.

    Genuine missing references remain errors: propagation occurs only when a
    path/target corresponds to a node already known to have been skipped.
    """
    skipped = set(unsupported)
    reasons: dict[str, str] = {}

    changed = True
    while changed:
        changed = False
        for node in graph.root.walk():
            if node.id in skipped or not isinstance(node.config, ElementSpec):
                continue
            position = node.config.position
            reason: str | None = None
            if isinstance(position, RelativePosition) and position.target in skipped:
                reason = f"relative target {position.target!r} was skipped"
            elif (
                isinstance(position, PathPosition)
                and position.path not in scene_paths
                and position.path in skipped
            ):
                reason = f"path provider {position.path!r} was skipped"

            if reason is not None:
                skipped.add(node.id)
                reasons[node.id] = reason
                changed = True

    for node_id, reason in reasons.items():
        group = svg_groups.get(node_id)
        if group is not None:
            current_style = group.get("style", "").rstrip(";")
            group.set("style", f"{current_style + ';' if current_style else ''}display:none")
            group.set(q(PATCHCREATOR_NS, "skipped"), "placement-dependency")
        warnings.append(
            f"skipping placement-dependent component {node_id!r} in partial render: {reason}"
        )

    return skipped


def _run_finalizers(
    graph: SceneGraph,
    finalizers: list[DeferredFinalizer],
    skipped: set[str],
    warnings: list[str],
) -> None:
    skipped_node_ids = frozenset(skipped)
    for callback, element, render_context in finalizers:
        node = graph.find(element.id)
        before_bounds = node.local_bounds
        before_anchors = dict(node.local_anchors)
        produced = callback(
            ComponentFinalizeContext(
                element=element,
                render_context=render_context,
                graph=graph,
                scene_node=node,
                skipped_node_ids=skipped_node_ids,
            )
        )
        if node.local_bounds != before_bounds or node.local_anchors != before_anchors:
            raise ValueError(
                f"post-placement finalizer for {element.id!r} modified placement-critical geometry; "
                "return conservative bounds/anchors from the prepare phase instead"
            )
        if produced:
            warnings.extend(str(item) for item in produced)


def _apply_scene_transforms(graph: SceneGraph, svg_groups: dict[str, ET.Element]) -> None:
    identity = AffineTransform.identity()
    for node_id, group in svg_groups.items():
        node = graph.find(node_id)
        if node.local_transform != identity:
            group.set("transform", node.local_transform.to_svg())


def _apply_clips(
    design: DesignSpec,
    geometry: CanvasGeometry,
    defs: ET.Element,
    graph: SceneGraph,
    svg_groups: dict[str, ET.Element],
) -> None:
    for node in graph.root.walk():
        if not isinstance(node.config, ElementSpec):
            continue
        group = svg_groups[node.id]
        clip_id = _clip_id_for_element(
            node.config,
            design,
            geometry,
            defs,
            graph,
        )
        if clip_id:
            group.set("clip-path", f"url(#{clip_id})")


def render_design(
    design: DesignSpec,
    *,
    allow_unsupported: bool = False,
    registry: ComponentRegistry | None = None,
) -> RenderResult:
    geometry = CanvasGeometry.from_spec(design.canvas)
    graph = SceneGraph.from_design(design)

    root = ET.Element(
        q(SVG_NS, "svg"),
        {
            "width": f"{_fmt(geometry.width)}mm",
            "height": f"{_fmt(geometry.height)}mm",
            "viewBox": f"0 0 {_fmt(geometry.width)} {_fmt(geometry.height)}",
            q(PATCHCREATOR_NS, "design-version"): str(design.version),
        },
    )
    defs = ET.SubElement(root, q(SVG_NS, "defs"))
    _add_clip_paths(defs, geometry)

    if design.canvas.background:
        background = _palette_colour(design, design.canvas.background)
        background_group = ET.SubElement(
            root,
            q(SVG_NS, "g"),
            {"id": "__canvas_background__"},
        )
        if design.settings.inkscape_metadata:
            background_group.set(q(INKSCAPE_NS, "groupmode"), "layer")
            background_group.set(q(INKSCAPE_NS, "label"), "Canvas background")
        _shape_element(background_group, geometry, fill=background)

    warnings: list[str] = []
    registry = registry or _default_registry()
    base_context = RenderContext(design, geometry, root, defs, root)
    svg_groups: dict[str, ET.Element] = {}
    scene_paths: dict[str, ScenePathBinding] = {}
    finalizers: list[DeferredFinalizer] = []
    unsupported: set[str] = set()

    for layer in design.layers:
        layer_attrs = {"id": layer.id}
        if design.settings.inkscape_metadata:
            layer_attrs[q(INKSCAPE_NS, "groupmode")] = "layer"
            layer_attrs[q(INKSCAPE_NS, "label")] = layer.label or layer.id
        layer_group = ET.SubElement(root, q(SVG_NS, "g"), layer_attrs)
        svg_groups[layer.id] = layer_group
        if not layer.visible:
            layer_group.set("style", "display:none")
        for element in layer.elements:
            _render_element(
                element,
                layer_group,
                base_context,
                registry,
                graph,
                svg_groups,
                scene_paths,
                finalizers,
                unsupported,
                warnings,
                allow_unsupported,
            )

    skipped = _expand_partial_skip_set(
        graph,
        scene_paths,
        unsupported,
        svg_groups,
        warnings,
    )
    PlacementResolver(
        graph,
        geometry,
        paths=scene_paths,
        skip_node_ids=skipped,
    ).resolve()
    _run_finalizers(graph, finalizers, skipped, warnings)
    _apply_scene_transforms(graph, svg_groups)
    _apply_clips(design, geometry, defs, graph, svg_groups)

    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return RenderResult(svg=xml + "\n", warnings=tuple(warnings))


def write_design_svg(
    design: DesignSpec,
    output: str | Path,
    *,
    allow_unsupported: bool = False,
) -> RenderResult:
    result = render_design(design, allow_unsupported=allow_unsupported)
    Path(output).write_text(result.svg, encoding="utf-8")
    return result
