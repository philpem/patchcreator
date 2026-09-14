"""Artist-facing Cartesian, polar, anchor-relative and path placement."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import Mapping

from patchcreator.config.schema import (
    CartesianPosition,
    CoordinateFrameSpec,
    PathPosition,
    PolarPosition,
    RelativePosition,
)
from patchcreator.geometry.patch import CanvasGeometry
from patchcreator.geometry.paths import PathSampler
from patchcreator.geometry.transform import AffineTransform, Point
from patchcreator.geometry.units import (
    parse_angle_degrees,
    parse_length_mm,
    parse_radius,
    polar_to_cartesian,
)

from .graph import SceneGraph
from .node import SceneNode


class PlacementError(ValueError):
    pass


class PlacementCycleError(PlacementError):
    pass


@dataclass(frozen=True)
class PlacementFrame:
    """A coordinate frame in document space plus its polar reference radius."""

    to_world: AffineTransform
    reference_radius: float

    def __post_init__(self) -> None:
        if self.reference_radius <= 0:
            raise ValueError("coordinate-frame reference radius must be positive")


class PlacementResolver:
    """Resolve declarative positions into each scene node's local transform.

    The default frame is centred on the patch and uses the patch reference
    radius. Frames are inherited unchanged unless a layer/group explicitly
    overrides them. This makes nested organizational groups continue to use
    patch coordinates, while ``frame: {origin: self, ...}`` establishes a local
    frame that moves and rotates with a group.

    Path samplers supplied here operate in document coordinates. Future
    trajectory/orbit components can expose their generated paths through this
    same protocol without coupling placement to SVG path syntax.
    """

    def __init__(
        self,
        graph: SceneGraph,
        geometry: CanvasGeometry,
        *,
        paths: Mapping[str, PathSampler] | None = None,
    ) -> None:
        self.graph = graph
        self.geometry = geometry
        self.paths = dict(paths or {})
        self._state: dict[str, str] = {}
        self._stack: list[str] = []
        cx, cy = geometry.centre
        self._child_frames: dict[str, PlacementFrame] = {
            graph.root.id: PlacementFrame(
                AffineTransform.translation(cx, cy),
                geometry.reference_radius,
            )
        }
        graph.root.world_transform = AffineTransform.identity()
        self._state[graph.root.id] = "done"

    def resolve(self) -> SceneGraph:
        for node in self.graph.root.walk():
            if node is not self.graph.root:
                self._ensure_placed(node)

        # Re-run the generic scene pass to aggregate final bounds/anchors from
        # the local transforms established above.
        self.graph.resolve()
        return self.graph

    def _ensure_placed(self, node: SceneNode) -> None:
        state = self._state.get(node.id)
        if state == "done":
            return
        if state == "visiting":
            cycle_start = self._stack.index(node.id) if node.id in self._stack else 0
            cycle = self._stack[cycle_start:] + [node.id]
            raise PlacementCycleError(
                "placement dependency cycle: " + " -> ".join(cycle)
            )

        self._state[node.id] = "visiting"
        self._stack.append(node.id)
        try:
            parent = node.parent
            if parent is None:
                raise PlacementError(f"scene node {node.id!r} has no parent")
            if parent is not self.graph.root:
                self._ensure_placed(parent)

            try:
                inherited_frame = self._child_frames[parent.id]
            except KeyError as exc:
                raise PlacementError(
                    f"parent frame for scene node {node.id!r} has not been resolved"
                ) from exc

            parent_world = parent.world_transform
            position = getattr(node.config, "position", None)
            if position is not None:
                node.local_transform = self._position_transform(
                    node, position, inherited_frame, parent_world
                )

            node.world_transform = parent_world @ node.local_transform
            frame_spec = getattr(node.config, "frame", None)
            self._child_frames[node.id] = self._derive_child_frame(
                node, inherited_frame, frame_spec
            )
            self._state[node.id] = "done"
        finally:
            self._stack.pop()
            if self._state.get(node.id) == "visiting":
                self._state.pop(node.id, None)

    def _derive_child_frame(
        self,
        node: SceneNode,
        inherited: PlacementFrame,
        spec: CoordinateFrameSpec | None,
    ) -> PlacementFrame:
        if spec is None:
            return inherited

        reference_radius = inherited.reference_radius
        if spec.reference_radius is not None:
            reference_radius = parse_radius(
                spec.reference_radius, inherited.reference_radius
            )
            if reference_radius <= 0:
                raise PlacementError(
                    f"coordinate frame on {node.id!r} has a non-positive reference radius"
                )

        if spec.origin == "inherit":
            transform = inherited.to_world
        elif spec.origin == "self":
            transform = node.world_transform
        else:
            x = parse_length_mm(spec.origin[0])
            y = parse_length_mm(spec.origin[1])
            transform = node.world_transform @ AffineTransform.translation(x, y)

        return PlacementFrame(transform, reference_radius)

    def _position_transform(
        self,
        node: SceneNode,
        position: CartesianPosition | PolarPosition | RelativePosition | PathPosition,
        frame: PlacementFrame,
        parent_world: AffineTransform,
    ) -> AffineTransform:
        try:
            self_anchor = node.local_anchor(position.self_anchor)
        except KeyError as exc:
            raise PlacementError(
                f"cannot position {node.id!r}: {exc.args[0]}"
            ) from exc
        anchor_shift = AffineTransform.translation(-self_anchor[0], -self_anchor[1])

        if isinstance(position, CartesianPosition):
            x = parse_length_mm(position.x)
            y = parse_length_mm(position.y)
            desired_world = (
                frame.to_world
                @ AffineTransform.translation(x, y)
                @ anchor_shift
            )

        elif isinstance(position, PolarPosition):
            reference_radius = frame.reference_radius
            if position.reference_radius is not None:
                reference_radius = parse_radius(
                    position.reference_radius, frame.reference_radius
                )
                if reference_radius <= 0:
                    raise PlacementError(
                        f"polar position on {node.id!r} has a non-positive reference radius"
                    )
            radius = parse_radius(position.radius, reference_radius)
            angle = parse_angle_degrees(position.angle)
            x, y = polar_to_cartesian(radius, angle)
            desired_world = (
                frame.to_world
                @ AffineTransform.translation(x, y)
                @ anchor_shift
            )

        elif isinstance(position, RelativePosition):
            target = self.graph.find(position.target)
            self._ensure_placed(target)
            try:
                target_anchor = target.local_anchor(position.target_anchor)
            except KeyError as exc:
                raise PlacementError(
                    f"cannot position {node.id!r} relative to {target.id!r}: {exc.args[0]}"
                ) from exc
            world_target = target.world_transform.apply(target_anchor)
            offset = (
                parse_length_mm(position.offset[0]),
                parse_length_mm(position.offset[1]),
            )
            world_offset = frame.to_world.apply_vector(offset)
            point = (
                world_target[0] + world_offset[0],
                world_target[1] + world_offset[1],
            )
            desired_world = frame.to_world.with_translation(point) @ anchor_shift

        elif isinstance(position, PathPosition):
            try:
                path = self.paths[position.path]
            except KeyError as exc:
                raise PlacementError(
                    f"cannot position {node.id!r}: unknown path {position.path!r}"
                ) from exc
            fraction = _parse_path_fraction(position.at)
            try:
                sample = path.sample(fraction)
            except ValueError as exc:
                raise PlacementError(
                    f"cannot position {node.id!r} on path {position.path!r}: {exc}"
                ) from exc
            tx, ty = _unit_vector(sample.tangent, node.id, position.path)
            normal_offset = parse_length_mm(position.normal_offset)
            normal = (-ty, tx)  # positive is the visual right side in SVG y-down space
            point = (
                sample.point[0] + normal[0] * normal_offset,
                sample.point[1] + normal[1] * normal_offset,
            )
            if position.orient == "tangent":
                angle = degrees(atan2(ty, tx))
                basis = AffineTransform.rotation(angle).with_translation(point)
            else:
                basis = frame.to_world.with_translation(point)
            desired_world = basis @ anchor_shift

        else:  # pragma: no cover - Pydantic's discriminated union prevents this
            raise PlacementError(f"unsupported placement mode on {node.id!r}")

        try:
            return parent_world.inverse() @ desired_world
        except ValueError as exc:
            raise PlacementError(
                f"cannot position {node.id!r} beneath a singular parent transform"
            ) from exc


def _parse_path_fraction(value: float | str) -> float:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            fraction = float(text[:-1]) / 100.0
        else:
            fraction = float(text)
    else:
        fraction = float(value)
    if not 0.0 <= fraction <= 1.0:
        raise PlacementError("path position must be between 0 and 1 (or 0% and 100%)")
    return fraction


def _unit_vector(vector: Point, node_id: str, path_id: str) -> Point:
    x, y = vector
    length = hypot(x, y)
    if length <= 1e-12:
        raise PlacementError(
            f"cannot orient {node_id!r} on path {path_id!r}: tangent has zero length"
        )
    return x / length, y / length
