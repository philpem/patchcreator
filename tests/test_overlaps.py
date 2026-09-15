from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.cli import main
from patchcreator.config.loader import loads_design
from patchcreator.svg.writer import SVG_NS, render_design
from patchcreator.validation import check_svg, validate_overlaps


def _root(body: str) -> ET.Element:
    return ET.fromstring(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">{body}</svg>'
    )


def _write_svg(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "overlap.svg"
    ET.ElementTree(_root(body)).write(path, encoding="unicode")
    return path


def test_plain_svg_overlap_defaults_to_warning():
    findings = validate_overlaps(
        _root(
            '<rect id="lower" x="0" y="0" width="10" height="10"/>'
            '<rect id="upper" x="5" y="0" width="10" height="10"/>'
        )
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "overlap-thread-buildup"
    assert finding.severity == "warning"
    assert finding.element_id == "lower"
    assert finding.related_element_id == "upper"
    assert finding.measured_mm2 == pytest.approx(50.0)
    assert "50 mm² overlap" in finding.format()


def test_background_and_allow_policies_suppress_intentional_overlap():
    root = _root(
        '<g id="bg" data-patchcreator-overlap-policy="background">'
        '  <rect x="0" y="0" width="80" height="80"/>'
        '</g>'
        '<g id="a" data-patchcreator-overlap-policy="allow">'
        '  <rect x="10" y="10" width="20" height="20"/>'
        '</g>'
        '<g id="b" data-patchcreator-overlap-policy="allow">'
        '  <rect x="20" y="20" width="20" height="20"/>'
        '</g>'
    )
    assert validate_overlaps(root) == []


def test_avoid_policy_overlap_is_an_error_with_logical_owner_ids():
    root = _root(
        '<g id="stars" data-patchcreator-overlap-policy="avoid">'
        '  <circle id="stars-one" cx="10" cy="10" r="5"/>'
        '  <circle id="stars-two" cx="30" cy="10" r="5"/>'
        '</g>'
        '<g id="subject" data-patchcreator-overlap-policy="warn">'
        '  <rect id="subject-shape" x="7" y="7" width="6" height="6"/>'
        '</g>'
    )
    findings = validate_overlaps(root)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "overlap-avoid-violation"
    assert finding.severity == "error"
    assert finding.element_id == "stars"
    assert finding.related_element_id == "subject"
    assert finding.element_policy == "avoid"
    assert finding.related_element_policy == "warn"
    assert finding.bounds_mm is not None
    assert finding.points_mm is not None


def test_geometry_inside_one_logical_component_is_unioned_before_comparison():
    root = _root(
        '<g id="asset" data-patchcreator-overlap-policy="warn">'
        '  <rect x="0" y="0" width="10" height="10"/>'
        '  <rect x="5" y="0" width="10" height="10"/>'
        '</g>'
    )
    # Layering inside a reusable/component object is its own artwork, not a
    # suspicious overlap between separate stitch objects.
    assert validate_overlaps(root) == []


def test_knockout_overlap_is_informational_and_does_not_make_report_fail(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        '<g id="lower" data-patchcreator-overlap-policy="knockout">'
        '  <rect x="0" y="0" width="10" height="10"/>'
        '</g>'
        '<g id="upper" data-patchcreator-overlap-policy="allow">'
        '  <rect x="5" y="0" width="10" height="10"/>'
        '</g>',
    )
    report = check_svg(path, overlap_diagnostics=True)
    assert len(report.findings) == 1
    assert report.findings[0].code == "overlap-knockout-pending"
    assert report.findings[0].severity == "info"
    assert report.info_count == 1
    assert report.ok

    assert main(["check", str(path)]) == 0
    output = capsys_output = None


def test_generated_patchcreator_svg_preserves_overlap_policy_metadata():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: lower
        type: star
        glyph: dot
        size: 10
        overlap_policy: allow
        clip: {target: none}
      - id: upper
        type: star
        glyph: dot
        size: 10
        overlap_policy: avoid
        clip: {target: none}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    lower = root.find(f".//{{{SVG_NS}}}g[@id='lower']")
    upper = root.find(f".//{{{SVG_NS}}}g[@id='upper']")
    assert lower is not None and upper is not None
    assert lower.attrib["data-patchcreator-overlap-policy"] == "allow"
    assert upper.attrib["data-patchcreator-overlap-policy"] == "avoid"

    findings = validate_overlaps(root)
    assert len(findings) == 1
    assert findings[0].code == "overlap-avoid-violation"
    assert findings[0].element_id == "lower"
    assert findings[0].related_element_id == "upper"


def test_canvas_background_is_treated_as_background_policy():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  background: space
palette: {space: '#000000'}
layers:
  - id: art
    elements:
      - id: subject
        type: star
        glyph: dot
        size: 10
        clip: {target: none}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    assert validate_overlaps(root) == []


def test_invalid_overlap_policy_metadata_is_rejected():
    root = _root(
        '<g id="bad" data-patchcreator-overlap-policy="sometimes">'
        '<rect x="0" y="0" width="10" height="10"/>'
        '</g>'
    )
    with pytest.raises(ValueError, match="invalid PatchCreator overlap policy"):
        validate_overlaps(root)
