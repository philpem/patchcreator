from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from patchcreator.components import ComponentRegistry
from patchcreator.components.registry import ComponentResult
from patchcreator.config.loader import loads_design
from patchcreator.geometry import Bounds
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design
from patchcreator.validation.geometry import _path_fill_geometry, polygon_components


def _shape_renderer(element, context):
    config = element.component_config()
    kind = config.get("kind", "rect")
    if kind == "rect":
        ET.SubElement(
            context.target_group,
            f"{{{SVG_NS}}}rect",
            {"x": "-5", "y": "-5", "width": "10", "height": "10", "fill": "#fff"},
        )
        return ComponentResult(bounds=Bounds(-5, -5, 5, 5))
    if kind == "concave":
        ET.SubElement(
            context.target_group,
            f"{{{SVG_NS}}}polygon",
            {
                "points": "-6,-6 6,-6 6,-2 1,-2 1,6 -6,6",
                "fill": "#fff",
            },
        )
        return ComponentResult(bounds=Bounds(-6, -6, 6, 6))
    if kind == "multipart":
        ET.SubElement(
            context.target_group,
            f"{{{SVG_NS}}}rect",
            {"x": "-6", "y": "-2", "width": "4", "height": "4", "fill": "#fff"},
        )
        ET.SubElement(
            context.target_group,
            f"{{{SVG_NS}}}rect",
            {"x": "2", "y": "-2", "width": "4", "height": "4", "fill": "#fff"},
        )
        return ComponentResult(bounds=Bounds(-6, -2, 6, 2))
    if kind == "text":
        node = ET.SubElement(context.target_group, f"{{{SVG_NS}}}text", {"x": "0", "y": "0"})
        node.text = "NOT OFFSETTABLE"
        return ComponentResult(bounds=Bounds(-5, -2, 5, 2))
    raise ValueError(kind)


def _registry():
    registry = ComponentRegistry()
    registry.register("test-shape", _shape_renderer)
    return registry


def _render(target_kind: str, inset: float, *, target_x: float = 0, clipped_x: float = 0):
    design = loads_design(
        f"""
version: 0.1
canvas: {{shape: circle, diameter: 80}}
settings: {{default_clip: none}}
layers:
  - id: art
    elements:
      - id: mask-shape
        type: test-shape
        kind: {target_kind}
        position: {{mode: cartesian, x: {target_x}, y: 0}}
        clip: {{target: none}}
      - id: clipped
        type: star
        glyph: dot
        size: 30
        position: {{mode: cartesian, x: {clipped_x}, y: 0}}
        clip:
          target: custom:mask-shape
          inset: {inset}
"""
    )
    return ET.fromstring(render_design(design, registry=_registry()).svg)


def _derived_path(root: ET.Element):
    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-element-clipped']")
    assert clip is not None
    path = clip.find(f"{{{SVG_NS}}}path")
    assert path is not None
    return clip, path


def test_positive_custom_inset_offsets_rectangle_inward_by_mm():
    root = _render("rect", 1.0)
    clip, path = _derived_path(root)
    geometry = _path_fill_geometry(path.attrib["d"], fill_rule="evenodd")

    assert geometry.bounds == pytest.approx((-4.0, -4.0, 4.0, 4.0))
    assert clip.attrib[f"{{{PATCHCREATOR_NS}}}derived-from"] == "mask-shape"
    assert clip.attrib[f"{{{PATCHCREATOR_NS}}}clip-offset-mm"] == "1"
    assert path.attrib["clip-rule"] == "evenodd"


def test_negative_custom_inset_is_physical_outset():
    root = _render("rect", -1.5)
    _, path = _derived_path(root)
    geometry = _path_fill_geometry(path.attrib["d"], fill_rule="evenodd")
    assert geometry.bounds == pytest.approx((-6.5, -6.5, 6.5, 6.5))


def test_concave_custom_clip_uses_real_polygon_offset_not_bbox_scaling():
    root = _render("concave", 1.0)
    _, path = _derived_path(root)
    geometry = _path_fill_geometry(path.attrib["d"], fill_rule="evenodd")

    assert geometry.bounds == pytest.approx((-5.0, -5.0, 5.0, 5.0))
    # An inset L shape remains substantially smaller than its 10x10 bounding
    # box; bbox scaling would incorrectly turn it into a rectangle.
    assert geometry.area < 75.0
    assert geometry.area > 40.0


def test_multipart_outset_preserves_disconnected_components_when_they_do_not_meet():
    root = _render("multipart", -0.75)
    _, path = _derived_path(root)
    geometry = _path_fill_geometry(path.attrib["d"], fill_rule="evenodd")

    assert len(polygon_components(geometry)) == 2
    assert geometry.bounds == pytest.approx((-6.75, -2.75, 6.75, 2.75))


def test_offset_clip_tracks_target_and_clipped_element_coordinate_frames():
    root = _render("rect", 1.0, target_x=12, clipped_x=-7)
    _, path = _derived_path(root)
    transform = path.attrib.get("transform")
    assert transform is not None
    # Both objects share the same parent frame, so the target is 19 mm to the
    # right of the clipped object's local coordinate system.
    assert transform == "matrix(1 0 0 1 19 0)"


def test_zero_offset_custom_clip_remains_reversible_use_reference():
    root = _render("rect", 0.0)
    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-element-clipped']")
    assert clip is not None
    use = clip.find(f"{{{SVG_NS}}}use")
    assert use is not None
    assert use.attrib["href"] == "#mask-shape"
    assert clip.find(f"{{{SVG_NS}}}path") is None


def test_offset_refuses_visible_geometry_that_cannot_be_reconstructed_safely():
    with pytest.raises(ValueError, match="visible <text>"):
        _render("text", 1.0)


def test_inset_that_consumes_target_fails_explicitly():
    with pytest.raises(ValueError, match="consumes the entire clipping silhouette"):
        _render("rect", 6.0)
