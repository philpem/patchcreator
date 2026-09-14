from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class SceneNode:
    id: str
    kind: str
    label: str | None = None
    visible: bool = True
    config: Any = None
    children: list["SceneNode"] = field(default_factory=list)

    def walk(self) -> Iterator["SceneNode"]:
        yield self
        for child in self.children:
            yield from child.walk()
