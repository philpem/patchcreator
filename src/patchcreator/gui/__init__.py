"""Optional GUI support built on the normal PatchCreator document pipeline.

Importing this package does not require Qt. The reusable preview session stays
GUI-toolkit independent so tests and future front ends can share it.
"""

from .clip_edit import (
    ClipState,
    SafeMarginState,
    clip_state,
    safe_margin_state,
    set_element_clip,
    set_safe_margin,
)
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
    "ClipState",
    "PlacementState",
    "PreviewResult",
    "PreviewSession",
    "SafeMarginState",
    "SceneTreeItem",
    "SourceEditError",
    "StarfieldSeedState",
    "clip_state",
    "placement_state",
    "resolved_starfield_seed",
    "safe_margin_state",
    "scene_tree",
    "set_element_clip",
    "set_element_position",
    "set_safe_margin",
    "set_starfield_seed",
    "starfield_seed_state",
]
