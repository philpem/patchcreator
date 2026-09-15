"""Structured validation findings shared by CLI and future debug overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class Finding:
    """One embroidery-geometry concern tied to SVG objects where possible."""

    code: str
    severity: Severity
    message: str
    element_id: str | None = None
    element_tag: str | None = None
    related_element_id: str | None = None
    related_element_tag: str | None = None
    element_policy: str | None = None
    related_element_policy: str | None = None
    measured_mm: float | None = None
    threshold_mm: float | None = None
    measured_mm2: float | None = None
    threshold_mm2: float | None = None
    bounds_mm: tuple[float, float, float, float] | None = None
    points_mm: tuple[tuple[float, float], ...] | None = None

    def format(self) -> str:
        location = self.element_id or self.element_tag or "document"
        related = self.related_element_id or self.related_element_tag
        if related:
            location = f"{location} <-> {related}"
        measurement = ""
        if self.measured_mm is not None and self.threshold_mm is not None:
            measurement = f" ({self.measured_mm:.3g} mm < {self.threshold_mm:.3g} mm)"
        elif self.measured_mm2 is not None and self.threshold_mm2 is not None:
            measurement = f" ({self.measured_mm2:.3g} mm² < {self.threshold_mm2:.3g} mm²)"
        elif self.measured_mm2 is not None:
            measurement = f" ({self.measured_mm2:.3g} mm² overlap)"
        return f"{self.severity}: {self.code}: {location}: {self.message}{measurement}"


@dataclass(frozen=True)
class ValidationReport:
    source: Path | None
    findings: tuple[Finding, ...]
    validator_names: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.error_count == 0 and self.warning_count == 0

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)

    @property
    def info_count(self) -> int:
        return sum(finding.severity == "info" for finding in self.findings)
