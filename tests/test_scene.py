import pytest

from patchcreator.config.loader import loads_design
from patchcreator.geometry import AffineTransform, Bounds
from patchcreator.scene import DuplicateNodeIdError, SceneGraph


def test_scene_graph_preserves_hierarchy_and_order():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
layers:
  - id: art
    elements:
      - id: group-a
        type: group
        elements:
          - id: child-a
            type: star
      - id: child-b
        type: star
"""
    )
    graph = SceneGraph.from_design(design)
    assert [node.id for node in graph.root.walk()] == ["__root__", "art", "group-a", "child-a", "child-b"]
    assert graph.find("child-a").parent is graph.find("group-a")
    assert graph.find("group-a").parent is graph.find("art")


def test_scene_graph_rejects_duplicate_ids():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
layers:
  - id: art
    elements:
      - id: duplicate
        type: star
      - id: duplicate
        type: star
"""
    )
    with pytest.raises(DuplicateNodeIdError):
        SceneGraph.from_design(design)


def test_scene_graph_rejects_reserved_root_id():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
layers:
  - id: art
    elements:
      - id: __root__
        type: star
"""
    )
    with pytest.raises(DuplicateNodeIdError, match="reserved"):
        SceneGraph.from_design(design)


def test_scene_resolution_combines_transforms_bounds_and_anchors():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
layers:
  - id: art
    elements:
      - id: group-a
        type: group
        elements:
          - id: child-a
            type: star
"""
    )
    graph = SceneGraph.from_design(design)
    graph.set_transform("group-a", AffineTransform.translation(10, 20))
    graph.set_transform("child-a", AffineTransform.translation(5, 0))
    graph.set_geometry(
        "child-a",
        Bounds(0, 0, 4, 2),
        anchors={"tip": (4, 1)},
    )

    graph.resolve()

    child = graph.find("child-a")
    group = graph.find("group-a")
    layer = graph.find("art")
    assert child.resolved_bounds == Bounds(15, 20, 19, 22)
    assert child.anchor("tip") == pytest.approx((19, 21))
    assert child.anchor("centre") == pytest.approx((17, 21))
    assert group.resolved_bounds == child.resolved_bounds
    assert layer.resolved_bounds == child.resolved_bounds
    assert graph.root.resolved_bounds == child.resolved_bounds
