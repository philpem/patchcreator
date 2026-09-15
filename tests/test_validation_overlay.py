from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.cli import main
from patchcreator.validation import (
    Finding,
    OverlayStyle,
    ValidationReport,
    add_debug_layer,
    write_debug_svg,
)

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _root(*, width: str = "80mm", viewbox: str = "0 0 80 80") -> ET.Element:
    return ET.fromstring(
        f'<svg xmlns="{SVG_NS}" width="{width}" height="{width}" viewBox="{viewbox}">'
        '<rect id="art" x="10" y="10" width="20" height="20" fill="#000"/>'
        '</svg>'
    )


def test_debug_layer_is_last_separate_inkscape_layer_in_physical_mm_space():
    root = _root(width="50mm", viewbox="0 0 100 100")
    finding = Finding(
        code="gap-too-narrow",
        severity="warning",
        message="gap",
        element_id="left",
        related_element_id="right",
        measured_mm=0.4,
        threshold_mm=0.6,
        bounds_mm=(10.0, 12.0, 20.0, 22.0),
        points_mm=((15.0, 17.0), (15.4, 17.0)),
    )

    layer = add_debug_layer(root, [finding])

    assert list(root)[-1] is layer
    assert layer.attrib[f"{{{INKSCAPE_NS}}}groupmode"] == "layer"
    assert layer.attrib[f"{{{INKSCAPE_NS}}}label"] == "PatchCreator Validation"
    assert layer.attrib[f"{{{PATCHCREATOR_NS}}}role"] == "validation-overlay"
    assert layer.attrib[f"{{{PATCHCREATOR_NS}}}finding-count"] == "1"
    # 100 SVG units map to 50 mm, so the overlay's mm-space is converted back
    # to SVG user coordinates with a 2x transform.
    assert layer.attrib["transform"] == "matrix(2 0 0 2 0 0)"

    group = layer.find(f"{{{SVG_NS}}}g[@id='patchcreator-validation-000']")
    assert group is not None
    assert group.attrib["data-patchcreator-target-id"] == "left"
    assert group.attrib["data-patchcreator-related-id"] == "right"
    rect = group.find(f"{{{SVG_NS}}}rect")
    line = group.find(f"{{{SVG_NS}}}line")
    circles = group.findall(f"{{{SVG_NS}}}circle")
    assert rect is not None and line is not None
    assert len(circles) == 2
    assert rect.attrib["stroke"] == "#ffb000"
    assert line.attrib["x1"] == "15"
    assert line.attrib["x2"] == "15.4"


def test_overlay_colours_are_configurable_by_severity():
    root = _root()
    findings = [
        Finding("one", "error", "error", bounds_mm=(1, 1, 2, 2)),
        Finding("two", "warning", "warning", bounds_mm=(3, 3, 4, 4)),
        Finding("three", "info", "info", bounds_mm=(5, 5, 6, 6)),
    ]
    style = OverlayStyle(
        error_colour="#aa0000",
        warning_colour="#bbbb00",
        info_colour="#0000cc",
    )
    layer = add_debug_layer(root, findings, style=style)
    strokes = [
        group.find(f"{{{SVG_NS}}}rect").attrib["stroke"]
        for group in layer.findall(f"{{{SVG_NS}}}g")[:3]
    ]
    assert strokes == ["#aa0000", "#bbbb00", "#0000cc"]


def test_unlocated_finding_gets_id_linked_legend_without_modifying_artwork():
    root = _root()
    original_art = root.find(f"{{{SVG_NS}}}rect[@id='art']")
    assert original_art is not None
    original_attrs = dict(original_art.attrib)

    finding = Finding(
        code="stroke-too-thin",
        severity="warning",
        message="thin",
        element_id="route",
        element_tag="path",
        measured_mm=0.3,
        threshold_mm=0.6,
    )
    layer = add_debug_layer(root, [finding])

    legend = layer.find(f"{{{SVG_NS}}}g[@id='patchcreator-validation-unlocated']")
    assert legend is not None
    text = legend.find(f"{{{SVG_NS}}}text")
    assert text is not None
    assert "stroke-too-thin" in (text.text or "")
    assert "route" in (text.text or "")
    assert dict(original_art.attrib) == original_attrs


def test_existing_debug_layer_is_replaced_not_duplicated():
    root = _root()
    add_debug_layer(root, [Finding("a", "warning", "a", bounds_mm=(1, 1, 2, 2))])
    add_debug_layer(root, [Finding("b", "error", "b", bounds_mm=(3, 3, 4, 4))])
    layers = [child for child in root if child.get("id") == "patchcreator-validation"]
    assert len(layers) == 1
    assert layers[0].attrib[f"{{{PATCHCREATOR_NS}}}finding-count"] == "1"
    group = layers[0].find(f"{{{SVG_NS}}}g[@id='patchcreator-validation-000']")
    assert group is not None
    assert group.attrib["data-patchcreator-finding-code"] == "b"


def test_write_debug_svg_copies_source_and_checks_report_source(tmp_path: Path):
    source = tmp_path / "source.svg"
    source.write_text(ET.tostring(_root(), encoding="unicode"), encoding="utf-8")
    destination = tmp_path / "debug.svg"
    original = source.read_text(encoding="utf-8")
    report = ValidationReport(
        source=source,
        findings=(Finding("feature-too-small", "warning", "small", bounds_mm=(1, 1, 2, 2)),),
    )

    assert write_debug_svg(source, report, destination) == destination
    assert source.read_text(encoding="utf-8") == original
    debug_root = ET.fromstring(destination.read_text(encoding="utf-8"))
    assert list(debug_root)[-1].get("id") == "patchcreator-validation"

    wrong = ValidationReport(source=tmp_path / "other.svg", findings=())
    with pytest.raises(ValueError, match="validation report belongs"):
        write_debug_svg(source, wrong, destination)


def test_cli_writes_debug_svg_with_custom_warning_colour(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    source = tmp_path / "thin.svg"
    source.write_text(
        f'''<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="route" d="M 5 5 L 70 5" fill="none" stroke="#fff" stroke-width="0.3"/>
</svg>''',
        encoding="utf-8",
    )
    debug = tmp_path / "thin-debug.svg"

    assert main(
        [
            "check",
            str(source),
            "--debug-svg",
            str(debug),
            "--debug-warning-colour",
            "#123456",
        ]
    ) == 1
    output = capsys.readouterr().out
    assert "stroke-too-thin" in output
    assert f"debug-svg: {debug}" in output

    root = ET.fromstring(debug.read_text(encoding="utf-8"))
    layer = root.find(f"{{{SVG_NS}}}g[@id='patchcreator-validation']")
    assert layer is not None
    legend = layer.find(f"{{{SVG_NS}}}g[@id='patchcreator-validation-unlocated']")
    assert legend is not None
    text = legend.find(f"{{{SVG_NS}}}text")
    assert text is not None
    assert text.attrib["fill"] == "#123456"
    assert "route" in (text.text or "")


def test_empty_report_still_produces_removable_empty_layer(tmp_path: Path):
    source = tmp_path / "clean.svg"
    source.write_text(ET.tostring(_root(), encoding="unicode"), encoding="utf-8")
    destination = tmp_path / "clean-debug.svg"
    report = ValidationReport(source=source, findings=())
    write_debug_svg(source, report, destination)

    root = ET.fromstring(destination.read_text(encoding="utf-8"))
    layer = root.find(f"{{{SVG_NS}}}g[@id='patchcreator-validation']")
    assert layer is not None
    assert layer.attrib[f"{{{PATCHCREATOR_NS}}}finding-count"] == "0"
