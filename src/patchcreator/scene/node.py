from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from patchcreator.geometry.primitives import Bounds
from patchcreator.geometry.transform import AffineTransform, Point


@dataclass
class SceneNode:
    id: str
    kind: str
    label: str | None = None
    visible: bool = True
    config: Any = None
    children: list["SceneNode"] = field(default_factory=list)
    local_transform: AffineTransform = field(default_factory=AffineTransform.identity)
    local_bounds: Bounds | None = None
    local_anchors: dict[str, Point] = field(default_factory=dict)
    parent: "SceneNode | None" = field(default=None, init=False, repr=False)
    world_transform: AffineTransform = field(
        default_factory=AffineTransform.identity, init=False
    )
    resolved_bounds: Bounds | None = field(default=None, init=False)
    resolved_anchors: dict[str, Point] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for child in self.children:
            self._adopt(child)

    def _adopt(self, child: "SceneNode") -> None:
        if child is self:
            raise ValueError("a scene node cannot be its own child")
        if child.parent is not None and child.parent is not self:
            raise ValueError(
                f"scene node {child.id!r} already belongs to {child.parent.id!r}"
            )
        child.parent = self

    def add_child(self, child: "SceneNode") -> None:
        self._adopt(child)
        self.children.append(child)

    def walk(self) -> Iterator["SceneNode"]:
        """Walk the hierarchy in SVG/visual paint order."""
        yield self
        for child in self.children:
            yield from child.walk()

    def set_geometry(
        self,
        bounds: Bounds | None,
        *,
        anchors: dict[str, Point] | None = None,
    ) -> None:
        """Attach component geometry expressed in this node's local space."""
        self.local_bounds = bounds
        self.local_anchors = dict(anchors or {})

    def local_anchor(self, name: str) -> Point:
        """Return an anchor in this node's untransformed local space.

        Explicit component anchors take precedence over bounds-derived anchors.
        ``origin`` is always available, which is especially useful when
        positioning geometry-less groups that establish a child coordinate
        frame.
        """
        if name in self.local_anchors:
            return self.local_anchors[name]
        if name == "origin":
            return (0.0, 0.0)
        if self.local_bounds is not None:
            try:
                return self.local_bounds.anchor(name)
            except KeyError:
                pass
        raise KeyError(f"scene node {self.id!r} has no local anchor {name!r}")

    def resolve(self, parent_transform: AffineTransform | None = None) -> Bounds | None:
        """Resolve world transform, world bounds and anchors recursively.

        Procedural components populate ``local_bounds`` and ``local_anchors``.
        Placement code populates ``local_transform``. Resolution combines those
        values through the hierarchy and aggregates group/layer bounds from
        their children.
        """
        parent_transform = parent_transform or AffineTransform.identity()
        self.world_transform = parent_transform @ self.local_transform

        own_bounds = (
            self.local_bounds.transformed(self.world_transform)
            if self.local_bounds is not None
            else None
        )

        child_bounds: list[Bounds] = []
        for child in self.children:
            resolved = child.resolve(self.world_transform)
            if resolved is not None:
                child_bounds.append(resolved)

        self.resolved_bounds = Bounds.union(own_bounds, *child_bounds)

        anchors: dict[str, Point] = {}
        if self.resolved_bounds is not None:
            anchors.update(self.resolved_bounds.standard_anchors())
        anchors.update(
            {
                name: self.world_transform.apply(point)
                for name, point in self.local_anchors.items()
            }
        )
        anchors["origin"] = self.world_transform.apply((0.0, 0.0))
        self.resolved_anchors = anchors
        return self.resolved_bounds

    def anchor(self, name: str) -> Point:
        try:
            return self.resolved_anchors[name]
        except KeyError as exc:
            if self.resolved_bounds is None and not self.resolved_anchors:
                raise RuntimeError(
                    f"scene node {self.id!r} has not been resolved or has no geometry"
                ) from exc
            raise KeyError(f"scene node {self.id!r} has no anchor {name!r}") from exc
