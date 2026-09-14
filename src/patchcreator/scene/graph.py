from __future__ import annotations

from dataclasses import dataclass

from patchcreator.config.schema import DesignSpec, ElementSpec

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
            root.children.append(
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
            if node.id == "__root__":
                continue
            if node.id in by_id:
                raise DuplicateNodeIdError(f"duplicate scene node id {node.id!r}")
            by_id[node.id] = node
        return cls(root=root, by_id=by_id)

    def find(self, node_id: str) -> SceneNode:
        try:
            return self.by_id[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown scene node {node_id!r}") from exc
