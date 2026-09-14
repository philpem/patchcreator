from __future__ import annotations

from dataclasses import dataclass

from patchcreator.config.schema import DesignSpec, ElementSpec
from patchcreator.geometry.primitives import Bounds
from patchcreator.geometry.transform import AffineTransform, Point

from .node import SceneNode


class DuplicateNodeIdError(ValueError):
    pass


def _element_node(spec: ElementSpec) -> SceneNode:
    return SceneNode(
        id=spec.id,
        kind=spec.type,
        label=spec.label,
        visible=spec.visible,
        config=spec,
        children=[_element_node(child) for child in spec.elements],
    )


@dataclass
class SceneGraph:
    root: SceneNode
    by_id: dict[str, SceneNode]

    @classmethod
    def from_design(cls, design: DesignSpec) -> "SceneGraph":
        root = SceneNode(id="__root__", kind="root", label="PatchCreator document")
        for layer in design.layers:
            root.add_child(
                SceneNode(
                    id=layer.id,
                    kind="layer",
                    label=layer.label,
                    visible=layer.visible,
                    config=layer,
                    children=[_element_node(element) for element in layer.elements],
                )
            )

        by_id: dict[str, SceneNode] = {}
        for node in root.walk():
            if node is root:
                continue
            if node.id == root.id:
                raise DuplicateNodeIdError(
                    f"scene node id {root.id!r} is reserved for the document root"
                )
            if node.id in by_id:
                raise DuplicateNodeIdError(f"duplicate scene node id {node.id!r}")
            by_id[node.id] = node
        return cls(root=root, by_id=by_id)

    def find(self, node_id: str) -> SceneNode:
        try:
            return self.by_id[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown scene node {node_id!r}") from exc

    def set_geometry(
        self,
        node_id: str,
        bounds: Bounds | None,
        *,
        anchors: dict[str, Point] | None = None,
    ) -> None:
        """Attach local component geometry to a node before resolution."""
        self.find(node_id).set_geometry(bounds, anchors=anchors)

    def set_transform(self, node_id: str, transform: AffineTransform) -> None:
        """Attach a local transform to a node before resolution."""
        self.find(node_id).local_transform = transform

    def resolve(self) -> "SceneGraph":
        """Resolve world transforms, bounds and anchors for the whole graph."""
        self.root.resolve()
        return self
