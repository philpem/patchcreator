import xml.etree.ElementTree as ET

from patchcreator.components import ComponentRegistry, ComponentResult
from patchcreator.config.loader import loads_design
from patchcreator.geometry import Bounds, LinePath
from patchcreator.svg.writer import SVG_NS, render_design


def _marker_renderer(element, context):
    radius = float(element.component_config().get("radius", 1.0))
    ET.SubElement(
        context.target_group,
        f"{{{SVG_NS}}}circle",
        {"cx": "0", "cy": "0", "r": str(radius)},
    )
    return ComponentResult(
        bounds=Bounds(-radius, -radius, radius, radius),
        anchors={"pin": (radius, 0.0)},
    )


def _line_renderer(element, context):
    ET.SubElement(
        context.target_group,
        f"{{{SVG_NS}}}line",
        {"x1": "0", "y1": "0", "x2": "10", "y2": "0"},
    )
    return ComponentResult(
        bounds=Bounds(0, -0.1, 10, 0.1),
        paths={element.id: LinePath((0, 0), (10, 0))},
    )


def _group_renderer(element, context):
    return ComponentResult()


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register("marker", _marker_renderer)
    registry.register("line", _line_renderer)
    registry.register("group", _group_renderer)
    return registry


def _group(root, node_id):
    return root.find(f".//{{{SVG_NS}}}g[@id='{node_id}']")


def test_cartesian_and_polar_placement_are_written_as_editable_group_transforms():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: cart
        type: marker
        clip: {target: none}
        position: {mode: cartesian, x: 10, y: -5}
      - id: polar
        type: marker
        clip: {target: none}
        position: {mode: polar, angle: 90deg, radius: 0.5r}
"""
    )
    root = ET.fromstring(render_design(design, registry=_registry()).svg)
    assert _group(root, "cart").attrib["transform"] == "matrix(1 0 0 1 50 35)"
    assert _group(root, "polar").attrib["transform"] == "matrix(1 0 0 1 60 40)"


def test_nested_group_writes_local_not_world_child_transform():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: constellation
        type: group
        clip: {target: none}
        position:
          mode: cartesian
          x: 10
          y: 0
          self_anchor: origin
        frame: {origin: self, reference_radius: 5}
        elements:
          - id: star
            type: marker
            clip: {target: none}
            position: {mode: polar, angle: 90deg, radius: 1r}
"""
    )
    root = ET.fromstring(render_design(design, registry=_registry()).svg)
    assert _group(root, "constellation").attrib["transform"] == "matrix(1 0 0 1 50 40)"
    assert _group(root, "star").attrib["transform"] == "matrix(1 0 0 1 5 0)"


def test_relative_anchor_placement_uses_component_geometry():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: first
        type: marker
        radius: 2
        clip: {target: none}
        position: {mode: cartesian, x: -10, y: 0}
      - id: second
        type: marker
        clip: {target: none}
        position:
          mode: relative
          target: first
          target_anchor: right
          self_anchor: left
          offset: [1, 0]
"""
    )
    root = ET.fromstring(render_design(design, registry=_registry()).svg)
    assert _group(root, "first").attrib["transform"] == "matrix(1 0 0 1 30 40)"
    assert _group(root, "second").attrib["transform"] == "matrix(1 0 0 1 34 40)"


def test_component_local_path_is_transformed_with_its_owner_before_path_placement():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: trajectory
        type: line
        clip: {target: none}
        position:
          mode: cartesian
          x: -10
          y: 0
          self_anchor: origin
      - id: marker
        type: marker
        clip: {target: none}
        position:
          mode: path
          path: trajectory
          at: 100%
          orient: tangent
"""
    )
    root = ET.fromstring(render_design(design, registry=_registry()).svg)
    assert _group(root, "trajectory").attrib["transform"] == "matrix(1 0 0 1 30 40)"
    assert _group(root, "marker").attrib["transform"] == "matrix(1 0 0 1 40 40)"


def test_global_safe_area_clip_is_compensated_for_placed_node_transform():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin: {fixed: 3}
settings: {default_clip: safe-area}
layers:
  - id: art
    elements:
      - id: marker
        type: marker
        position: {mode: cartesian, x: 10, y: 0}
"""
    )
    root = ET.fromstring(render_design(design, registry=_registry()).svg)
    group = _group(root, "marker")
    assert group.attrib["transform"] == "matrix(1 0 0 1 50 40)"
    assert group.attrib["clip-path"] == "url(#clip-element-marker)"
    circle = root.find(
        f".//{{{SVG_NS}}}clipPath[@id='clip-element-marker']/{{{SVG_NS}}}circle"
    )
    assert circle is not None
    assert circle.attrib["r"] == "37"
    assert circle.attrib["transform"] == "matrix(1 0 0 1 -50 -40)"


def test_allow_unsupported_skips_unresolvable_placement_but_keeps_partial_svg():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: future-earth
        type: earth
        position: {mode: cartesian, x: 0, y: 15}
"""
    )
    result = render_design(design, registry=_registry(), allow_unsupported=True)
    root = ET.fromstring(result.svg)
    group = _group(root, "future-earth")
    assert result.warnings
    assert group is not None
    assert "transform" not in group.attrib
