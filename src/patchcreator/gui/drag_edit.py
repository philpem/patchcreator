"""GUI-independent coordinate mapping and drag-placement source edits."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from patchcreator.config.loader import DesignLoadError, loads_design

from .source_edit import SourceEditError, _load, set_element_position


@dataclass(frozen=True)
class CanvasSize:
    width: float
    height: float

    @property
    def centre(self) -> tuple[float, float]:
        return self.width / 2.0, self.height / 2.0


@dataclass(frozen=True)
class DragPosition:
    element_id: str
    mode: str
    first: float
    second: float


def canvas_size(text: str) -> CanvasSize:
    """Return the physical SVG canvas dimensions in millimetres."""

    try:
        design = loads_design(text)
    except DesignLoadError as exc:
        raise SourceEditError(f"cannot drag in invalid design: {exc}") from exc
    canvas = design.canvas
    if canvas.shape == "circle":
        assert canvas.diameter is not None
        return CanvasSize(float(canvas.diameter), float(canvas.diameter))
    assert canvas.width is not None and canvas.height is not None
    return CanvasSize(float(canvas.width), float(canvas.height))


def viewport_to_canvas(
    x: float,
    y: float,
    *,
    viewport_width: float,
    viewport_height: float,
    canvas_width: float,
    canvas_height: float,
) -> tuple[float, float] | None:
    """Map preview-widget coordinates to SVG canvas coordinates.

    DragSvgWidget explicitly enables Qt's KeepAspectRatio behaviour, so the
    rendered artwork may be letterboxed inside the
    widget. Points in that letterboxing return None instead of being
    extrapolated outside the artwork.
    """

    values = (viewport_width, viewport_height, canvas_width, canvas_height)
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("viewport and canvas dimensions must be finite and positive")
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("pointer coordinates must be finite")

    scale = min(viewport_width / canvas_width, viewport_height / canvas_height)
    rendered_width = canvas_width * scale
    rendered_height = canvas_height * scale
    offset_x = (viewport_width - rendered_width) / 2.0
    offset_y = (viewport_height - rendered_height) / 2.0

    if (
        x < offset_x
        or y < offset_y
        or x > offset_x + rendered_width
        or y > offset_y + rendered_height
    ):
        return None

    return (x - offset_x) / scale, (y - offset_y) / scale


def _iter_contexts(root: CommentedMap):
    layers = root.get("layers")
    if not isinstance(layers, CommentedSeq):
        return

    def walk(elements: object, ancestors: tuple[CommentedMap, ...], layer: CommentedMap):
        if not isinstance(elements, CommentedSeq):
            return
        for element in elements:
            if not isinstance(element, CommentedMap):
                continue
            yield element, layer, ancestors
            yield from walk(element.get("elements"), ancestors + (element,), layer)

    for layer in layers:
        if not isinstance(layer, CommentedMap):
            continue
        yield from walk(layer.get("elements"), (), layer)


def _find_context(
    root: CommentedMap,
    element_id: str,
) -> tuple[CommentedMap, CommentedMap, tuple[CommentedMap, ...]]:
    matches = [
        (element, layer, ancestors)
        for element, layer, ancestors in _iter_contexts(root)
        if element.get("id") == element_id
    ]
    if not matches:
        raise SourceEditError(f"element {element_id!r} does not exist in the current YAML source")
    if len(matches) > 1:
        raise SourceEditError(f"element id {element_id!r} is duplicated in the current YAML source")
    return matches[0]


def _frame_changes_default(raw: object, *, owner: str) -> bool:
    if raw is None:
        return False
    if not isinstance(raw, CommentedMap):
        raise SourceEditError(f"{owner} frame must be a YAML mapping")
    origin = raw.get("origin", "inherit")
    reference_radius = raw.get("reference_radius")
    return origin != "inherit" or reference_radius is not None


def _drag_mode(
    root: CommentedMap,
    element_id: str,
) -> str:
    element, layer, ancestors = _find_context(root, element_id)

    if _frame_changes_default(layer.get("frame"), owner=f"layer {layer.get('id')!r}"):
        raise SourceEditError(
            f"element {element_id!r} uses a non-default ancestor coordinate frame; "
            "drag placement is not supported yet"
        )
    for ancestor in ancestors:
        if _frame_changes_default(
            ancestor.get("frame"),
            owner=f"element {ancestor.get('id')!r}",
        ):
            raise SourceEditError(
                f"element {element_id!r} uses a non-default ancestor coordinate frame; "
                "drag placement is not supported yet"
            )

    position = element.get("position")
    if position is None:
        return "cartesian"
    if not isinstance(position, CommentedMap):
        raise SourceEditError(f"element {element_id!r} has a non-mapping position")
    mode = position.get("mode")
    if mode in {"cartesian", "polar"}:
        return str(mode)
    raise SourceEditError(
        f"element {element_id!r} uses position mode {mode!r}; "
        "drag placement currently supports only default/cartesian/polar positions"
    )


def drag_position(
    text: str,
    element_id: str,
    *,
    canvas_x: float,
    canvas_y: float,
) -> DragPosition:
    """Calculate the YAML placement represented by one canvas-space pointer."""

    if not math.isfinite(canvas_x) or not math.isfinite(canvas_y):
        raise SourceEditError("drag coordinates must be finite")

    _, root = _load(text)
    mode = _drag_mode(root, element_id)
    size = canvas_size(text)
    cx, cy = size.centre
    dx = float(canvas_x) - cx
    dy = float(canvas_y) - cy

    if abs(dx) < 1e-12:
        dx = 0.0
    if abs(dy) < 1e-12:
        dy = 0.0

    if mode == "cartesian":
        return DragPosition(element_id, mode, dx, dy)

    radius = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dx, -dy)) % 360.0
    if abs(angle - 360.0) < 1e-12 or abs(angle) < 1e-12:
        angle = 0.0
    if abs(radius) < 1e-12:
        radius = 0.0
    return DragPosition(element_id, mode, angle, radius)


def set_drag_position(
    text: str,
    element_id: str,
    *,
    canvas_x: float,
    canvas_y: float,
) -> str:
    """Move one element to a canvas-space point via its editable placement mode."""

    position = drag_position(
        text,
        element_id,
        canvas_x=canvas_x,
        canvas_y=canvas_y,
    )
    return set_element_position(
        text,
        element_id,
        mode=position.mode,  # type: ignore[arg-type]
        first=str(position.first),
        second=str(position.second),
    )
