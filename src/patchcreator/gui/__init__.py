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
from .drag_edit import (
    CanvasSize,
    DragPosition,
    canvas_size,
    drag_position,
    set_drag_position,
    viewport_to_canvas,
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
    "CanvasSize",
    "ClipState",
    "DragPosition",
    "PlacementState",
    "PreviewResult",
    "PreviewSession",
    "SafeMarginState",
    "SceneTreeItem",
    "SourceEditError",
    "StarfieldSeedState",
    "canvas_size",
    "clip_state",
    "drag_position",
    "placement_state",
    "resolved_starfield_seed",
    "safe_margin_state",
    "scene_tree",
    "set_drag_position",
    "set_element_clip",
    "set_element_position",
    "set_safe_margin",
    "set_starfield_seed",
    "starfield_seed_state",
    "viewport_to_canvas",
]
