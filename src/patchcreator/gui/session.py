"""GUI-independent editable YAML preview state.

The GUI intentionally owns only source text and file state. Parsing, scene
construction and SVG generation are delegated to the normal PatchCreator
library pipeline so there is no second GUI document model to keep in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from patchcreator.config.loader import DesignLoadError, loads_design
from patchcreator.config.schema import DesignSpec, ElementSpec, LayerSpec
from patchcreator.svg.writer import render_design


@dataclass(frozen=True)
class SceneTreeItem:
    id: str
    label: str
    kind: str
    visible: bool
    children: tuple["SceneTreeItem", ...] = ()


def _element_tree(element: ElementSpec) -> SceneTreeItem:
    return SceneTreeItem(
        id=element.id,
        label=element.label or element.id,
        kind=element.type,
        visible=element.visible,
        children=tuple(_element_tree(child) for child in element.elements),
    )


def _layer_tree(layer: LayerSpec) -> SceneTreeItem:
    return SceneTreeItem(
        id=layer.id,
        label=layer.label or layer.id,
        kind="layer",
        visible=layer.visible,
        children=tuple(_element_tree(element) for element in layer.elements),
    )


def scene_tree(design: DesignSpec) -> tuple[SceneTreeItem, ...]:
    """Return an immutable hierarchy derived directly from ``DesignSpec``."""

    return tuple(_layer_tree(layer) for layer in design.layers)


@dataclass(frozen=True)
class PreviewResult:
    svg: str | None
    warnings: tuple[str, ...] = ()
    error: str | None = None
    tree: tuple[SceneTreeItem, ...] = ()

    @property
    def valid(self) -> bool:
        return self.error is None


class PreviewSession:
    """Editable design source plus the last successfully rendered preview."""

    def __init__(self, text: str = "", *, source_path: str | Path | None = None) -> None:
        self.text = text
        self.source_path = Path(source_path) if source_path is not None else None
        self.last_valid_svg: str | None = None
        self.last_valid_tree: tuple[SceneTreeItem, ...] = ()
        self.last_warnings: tuple[str, ...] = ()
        self.last_error: str | None = None
        self.dirty = False

    @property
    def display_name(self) -> str:
        return self.source_path.name if self.source_path is not None else "Untitled"

    def set_text(self, text: str) -> None:
        if text != self.text:
            self.text = text
            self.dirty = True

    def render(self) -> PreviewResult:
        source = str(self.source_path) if self.source_path is not None else None
        try:
            design = loads_design(self.text, source=source)
            if self.source_path is not None:
                design.set_source_dir(self.source_path.parent)
            rendered = render_design(design)
            tree = scene_tree(design)
        except (DesignLoadError, OSError, ValueError) as exc:
            self.last_error = str(exc)
            return PreviewResult(
                svg=self.last_valid_svg,
                warnings=self.last_warnings,
                error=self.last_error,
                tree=self.last_valid_tree,
            )

        self.last_valid_svg = rendered.svg
        self.last_valid_tree = tree
        self.last_warnings = rendered.warnings
        self.last_error = None
        return PreviewResult(svg=rendered.svg, warnings=rendered.warnings, tree=tree)

    def load(self, path: str | Path) -> PreviewResult:
        source_path = Path(path)
        self.text = source_path.read_text(encoding="utf-8")
        self.source_path = source_path
        self.dirty = False
        return self.render()

    def save(self, path: str | Path | None = None) -> Path:
        destination = Path(path) if path is not None else self.source_path
        if destination is None:
            raise ValueError("no destination selected for unsaved design")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.text, encoding="utf-8")
        self.source_path = destination
        self.dirty = False
        return destination
