import pytest

from patchcreator.config.loader import loads_design
from patchcreator.geometry import Bounds, CanvasGeometry, LinePath
from patchcreator.scene import PlacementCycleError, PlacementResolver, SceneGraph


def _graph(yaml_text: str) -> tuple[SceneGraph, CanvasGeometry]:
    design = loads_design(yaml_text)
    return SceneGraph.from_design(design), CanvasGeometry.from_spec(design.canvas)


def test_cartesian_position_is_relative_to_patch_centre():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: marker
        type: star
        position:
          mode: cartesian
          x: 10mm
          y: -5
"""
    )
    graph.set_geometry("marker", Bounds(-1, -1, 1, 1))
    PlacementResolver(graph, geometry).resolve()

    assert graph.find("marker").anchor("centre") == pytest.approx((50, 35))
    assert graph.find("marker").resolved_bounds == Bounds(49, 34, 51, 36)


def test_polar_position_uses_patch_radius_and_clockwise_angles():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: north
        type: star
        position: {mode: polar, angle: 0deg, radius: 0.5r}
      - id: east
        type: star
        position: {mode: polar, angle: 90deg, radius: 0.5r}
"""
    )
    for node_id in ("north", "east"):
        graph.set_geometry(node_id, Bounds(-1, -1, 1, 1))
    PlacementResolver(graph, geometry).resolve()

    assert graph.find("north").anchor("centre") == pytest.approx((40, 20))
    assert graph.find("east").anchor("centre") == pytest.approx((60, 40))


def test_group_can_establish_local_polar_frame():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: constellation
        type: group
        position:
          mode: cartesian
          x: 10
          y: 0
          self_anchor: origin
        frame:
          origin: self
          reference_radius: 5
        elements:
          - id: star
            type: star
            position:
              mode: polar
              angle: 90deg
              radius: 1r
"""
    )
    graph.set_geometry("star", Bounds(-0.5, -0.5, 0.5, 0.5))
    PlacementResolver(graph, geometry).resolve()

    assert graph.find("constellation").anchor("origin") == pytest.approx((50, 40))
    assert graph.find("star").anchor("centre") == pytest.approx((55, 40))


def test_relative_position_aligns_named_anchors():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: first
        type: box
        position: {mode: cartesian, x: -10, y: 0}
      - id: second
        type: box
        position:
          mode: relative
          target: first
          target_anchor: right
          self_anchor: left
          offset: [1mm, 0]
"""
    )
    graph.set_geometry("first", Bounds(-2, -1, 2, 1))
    graph.set_geometry("second", Bounds(-1, -1, 1, 1))
    PlacementResolver(graph, geometry).resolve()

    assert graph.find("first").anchor("right") == pytest.approx((32, 40))
    assert graph.find("second").anchor("left") == pytest.approx((33, 40))
    assert graph.find("second").anchor("centre") == pytest.approx((34, 40))


def test_path_position_supports_fraction_normal_offset_and_tangent_orientation():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: marker
        type: star
        position:
          mode: path
          path: trajectory
          at: 50%
          orient: tangent
          normal_offset: 2
"""
    )
    graph.set_geometry("marker", Bounds(-1, -0.5, 1, 0.5))
    path = LinePath((20, 20), (20, 60))
    PlacementResolver(graph, geometry, paths={"trajectory": path}).resolve()

    marker = graph.find("marker")
    assert marker.anchor("centre") == pytest.approx((18, 40))
    assert marker.world_transform.apply((1, 0)) == pytest.approx((18, 41))


def test_relative_placement_cycles_are_reported():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: a
        type: star
        position: {mode: relative, target: b}
      - id: b
        type: star
        position: {mode: relative, target: a}
"""
    )
    graph.set_geometry("a", Bounds(-1, -1, 1, 1))
    graph.set_geometry("b", Bounds(-1, -1, 1, 1))

    with pytest.raises(PlacementCycleError, match="a -> b -> a"):
        PlacementResolver(graph, geometry).resolve()


def test_layer_can_override_only_reference_radius_while_inheriting_origin():
    graph, geometry = _graph(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    frame:
      reference_radius: 10
    elements:
      - id: star
        type: star
        position: {mode: polar, angle: 180deg, radius: 0.5r}
"""
    )
    graph.set_geometry("star", Bounds(-1, -1, 1, 1))
    PlacementResolver(graph, geometry).resolve()

    assert graph.find("star").anchor("centre") == pytest.approx((40, 45))
