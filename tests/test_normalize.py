from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.assets import inspect_asset, normalize_asset
from patchcreator.cli import main

SVG_NS = "http://www.w3.org/2000/svg"


def test_inspect_reports_bounds_anchors_roles_and_ignores_hidden_defs(tmp_path: Path):
    source = tmp_path / "asset.svg"
    source.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0 0 100 50">
  <defs><rect x="-1000" y="-1000" width="2000" height="2000"/></defs>
  <g transform="translate(10 5)">
    <rect x="0" y="0" width="20" height="10" fill="#123456"
          data-patchcreator-fill-role="primary"/>
    <circle cx="90" cy="40" r="2" style="display:none"
            data-patchcreator-anchor="nose"/>
  </g>
</svg>""",
        encoding="utf-8",
    )

    report = inspect_asset(source)
    assert report.viewbox == pytest.approx((0, 0, 100, 50))
    assert report.physical_size_mm == pytest.approx((20, 10))
    assert report.bounds is not None
    assert (report.bounds.min_x, report.bounds.min_y, report.bounds.max_x, report.bounds.max_y) == pytest.approx(
        (10, 5, 30, 15)
    )
    assert report.anchors == ("nose",)
    assert report.colour_roles == ("primary",)
    assert report.transform_count == 1
    assert report.unsupported_geometry == ()


def test_fix_viewbox_and_flatten_safe_primitive_transform(tmp_path: Path):
    source = tmp_path / "asset.svg"
    output = tmp_path / "normal.svg"
    source.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg">
  <rect id="body" x="1" y="2" width="10" height="5" transform="translate(5 7) scale(2)"/>
</svg>""",
        encoding="utf-8",
    )

    report = normalize_asset(
        source,
        output=output,
        fix_viewbox=True,
        padding=1,
        flatten_safe_transforms=True,
    )
    assert report.flattened_transform_count == 1
    assert report.transform_count == 0
    assert report.viewbox == pytest.approx((6, 10, 22, 12))

    root = ET.parse(output).getroot()
    rect = root.find(f"{{{SVG_NS}}}rect")
    assert rect is not None
    assert "transform" not in rect.attrib
    assert float(rect.attrib["x"]) == pytest.approx(7)
    assert float(rect.attrib["y"]) == pytest.approx(11)
    assert float(rect.attrib["width"]) == pytest.approx(20)
    assert float(rect.attrib["height"]) == pytest.approx(10)


def test_fix_viewbox_refuses_unknown_visible_geometry(tmp_path: Path):
    source = tmp_path / "asset.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="10">hello</text><rect width="10" height="10"/></svg>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported visible geometry.*text"):
        normalize_asset(source, output=tmp_path / "out.svg", fix_viewbox=True)


def test_path_bounds_are_conservative_for_bezier_control_points(tmp_path: Path):
    source = tmp_path / "asset.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M 0 0 C 5 20 15 20 20 0"/></svg>',
        encoding="utf-8",
    )
    report = inspect_asset(source)
    assert report.bounds is not None
    assert report.bounds.min_x == pytest.approx(0)
    assert report.bounds.max_x == pytest.approx(20)
    assert report.bounds.max_y == pytest.approx(20)


def test_cli_normalize_inspects_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    source = tmp_path / "asset.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" data-patchcreator-anchor="centre-pin"/></svg>',
        encoding="utf-8",
    )
    assert main(["normalize", str(source)]) == 0
    output = capsys.readouterr().out
    assert "viewBox: 0 0 10 10" in output
    assert "geometry-bounds: 1,1 9,9" in output
    assert "anchors: centre-pin" in output


def test_cli_mutation_requires_explicit_destination(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    source = tmp_path / "asset.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>',
        encoding="utf-8",
    )
    assert main(["normalize", str(source), "--fix-viewbox"]) == 2
    assert "--output FILE or --in-place" in capsys.readouterr().err
