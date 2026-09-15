from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.cli import main
from patchcreator.validation import check_svg, validate_narrow_gaps


def _write_svg(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "gaps.svg"
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">{body}</svg>',
        encoding="utf-8",
    )
    return path


def test_narrow_gap_reports_pair_ids_distance_and_closest_points(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        '<rect id="left" x="0" y="0" width="10" height="10"/>'
        '<rect id="right" x="10.4" y="0" width="10" height="10"/>',
    )
    report = check_svg(path, minimum_gap_mm=0.6)

    assert report.validator_names == ("narrow-gaps",)
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.code == "gap-too-narrow"
    assert finding.element_id == "left"
    assert finding.related_element_id == "right"
    assert finding.measured_mm == pytest.approx(0.4)
    assert finding.threshold_mm == pytest.approx(0.6)
    assert finding.points_mm is not None
    assert abs(finding.points_mm[0][0] - finding.points_mm[1][0]) == pytest.approx(0.4)
    assert "left <-> right" in finding.format()


def test_gap_equal_to_threshold_is_not_reported(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        '<rect id="left" x="0" y="0" width="10" height="10"/>'
        '<rect id="right" x="10.6" y="0" width="10" height="10"/>',
    )
    assert check_svg(path, minimum_gap_mm=0.6).findings == ()


def test_touching_and_overlapping_shapes_are_left_for_overlap_validator(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        '<rect id="left" x="0" y="0" width="10" height="10"/>'
        '<rect id="touch" x="10" y="0" width="5" height="5"/>'
        '<rect id="overlap" x="9" y="6" width="5" height="3"/>',
    )
    assert check_svg(path, minimum_gap_mm=0.6).findings == ()


def test_transforms_and_document_scale_are_measured_in_physical_mm(tmp_path: Path):
    path = tmp_path / "scaled.svg"
    path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="40mm" viewBox="0 0 80 80">
  <rect id="left" x="0" y="0" width="20" height="20"/>
  <rect id="right" x="21" y="0" width="20" height="20" transform="translate(0.2 0)"/>
</svg>""",
        encoding="utf-8",
    )
    # User-space gap is 1.2, but the physical document scale is 0.5 mm/unit.
    report = check_svg(path, minimum_gap_mm=0.7)
    assert len(report.findings) == 1
    assert report.findings[0].measured_mm == pytest.approx(0.6)


def test_disconnected_parts_of_one_compound_path_are_checked():
    root = ET.fromstring(
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="compound" d="M 0 0 H 10 V 10 H 0 Z M 10.4 0 H 20.4 V 10 H 10.4 Z"/>
</svg>"""
    )
    findings = validate_narrow_gaps(root, minimum_mm=0.6)
    assert len(findings) == 1
    assert findings[0].element_id == "compound"
    assert findings[0].related_element_id is None
    assert findings[0].measured_mm == pytest.approx(0.4)
    assert "disconnected filled parts" in findings[0].message


def test_cli_uses_profile_gap_and_supports_one_off_override(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(
        tmp_path,
        '<rect id="left" x="0" y="0" width="10" height="10"/>'
        '<rect id="right" x="10.4" y="0" width="10" height="10"/>',
    )

    assert main(["check", str(path)]) == 1
    output = capsys.readouterr().out
    assert "gap-too-narrow" in output
    assert "left <-> right" in output
    assert "0.4 mm < 0.6 mm" in output

    assert main(["check", str(path), "--minimum-gap", "0.3"]) == 0
    assert "OK; profile standard-patch" in capsys.readouterr().out


def test_negative_gap_threshold_is_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(tmp_path, '<rect x="0" y="0" width="10" height="10"/>')
    assert main(["check", str(path), "--minimum-gap", "-0.1"]) == 2
    assert "--minimum-gap must not be negative" in capsys.readouterr().err
