"""Optional GUI support built on the normal PatchCreator document pipeline.

Importing this package does not require Qt. The reusable preview session stays
GUI-toolkit independent so tests and future front ends can share it.
"""

from .session import PreviewResult, PreviewSession, SceneTreeItem, scene_tree
from .source_edit import (
    PlacementState,
    SourceEditError,
    placement_state,
    set_element_position,
)

__all__ = [
    "PlacementState",
    "PreviewResult",
    "PreviewSession",
    "SceneTreeItem",
    "SourceEditError",
    "placement_state",
    "scene_tree",
    "set_element_position",
]
