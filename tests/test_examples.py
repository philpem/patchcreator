from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

import patchcreator.components.earth as earth_component
from patchcreator.assets import inspect_asset
from patchcreator.config.loader import load_design
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design
from patchcreator.validation import check_svg


EXAMPLES = Path(__file__).parents[1] / "examples"


def _synthetic_land():
    # Offline land geometry sufficient to exercise projection/rendering without
    # downloading Natural Earth during CI.
    return (
        (
            (-25.0, -12.0),
            (25.0, -12.0),
            (25.0, 12.0),
            (-25.0, 12.0),
            (-25.0, -12.0),
        ),
    )


def test_full_80mm_example_is_deterministic_and_has_expected_structure(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(earth_component, "load_natural_earth_land_rings", _synthetic_land)
    design = load_design(EXAMPLES / "basic-round-patch.yaml")

    first = render_design(design)
    second = render_design(load_design(EXAMPLES / "basic-round-patch.yaml"))
    assert first.svg == second.svg

    root = ET.fromstring(first.svg)
    assert root.attrib["width"] == "80mm"
    assert root.attrib["height"] == "80mm"
    for element_id in (
        "stars",
        "earth",
        "orbit-main",
        "orbit-marker",
        "title",
        "outer-border",
    ):
        assert root.find(f".//*[@id='{element_id}']") is not None

    stars = root.find(f".//{{{SVG_NS}}}g[@id='stars']")
    assert stars is not None
    assert stars.attrib[f"{{{PATCHCREATOR_NS}}}seed"] == "1511506142"
    assert stars.attrib[f"{{{PATCHCREATOR_NS}}}requested-count"] == "12"
    assert int(stars.attrib[f"{{{PATCHCREATOR_NS}}}placed-count"]) > 0

    title = root.find(f".//{{{SVG_NS}}}g[@id='title']")
    assert title is not None
    assert title.attrib[f"{{{PATCHCREATOR_NS}}}text-live"] == "true"


def test_dataset_free_yaml_examples_render_without_warnings():
    for name in (
        "minimal-patch.yaml",
        "trajectory-and-placement.yaml",
        "text-layouts.yaml",
        "reusable-asset-patch.yaml",
    ):
        result = render_design(load_design(EXAMPLES / name))
        assert "<svg" in result.svg, name
        assert not result.warnings, (name, result.warnings)


def test_reusable_asset_example_exposes_documented_anchors_and_roles():
    report = inspect_asset(EXAMPLES / "assets" / "demo-satellite.svg")
    assert set(report.anchors) == {
        "body-centre",
        "dish-tip",
        "left-panel-tip",
        "right-panel-tip",
    }
    assert set(report.colour_roles) == {"accent", "body", "dish", "outline", "panel"}

    root = ET.fromstring(render_design(load_design(EXAMPLES / "reusable-asset-patch.yaml")).svg)
    satellite = root.find(f".//{{{SVG_NS}}}g[@id='satellite']")
    beacon = root.find(f".//{{{SVG_NS}}}g[@id='dish-beacon']")
    assert satellite is not None and beacon is not None
    assert "transform" in satellite.attrib
    assert "transform" in beacon.attrib


def test_validation_risk_demo_exercises_each_current_validator():
    report = check_svg(
        EXAMPLES / "validation-risk-demo.svg",
        minimum_stroke_width_mm=0.6,
        minimum_feature_dimension_mm=0.8,
        minimum_island_area_mm2=1.5,
        minimum_gap_mm=0.6,
        overlap_diagnostics=True,
    )
    codes = {finding.code for finding in report.findings}
    assert "stroke-too-thin" in codes
    assert "feature-too-small" in codes
    assert "island-too-small" in codes
    assert "gap-too-narrow" in codes
    assert "overlap-thread-buildup" in codes
    assert "overlap-knockout-pending" in codes
