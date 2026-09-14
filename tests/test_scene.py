import pytest

from patchcreator.config.loader import loads_design
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
