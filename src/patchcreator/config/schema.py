"""Pydantic models for the human-authored PatchCreator YAML format.

The element model is deliberately extensible: common compositor properties are
validated here, while component-specific properties remain available to the
component implementation. This lets third-party procedural components extend
the format without requiring edits to the core schema dispatcher.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from patchcreator.palette import resolve_palette_map
from patchcreator.profiles.model import ProfileConstraints


LengthValue = float | str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtensibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SafeMarginSpec(StrictModel):
    fixed: float | None = Field(default=None, ge=0)
    percent: float | None = Field(default=None, ge=0)
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_mode(self) -> "SafeMarginSpec":
        if (self.fixed is None) == (self.percent is None):
            raise ValueError("safe_margin must specify exactly one of 'fixed' or 'percent'")
        if self.fixed is not None and (self.min is not None or self.max is not None):
            raise ValueError("safe_margin min/max clamps apply only to percentage margins")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("safe_margin min must not exceed max")
        return self


class CanvasSpec(StrictModel):
    shape: Literal["circle", "ellipse"]
    diameter: float | None = Field(default=None, gt=0)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    background: str | None = None
    safe_margin: SafeMarginSpec = Field(default_factory=lambda: SafeMarginSpec(fixed=0))

    @model_validator(mode="after")
    def validate_dimensions(self) -> "CanvasSpec":
        if self.shape == "circle":
            if self.diameter is None:
                raise ValueError("a circular canvas requires 'diameter'")
            if self.width is not None or self.height is not None:
                raise ValueError("a circular canvas uses 'diameter', not width/height")
        elif self.shape == "ellipse":
            if self.width is None or self.height is None:
                raise ValueError("an elliptical canvas requires both 'width' and 'height'")
            if self.diameter is not None:
                raise ValueError("an elliptical canvas uses width/height, not 'diameter'")
        return self


class ProfileSpec(StrictModel):
    machine: str | None = None
    intent: str | None = None
    overrides: ProfileConstraints = Field(default_factory=ProfileConstraints)


class MetadataSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str | None = None


class DerivedColourSpec(StrictModel):
    from_: str = Field(alias="from")
    lighten: float | None = Field(default=None, ge=0, le=1)
    darken: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def one_derivation(self) -> "DerivedColourSpec":
        if self.lighten is not None and self.darken is not None:
            raise ValueError("a derived colour cannot specify both lighten and darken")
        return self


PaletteValue = str | DerivedColourSpec


class SettingsSpec(StrictModel):
    default_clip: str = "safe-area"
    inkscape_metadata: bool = True
    construction_guides: bool = False
    embroidery_safety: bool = True


class ClipSpec(StrictModel):
    target: str = "inherit"
    enabled: bool = True
    inset: float = 0.0


class CoordinateFrameSpec(StrictModel):
    """Coordinate-frame override inherited by an element's children.

    ``origin: inherit`` keeps the parent's frame and can be used to override
    only its reference radius. ``origin: self`` establishes a frame at the
    element's local origin with axes following the element transform. A pair is
    interpreted as an explicit point in the element's local coordinate system.
    """

    origin: Literal["inherit", "self"] | tuple[LengthValue, LengthValue] = "inherit"
    reference_radius: LengthValue | None = None


class CartesianPosition(StrictModel):
    mode: Literal["cartesian"]
    x: LengthValue = 0.0
    y: LengthValue = 0.0
    self_anchor: str = "centre"


class PolarPosition(StrictModel):
    mode: Literal["polar"]
    angle: float | str
    radius: LengthValue
    reference_radius: LengthValue | None = None
    self_anchor: str = "centre"


class RelativePosition(StrictModel):
    mode: Literal["relative"]
    target: str
    target_anchor: str = "centre"
    self_anchor: str = "centre"
    offset: tuple[LengthValue, LengthValue] = (0.0, 0.0)


class PathPosition(StrictModel):
    mode: Literal["path"]
    path: str
    at: float | str = 0.0
    orient: Literal["none", "tangent"] = "none"
    normal_offset: LengthValue = 0.0
    self_anchor: str = "centre"


PositionSpec = Annotated[
    CartesianPosition | PolarPosition | RelativePosition | PathPosition,
    Field(discriminator="mode"),
]


class ElementSpec(ExtensibleModel):
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    label: str | None = None
    visible: bool = True
    position: PositionSpec | None = None
    frame: CoordinateFrameSpec | None = None
    clip: ClipSpec | None = None
    overlap_policy: Literal["allow", "warn", "avoid", "knockout", "background"] = "warn"
    elements: list["ElementSpec"] = Field(default_factory=list)

    def component_config(self) -> dict[str, Any]:
        """Return component-specific fields not consumed by the core model."""
        return dict(self.__pydantic_extra__ or {})


class LayerSpec(StrictModel):
    id: str = Field(min_length=1)
    label: str | None = None
    visible: bool = True
    frame: CoordinateFrameSpec | None = None
    elements: list[ElementSpec] = Field(default_factory=list)


class DesignSpec(StrictModel):
    version: str | float
    units: Literal["mm"] = "mm"
    canvas: CanvasSpec
    profile: ProfileSpec = Field(default_factory=ProfileSpec)
    metadata: MetadataSpec = Field(default_factory=MetadataSpec)
    palette: dict[str, PaletteValue] = Field(default_factory=dict)
    settings: SettingsSpec = Field(default_factory=SettingsSpec)
    layers: list[LayerSpec] = Field(default_factory=list)

    _source_dir: Path | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def validate_design(self) -> "DesignSpec":
        version = str(self.version)
        if version != "0.1":
            raise ValueError(f"unsupported design version {version!r}; expected '0.1'")
        # Resolve derived values once so existing and third-party renderers only
        # need to deal with ordinary CSS colour strings.
        self.palette = resolve_palette_map(self.palette)
        return self

    @property
    def source_dir(self) -> Path | None:
        """Directory containing the loaded YAML design, if it came from a file."""
        return self._source_dir

    def set_source_dir(self, path: str | Path | None) -> None:
        self._source_dir = Path(path).resolve() if path is not None else None
