"""Optional GUI support built on the normal PatchCreator document pipeline.

Importing this package does not require Qt. The reusable preview session stays
GUI-toolkit independent so tests and future front ends can share it.
"""

from .session import (
    PreviewResult,
    PreviewSession,
    SceneTreeItem,
    resolved_starfield_seed,
    scene_tree,
)
from .source_edit import (
    PlacementState,
    SourceEditError,
    StarfieldSeedState,
    placement_state,
    set_element_position,
    set_starfield_seed,
    starfield_seed_state,
)

__all__ = [
    "PlacementState",
    "PreviewResult",
    "PreviewSession",
    "SceneTreeItem",
    "SourceEditError",
    "StarfieldSeedState",
    "placement_state",
    "resolved_starfield_seed",
    "scene_tree",
    "set_element_position",
    "set_starfield_seed",
    "starfield_seed_state",
]
