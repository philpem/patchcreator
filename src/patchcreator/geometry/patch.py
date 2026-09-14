"""Patch boundary and safe-area geometry."""

from __future__ import annotations

from dataclasses import dataclass

from patchcreator.config.schema import CanvasSpec


@dataclass(frozen=True)
class CanvasGeometry:
    shape: str
    width: float
    height: float
    safe_margin: float

    @classmethod
    def from_spec(cls, spec: CanvasSpec) -> "CanvasGeometry":
        if spec.shape == "circle":
            assert spec.diameter is not None
            width = height = spec.diameter
        else:
            assert spec.width is not None and spec.height is not None
            width, height = spec.width, spec.height

        reference_radius = min(width, height) / 2.0
        margin_spec = spec.safe_margin
        if margin_spec.fixed is not None:
            safe_margin = margin_spec.fixed
        else:
            assert margin_spec.percent is not None
            safe_margin = reference_radius * (margin_spec.percent / 100.0)
            if margin_spec.min is not None:
                safe_margin = max(safe_margin, margin_spec.min)
            if margin_spec.max is not None:
                safe_margin = min(safe_margin, margin_spec.max)

        if safe_margin >= reference_radius:
            raise ValueError(
                f"safe margin {safe_margin:g} mm leaves no usable design area "
                f"for a {width:g} x {height:g} mm patch"
            )
        return cls(spec.shape, width, height, safe_margin)

    @property
    def centre(self) -> tuple[float, float]:
        return self.width / 2.0, self.height / 2.0

    @property
    def reference_radius(self) -> float:
        return min(self.width, self.height) / 2.0

    @property
    def safe_width(self) -> float:
        return self.width - 2 * self.safe_margin

    @property
    def safe_height(self) -> float:
        return self.height - 2 * self.safe_margin
