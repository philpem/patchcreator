"""Inkscape-friendly visual overlay for structured validation findings.

The overlay is intentionally a separate top-level SVG layer. Validation never
rewrites artwork geometry: a debug copy can be hidden or deleted wholesale in
Inkscape without changing the source objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from .geometry import _root_transform_mm
from .model import Finding, ValidationReport
from .svg import load_svg, parse_svg_text

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"

ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)
ET.register_namespace("patchcreator", PATCHCREATOR_NS)


def _q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class OverlayStyle:
    """Physical drawing style for the debug layer.

    Sizes are millimetres because the layer establishes a millimetre coordinate
    space independent of the source SVG's viewBox. Colours are ordinary SVG/CSS
    colour strings and are intentionally configurable by API and CLI.
    """

    error_colour: str = "#ff2d2d"
    warning_colour: str = "#ffb000"
    info_colour: str = "#00a6ff"
    stroke_width_mm: float = 0.45
    point_radius_mm: float = 0.65
    bounds_padding_mm: float = 0.35
    label_font_size_mm: float = 2.2
    label_line_height_mm: float = 3.0
    fill_opacity: float = 0.10

    def __post_init__(self) -> None:
        if self.stroke_width_mm <= 0:
            raise ValueError("overlay stroke width must be positive")
        if self.point_radius_mm <= 0:
            raise ValueError("overlay point radius must be positive")
        if self.bounds_padding_mm < 0:
            raise ValueError("overlay bounds padding must not be negative")
        if self.label_font_size_mm <= 0 or self.label_line_height_mm <= 0:
            raise ValueError("overlay label sizes must be positive")
        if not 0.0 <= self.fill_opacity <= 1.0:
            raise ValueError("overlay fill opacity must be between 0 and 1")

    def colour_for(self, finding: Finding) -> str:
        if finding.severity == "error":
            return self.error_colour
        if finding.severity == "warning":
            return self.warning_colour
        return self.info_colour


def _target_text(finding: Finding) -> str:
    first = finding.element_id or finding.element_tag or "document"
    second = finding.related_element_id or finding.related_element_tag
    return f"{first} ↔ {second}" if second else first


def _finding_attrs(index: int, finding: Finding) -> dict[str, str]:
    attrs = {
        "id": f"patchcreator-validation-{index:03d}",
        "data-patchcreator-finding-code": finding.code,
        "data-patchcreator-severity": finding.severity,
        "data-patchcreator-target": _target_text(finding),
    }
    if finding.element_id:
        attrs["data-patchcreator-target-id"] = finding.element_id
    if finding.related_element_id:
        attrs["data-patchcreator-related-id"] = finding.related_element_id
    return attrs


def _append_geometry_marker(
    parent: ET.Element,
    finding: Finding,
    *,
    colour: str,
    style: OverlayStyle,
) -> bool:
    """Append geometric marker(s) in millimetres and report whether located."""
    located = False

    if finding.bounds_mm is not None:
        min_x, min_y, max_x, max_y = finding.bounds_mm
        padding = style.bounds_padding_mm
        ET.SubElement(
            parent,
            _q(SVG_NS, "rect"),
            {
                "x": _fmt(min_x - padding),
                "y": _fmt(min_y - padding),
                "width": _fmt(max(0.0, max_x - min_x) + padding * 2.0),
                "height": _fmt(max(0.0, max_y - min_y) + padding * 2.0),
                "rx": _fmt(min(0.8, padding + 0.15)),
                "fill": colour,
                "fill-opacity": _fmt(style.fill_opacity),
                "stroke": colour,
                "stroke-width": _fmt(style.stroke_width_mm),
                "stroke-dasharray": "1.5 0.8",
            },
        )
        located = True

    points = finding.points_mm or ()
    if len(points) >= 2:
        first, second = points[0], points[1]
        ET.SubElement(
            parent,
            _q(SVG_NS, "line"),
            {
                "x1": _fmt(first[0]),
                "y1": _fmt(first[1]),
                "x2": _fmt(second[0]),
                "y2": _fmt(second[1]),
                "stroke": colour,
                "stroke-width": _fmt(style.stroke_width_mm),
            },
        )
        located = True

    for x, y in points:
        ET.SubElement(
            parent,
            _q(SVG_NS, "circle"),
            {
                "cx": _fmt(x),
                "cy": _fmt(y),
                "r": _fmt(style.point_radius_mm),
                "fill": "none",
                "stroke": colour,
                "stroke-width": _fmt(style.stroke_width_mm),
            },
        )
        located = True

    return located


def add_debug_layer(
    root: ET.Element,
    findings: tuple[Finding, ...] | list[Finding],
    *,
    style: OverlayStyle | None = None,
    layer_id: str = "patchcreator-validation",
    layer_label: str = "PatchCreator Validation",
) -> ET.Element:
    """Append/replace a visible top Inkscape layer describing ``findings``."""
    style = style or OverlayStyle()

    for child in list(root):
        if child.get("id") == layer_id:
            root.remove(child)

    millimetres_to_user = _root_transform_mm(root).inverse()
    layer = ET.SubElement(
        root,
        _q(SVG_NS, "g"),
        {
            "id": layer_id,
            _q(INKSCAPE_NS, "groupmode"): "layer",
            _q(INKSCAPE_NS, "label"): layer_label,
            _q(PATCHCREATOR_NS, "role"): "validation-overlay",
            _q(PATCHCREATOR_NS, "finding-count"): str(len(findings)),
            "transform": millimetres_to_user.to_svg(),
        },
    )

    unlocated: list[tuple[int, Finding, str]] = []
    for index, finding in enumerate(findings):
        colour = style.colour_for(finding)
        group = ET.SubElement(
            layer,
            _q(SVG_NS, "g"),
            _finding_attrs(index, finding),
        )
        if not _append_geometry_marker(group, finding, colour=colour, style=style):
            unlocated.append((index, finding, colour))

    if unlocated:
        legend = ET.SubElement(
            layer,
            _q(SVG_NS, "g"),
            {
                "id": "patchcreator-validation-unlocated",
                "data-patchcreator-role": "unlocated-findings",
            },
        )
        x = 1.5
        y = 3.0
        width = 36.0
        height = style.label_line_height_mm * len(unlocated) + 1.5
        ET.SubElement(
            legend,
            _q(SVG_NS, "rect"),
            {
                "x": _fmt(x - 0.8),
                "y": _fmt(y - style.label_font_size_mm),
                "width": _fmt(width),
                "height": _fmt(height),
                "rx": "0.8",
                "fill": "#ffffff",
                "fill-opacity": "0.9",
                "stroke": "#000000",
                "stroke-width": "0.2",
            },
        )
        for line, (index, finding, colour) in enumerate(unlocated):
            text = ET.SubElement(
                legend,
                _q(SVG_NS, "text"),
                {
                    "x": _fmt(x),
                    "y": _fmt(y + line * style.label_line_height_mm),
                    "font-family": "sans-serif",
                    "font-size": _fmt(style.label_font_size_mm),
                    "font-weight": "bold",
                    "fill": colour,
                    "data-patchcreator-finding-index": str(index),
                },
            )
            text.text = f"{finding.severity.upper()}: {finding.code}: {_target_text(finding)}"

    return layer


def debug_svg_text(
    text: str,
    report: ValidationReport,
    *,
    style: OverlayStyle | None = None,
) -> str:
    """Return an in-memory SVG copy with the removable validation layer added."""

    root = parse_svg_text(text, source=report.source)
    add_debug_layer(root, report.findings, style=style)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False) + "\n"


def write_debug_svg(
    source: str | Path,
    report: ValidationReport,
    output: str | Path,
    *,
    style: OverlayStyle | None = None,
) -> Path:
    """Write a copy of ``source`` with a removable top validation layer."""
    source_path, root = load_svg(source)
    if report.source is not None and report.source.resolve() != source_path.resolve():
        raise ValueError(
            f"validation report belongs to {report.source}, not {source_path}"
        )
    add_debug_layer(root, report.findings, style=style)
    ET.indent(root, space="  ")
    destination = Path(output)
    destination.write_text(
        ET.tostring(root, encoding="unicode", xml_declaration=False) + "\n",
        encoding="utf-8",
    )
    return destination
