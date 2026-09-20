from __future__ import annotations

from pathlib import Path

import pytest

from patchcreator.cli import main
from patchcreator.validation import check_svg


def _write_svg(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "artwork.svg"
    path.write_text(content, encoding="utf-8")
    return path


def test_minimum_stroke_finds_thin_visible_presentation_and_inherited_strokes(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <g stroke="#fff" stroke-width="0.5">
    <path id="inherited" d="M 0 0 L 10 0"/>
  </g>
  <path id="safe" d="M 0 1 L 10 1" stroke="#fff" stroke-width="0.8"/>
  <path id="styled" d="M 0 2 L 10 2" style="stroke:#fff;stroke-width:0.4"/>
</svg>""",
    )
    report = check_svg(path, minimum_stroke_width_mm=0.6)
    assert [finding.element_id for finding in report.findings] == ["inherited", "styled"]
    assert [finding.measured_mm for finding in report.findings] == pytest.approx([0.5, 0.4])
    assert all(finding.code == "stroke-too-thin" for finding in report.findings)
    assert all(finding.threshold_mm == pytest.approx(0.6) for finding in report.findings)


def test_transforms_scale_stroke_but_non_scaling_uses_viewport_units(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="scaled" d="M 0 0 L 10 0" stroke="#fff" stroke-width="1" transform="scale(0.5)"/>
  <path id="non-scaling" d="M 0 1 L 10 1" stroke="#fff" stroke-width="0.8"
        transform="scale(0.1)" vector-effect="non-scaling-stroke"/>
</svg>""",
    )
    report = check_svg(path, minimum_stroke_width_mm=0.6)
    assert [finding.element_id for finding in report.findings] == ["scaled", "non-scaling"]
    assert [finding.measured_mm for finding in report.findings] == pytest.approx(
        [0.5, 0.8 * 25.4 / 96.0]
    )


def test_non_scaling_stroke_uses_css_px_even_when_viewbox_is_physical_mm(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <line id="ordinary" x1="0" y1="0" x2="10" y2="0" stroke="#000" stroke-width="1.5"/>
  <line id="non-scaling" x1="0" y1="1" x2="10" y2="1" stroke="#000" stroke-width="1.5"
        vector-effect="non-scaling-stroke"/>
</svg>""",
    )
    report = check_svg(path, minimum_stroke_width_mm=0.6)
    assert [finding.element_id for finding in report.findings] == ["non-scaling"]
    assert report.findings[0].measured_mm == pytest.approx(1.5 * 25.4 / 96.0)


def test_root_css_pixels_are_converted_to_physical_mm(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="96px" height="96px" viewBox="0 0 96 96">
  <line id="two-user-units" x1="0" y1="0" x2="50" y2="0" stroke="#000" stroke-width="2"/>
</svg>""",
    )
    report = check_svg(path, minimum_stroke_width_mm=0.6)
    assert len(report.findings) == 1
    assert report.findings[0].measured_mm == pytest.approx(2 * 25.4 / 96.0)


def test_absolute_mm_stroke_width_is_measured_physically(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 10 10">
  <line id="physical" x1="0" y1="0" x2="10" y2="0" stroke="#000" stroke-width="0.5mm"/>
</svg>""",
    )
    report = check_svg(path, minimum_stroke_width_mm=0.6)
    assert report.findings[0].measured_mm == pytest.approx(0.5)


def test_hidden_and_definition_geometry_is_ignored(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><path id="definition" d="M0 0L1 0" stroke="#000" stroke-width="0.1"/></defs>
  <g style="display:none"><path id="hidden" d="M0 0L1 0" stroke="#000" stroke-width="0.1"/></g>
  <path id="transparent" d="M0 0L1 0" stroke="#000" stroke-width="0.1" stroke-opacity="0"/>
</svg>""",
    )
    assert check_svg(path, minimum_stroke_width_mm=0.6).findings == ()


def test_small_filled_primitive_reports_dimension_and_area(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <rect id="tiny" x="10" y="10" width="0.5" height="2" fill="#fff"/>
</svg>""",
    )
    report = check_svg(
        path,
        minimum_feature_dimension_mm=0.8,
        minimum_island_area_mm2=1.5,
    )
    by_code = {finding.code: finding for finding in report.findings}
    assert by_code["feature-too-small"].element_id == "tiny"
    assert by_code["feature-too-small"].measured_mm == pytest.approx(0.5)
    assert by_code["island-too-small"].measured_mm2 == pytest.approx(1.0)
    assert by_code["island-too-small"].bounds_mm == pytest.approx((10, 10, 10.5, 12))


def test_compound_path_reports_tiny_detached_island_separately(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="compound" fill="#fff" fill-rule="evenodd"
        d="M 5 5 L 25 5 L 25 25 L 5 25 Z M 40 40 L 40.5 40 L 40.5 40.5 L 40 40.5 Z"/>
</svg>""",
    )
    report = check_svg(
        path,
        minimum_feature_dimension_mm=0.8,
        minimum_island_area_mm2=1.5,
    )
    island_findings = [finding for finding in report.findings if finding.code == "island-too-small"]
    feature_findings = [finding for finding in report.findings if finding.code == "feature-too-small"]
    assert len(island_findings) == 1
    assert island_findings[0].element_id == "compound"
    assert island_findings[0].measured_mm2 == pytest.approx(0.25)
    assert "island" in island_findings[0].message
    # The element as a whole is large; only its detached island is suspect.
    assert feature_findings == []


def test_filled_geometry_honours_nested_transforms(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <g transform="scale(0.5)">
    <rect id="scaled-fill" x="0" y="0" width="1" height="4" fill="#fff"/>
  </g>
</svg>""",
    )
    report = check_svg(path, minimum_feature_dimension_mm=0.8)
    assert len(report.findings) == 1
    assert report.findings[0].code == "feature-too-small"
    assert report.findings[0].measured_mm == pytest.approx(0.5)


def test_curve_and_arc_paths_are_flattened_only_for_analysis(tmp_path: Path):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="curve" fill="#fff" d="M 10 10 C 12 8 18 8 20 10 A 5 5 0 0 1 10 10 Z"/>
</svg>""",
    )
    report = check_svg(
        path,
        minimum_feature_dimension_mm=0.1,
        minimum_island_area_mm2=0.1,
    )
    assert report.findings == ()


def test_cli_check_uses_standard_patch_profile_by_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path id="route" d="M0 0L10 0" fill="none" stroke="#fff" stroke-width="0.4"/>
</svg>""",
    )
    assert main(["check", str(path)]) == 1
    output = capsys.readouterr().out
    assert "stroke-too-thin" in output
    assert "route" in output
    assert "0.4 mm < 0.6 mm" in output


def test_cli_standard_profile_also_checks_small_fills(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <rect id="speck" x="1" y="1" width="0.5" height="0.5" fill="#fff"/>
</svg>""",
    )
    assert main(["check", str(path)]) == 1
    output = capsys.readouterr().out
    assert "feature-too-small" in output
    assert "island-too-small" in output
    assert "0.25 mm² < 1.5 mm²" in output


def test_cli_check_profile_can_disable_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path d="M0 0L10 0" stroke="#fff" stroke-width="0.1"/>
</svg>""",
    )
    assert main(["check", str(path), "--intent", "display-art"]) == 0
    assert "validation disabled" in capsys.readouterr().out


def test_cli_explicit_stroke_threshold_overrides_profile(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(
        tmp_path,
        """<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">
  <path d="M0 0L10 0" fill="none" stroke="#fff" stroke-width="0.4"/>
</svg>""",
    )
    assert main(["check", str(path), "--minimum-stroke-width", "0.3"]) == 0
    assert "OK; profile standard-patch" in capsys.readouterr().out


def test_svg_without_physical_size_gives_actionable_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = _write_svg(
        tmp_path,
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><path d="M0 0L1 1" stroke="#000"/></svg>',
    )
    assert main(["check", str(path)]) == 2
    assert "no physical width" in capsys.readouterr().err
