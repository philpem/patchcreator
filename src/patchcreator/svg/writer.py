"""Editable SVG writer for the initial PatchCreator core.

Only core canvas/background/border rendering is implemented here. Other
procedural component types are intentionally dispatched through the registry as
they are added, rather than accumulating a monolithic type switch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from patchcreator.components.registry import ComponentRegistry, UnsupportedComponentError
from patchcreator.config.schema import DesignSpec, ElementSpec
from patchcreator.geometry.patch import CanvasGeometry
from patchcreator.scene.graph import SceneGraph

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
    # Derived-colour calculation belongs in the palette subsystem. Fail
    # explicitly for now rather than silently emitting a wrong colour.
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


def _shape_element(parent: ET.Element, geometry: CanvasGeometry, *, inset: float = 0.0, **attrs: str) -> ET.Element:
    if geometry.shape == "circle":
        radius = geometry.width / 2.0 - inset
        if radius <= 0:
            raise ValueError("inset consumes the circular patch boundary")
        cx, cy = geometry.centre
        return ET.SubElement(parent, q(SVG_NS, "circle"), {"cx": _fmt(cx), "cy": _fmt(cy), "r": _fmt(radius), **attrs})

    rx = geometry.width / 2.0 - inset
    ry = geometry.height / 2.0 - inset
    if rx <= 0 or ry <= 0:
        raise ValueError("inset consumes the elliptical patch boundary")
    cx, cy = geometry.centre
    return ET.SubElement(parent, q(SVG_NS, "ellipse"), {"cx": _fmt(cx), "cy": _fmt(cy), "rx": _fmt(rx), "ry": _fmt(ry), **attrs})


def _add_clip_paths(defs: ET.Element, geometry: CanvasGeometry) -> None:
    patch_clip = ET.SubElement(defs, q(SVG_NS, "clipPath"), {"id": "clip-patch", "clipPathUnits": "userSpaceOnUse"})
    _shape_element(patch_clip, geometry)

    safe_clip = ET.SubElement(defs, q(SVG_NS, "clipPath"), {"id": "clip-safe-area", "clipPathUnits": "userSpaceOnUse"})
    _shape_element(safe_clip, geometry, inset=geometry.safe_margin)


def _clip_target(element: ElementSpec, design: DesignSpec) -> str | None:
    clip = element.clip
    if clip is not None:
        if not clip.enabled:
            return None
        target = clip.target
    else:
        target = design.settings.default_clip

    if target == "inherit":
        target = design.settings.default_clip
    if target == "none":
        return None
    if target == "patch":
        return "clip-patch"
    if target in {"safe-area", "safe_area"}:
        return "clip-safe-area"
    if target.startswith("custom:"):
        return f"clip-{target.split(':', 1)[1]}"
    raise ValueError(f"unknown clip target {target!r} on element {element.id!r}")


def _render_border(element: ElementSpec, context: RenderContext) -> None:
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


def _default_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register("border", _render_border)
    return registry


def _render_element(
    element: ElementSpec,
    group: ET.Element,
    base_context: RenderContext,
    registry: ComponentRegistry,
    warnings: list[str],
    allow_unsupported: bool,
) -> None:
    attrs = {"id": element.id}
    if element.label and base_context.design.settings.inkscape_metadata:
        attrs[q(INKSCAPE_NS, "label")] = element.label
    attrs[q(PATCHCREATOR_NS, "component")] = element.type

    clip_target = _clip_target(element, base_context.design)
    if element.clip is not None:
        attrs[q(PATCHCREATOR_NS, "clip-target")] = element.clip.target
        attrs[q(PATCHCREATOR_NS, "clip-enabled")] = str(element.clip.enabled).lower()
    if clip_target:
        attrs["clip-path"] = f"url(#{clip_target})"

    element_group = ET.SubElement(group, q(SVG_NS, "g"), attrs)
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
        warnings.append(message)
    else:
        renderer(element, context)

    for child in element.elements:
        _render_element(child, element_group, context, registry, warnings, allow_unsupported)


def render_design(
    design: DesignSpec,
    *,
    allow_unsupported: bool = False,
    registry: ComponentRegistry | None = None,
) -> RenderResult:
    geometry = CanvasGeometry.from_spec(design.canvas)
    SceneGraph.from_design(design)  # validates IDs before output begins

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
        background_group = ET.SubElement(root, q(SVG_NS, "g"), {"id": "__canvas_background__"})
        if design.settings.inkscape_metadata:
            background_group.set(q(INKSCAPE_NS, "groupmode"), "layer")
            background_group.set(q(INKSCAPE_NS, "label"), "Canvas background")
        _shape_element(background_group, geometry, fill=background)

    warnings: list[str] = []
    registry = registry or _default_registry()
    base_context = RenderContext(design, geometry, root, defs, root)

    for layer in design.layers:
        layer_attrs = {"id": layer.id}
        if design.settings.inkscape_metadata:
            layer_attrs[q(INKSCAPE_NS, "groupmode")] = "layer"
            layer_attrs[q(INKSCAPE_NS, "label")] = layer.label or layer.id
        layer_group = ET.SubElement(root, q(SVG_NS, "g"), layer_attrs)
        if not layer.visible:
            layer_group.set("style", "display:none")
        for element in layer.elements:
            _render_element(element, layer_group, base_context, registry, warnings, allow_unsupported)

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
