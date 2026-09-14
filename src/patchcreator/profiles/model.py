"""Embroidery machine and design-intent profile models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProfileConstraints(BaseModel):
    """Geometry limits used by the embroidery validator.

    Values are millimetres except ``minimum_island_area``, which is mm².
    ``None`` means that this profile layer does not constrain that property.
    """

    model_config = ConfigDict(extra="forbid")

    validation_enabled: bool | None = None
    minimum_stroke_width: float | None = Field(default=None, ge=0)
    minimum_gap: float | None = Field(default=None, ge=0)
    minimum_feature_dimension: float | None = Field(default=None, ge=0)
    minimum_island_area: float | None = Field(default=None, ge=0)

    def merged(self, override: "ProfileConstraints") -> "ProfileConstraints":
        data = self.model_dump()
        for key, value in override.model_dump().items():
            if value is not None:
                data[key] = value
        return ProfileConstraints.model_validate(data)


class ProfileDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: Literal["machine", "intent"]
    description: str | None = None
    experimental: bool = False
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)


class EffectiveProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    machine: str | None = None
    intent: str | None = None
    constraints: ProfileConstraints = Field(default_factory=ProfileConstraints)
    sources: tuple[str, ...] = ()
