"""GUI-independent editable YAML preview state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import secrets
import xml.etree.ElementTree as ET

from patchcreator.config.loader import DesignLoadError, loads_design
from patchcreator.config.schema import DesignSpec, ElementSpec, LayerSpec
from patchcreator.profiles import ProfileError, resolve_profile
from patchcreator.svg.writer import render_design
from patchcreator.validation import ValidationReport, check_svg_text, debug_svg_text

from .source_edit import (
    PlacementMode,
    PlacementState,
    StarfieldSeedState,
    placement_state,
    set_element_position,
    set_starfield_seed,
    starfield_seed_state,
)

PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


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
    return tuple(_layer_tree(layer) for layer in design.layers)


def resolved_starfield_seed(svg: str | None, element_id: str) -> int | None:
    """Read the renderer-resolved seed from PatchCreator SVG metadata."""

    if not svg:
        return None
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return None
    for element in root.iter():
        if element.get("id") != element_id:
            continue
        raw = element.get(f"{{{PATCHCREATOR_NS}}}seed")
        if raw is None:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if 0 <= value < 1 << 64 else None
    return None


@dataclass(frozen=True)
class PreviewResult:
    svg: str | None
    warnings: tuple[str, ...] = ()
    error: str | None = None
    tree: tuple[SceneTreeItem, ...] = ()
    validation_report: ValidationReport | None = None
    validation_error: str | None = None
    validation_profile: str | None = None

    @property
    def valid(self) -> bool:
        return self.error is None


class PreviewSession:
    def __init__(self, text: str = "", *, source_path: str | Path | None = None) -> None:
        self.text = text
        self.source_path = Path(source_path) if source_path is not None else None
        self.validation_enabled = False
        self.last_valid_svg: str | None = None
        self.last_display_svg: str | None = None
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

    def set_validation_enabled(self, enabled: bool) -> None:
        self.validation_enabled = bool(enabled)

    def placement(self, element_id: str) -> PlacementState:
        return placement_state(self.text, element_id)

    def set_placement(
        self,
        element_id: str,
        *,
        mode: PlacementMode,
        first: str,
        second: str,
    ) -> str:
        updated = set_element_position(
            self.text,
            element_id,
            mode=mode,
            first=first,
            second=second,
        )
        self.set_text(updated)
        return updated

    def starfield_seed(self, element_id: str) -> StarfieldSeedState:
        return starfield_seed_state(self.text, element_id)

    def resolved_seed(self, element_id: str) -> int | None:
        return resolved_starfield_seed(self.last_valid_svg, element_id)

    def set_seed(self, element_id: str, seed: int | str) -> str:
        updated = set_starfield_seed(self.text, element_id, seed)
        self.set_text(updated)
        return updated

    def lock_current_seed(self, element_id: str) -> str:
        seed = self.resolved_seed(element_id)
        if seed is None:
            raise ValueError(f"starfield {element_id!r} has no resolved seed in the current render")
        return self.set_seed(element_id, seed)

    def regenerate_seed(self, element_id: str) -> str:
        return self.set_seed(element_id, secrets.randbits(64))

    def auto_seed(self, element_id: str) -> str:
        return self.set_seed(element_id, "auto")

    def _validate_preview(
        self,
        design: DesignSpec,
        svg: str,
    ) -> tuple[str, ValidationReport | None, str | None, str | None]:
        if not self.validation_enabled:
            return svg, None, None, None
        try:
            effective = resolve_profile(design.profile)
            constraints = effective.constraints
            profile_name = effective.intent or effective.machine or "custom"
            if constraints.validation_enabled is False:
                return svg, None, "validation disabled by effective profile", profile_name
            if not any(
                value is not None
                for value in (
                    constraints.minimum_stroke_width,
                    constraints.minimum_gap,
                    constraints.minimum_feature_dimension,
                    constraints.minimum_island_area,
                )
            ):
                raise ProfileError("effective profile does not define any validation thresholds")
            report = check_svg_text(
                svg,
                minimum_stroke_width_mm=constraints.minimum_stroke_width,
                minimum_feature_dimension_mm=constraints.minimum_feature_dimension,
                minimum_island_area_mm2=constraints.minimum_island_area,
                minimum_gap_mm=constraints.minimum_gap,
                overlap_diagnostics=True,
            )
            return debug_svg_text(svg, report), report, None, profile_name
        except (ProfileError, ValueError) as exc:
            return svg, None, str(exc), None

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
                svg=self.last_display_svg or self.last_valid_svg,
                warnings=self.last_warnings,
                error=self.last_error,
                tree=self.last_valid_tree,
            )

        self.last_valid_svg = rendered.svg
        self.last_valid_tree = tree
        self.last_warnings = rendered.warnings
        self.last_error = None
        display_svg, report, validation_error, profile_name = self._validate_preview(
            design, rendered.svg
        )
        self.last_display_svg = display_svg
        return PreviewResult(
            svg=display_svg,
            warnings=rendered.warnings,
            tree=tree,
            validation_report=report,
            validation_error=validation_error,
            validation_profile=profile_name,
        )

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
