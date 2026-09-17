from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.validation import (
    SvgInspectionError,
    check_svg,
    check_svg_text,
    debug_svg_text,
)

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"

_SAMPLE = f"""<svg xmlns="{SVG_NS}" width="20mm" height="20mm" viewBox="0 0 20 20">
  <rect id="thin" x="2" y="2" width="6" height="6" fill="#f00" stroke="#000" stroke-width="0.2"/>
  <rect id="near" x="8.4" y="2" width="6" height="6" fill="#0f0"/>
</svg>"""


def _options() -> dict[str, object]:
    return {
        "minimum_stroke_width_mm": 0.5,
        "minimum_feature_dimension_mm": 1.0,
        "minimum_island_area_mm2": 1.0,
        "minimum_gap_mm": 1.0,
        "overlap_diagnostics": True,
    }


def test_check_svg_text_matches_file_validation(tmp_path: Path):
    source = tmp_path / "sample.svg"
    source.write_text(_SAMPLE, encoding="utf-8")

    file_report = check_svg(source, **_options())
    memory_report = check_svg_text(_SAMPLE, source=source, **_options())

    assert memory_report.source == source
    assert memory_report.validator_names == file_report.validator_names
    assert memory_report.findings == file_report.findings


def test_check_svg_text_source_is_optional_and_not_read_from_disk(tmp_path: Path):
    missing = tmp_path / "not-created.svg"
    report = check_svg_text(
        _SAMPLE,
        source=missing,
        minimum_stroke_width_mm=0.5,
    )

    assert report.source == missing
    assert report.findings
    assert not missing.exists()


def test_debug_svg_text_adds_removable_overlay_without_mutating_input():
    report = check_svg_text(_SAMPLE, minimum_stroke_width_mm=0.5)
    debug = debug_svg_text(_SAMPLE, report)

    assert "patchcreator-validation" not in _SAMPLE
    root = ET.fromstring(debug)
    layer = root.find(f".//{{{SVG_NS}}}g[@id='patchcreator-validation']")
    assert layer is not None
    assert layer.get(f"{{{PATCHCREATOR_NS}}}role") == "validation-overlay"
    assert int(layer.get(f"{{{PATCHCREATOR_NS}}}finding-count", "0")) == len(report.findings)


def test_file_and_text_parsers_reject_doctype_consistently(tmp_path: Path):
    text = f"<!DOCTYPE svg><svg xmlns=\"{SVG_NS}\" width=\"1mm\" height=\"1mm\"/>"
    source = tmp_path / "doctype.svg"
    source.write_text(text, encoding="utf-8")

    with pytest.raises(SvgInspectionError, match="DOCTYPE"):
        check_svg_text(text)
    with pytest.raises(SvgInspectionError, match="DOCTYPE"):
        check_svg(source)


def test_text_parser_rejects_invalid_xml_and_non_svg():
    with pytest.raises(SvgInspectionError, match="cannot parse SVG"):
        check_svg_text("<svg")

    with pytest.raises(SvgInspectionError, match="not an SVG document"):
        check_svg_text("<html/>")
