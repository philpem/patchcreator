from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

import patchcreator.components.earth as earth_component
from patchcreator.config.loader import load_design
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design


EXAMPLE = Path(__file__).parents[1] / "examples" / "lower-earth-patch.yaml"


SYNTHETIC_LAND = (
    (
        (-20.0, -10.0),
        (20.0, -10.0),
        (20.0, 10.0),
        (-20.0, 10.0),
        (-20.0, -10.0),
    ),
)


def test_lower_earth_example_fills_lower_half_and_clips_to_merrow_inner_edge(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        earth_component,
        "load_natural_earth_land_rings",
        lambda: SYNTHETIC_LAND,
    )

    result = render_design(load_design(EXAMPLE))
    assert not result.warnings
    root = ET.fromstring(result.svg)

    earth = root.find(f".//{{{SVG_NS}}}g[@id='lower-earth']")
    assert earth is not None
    assert earth.attrib["transform"] == "matrix(1 0 0 1 40 80)"
    assert earth.attrib[f"{{{PATCHCREATOR_NS}}}earth-render"] == "globe"
    sea = earth.find(f".//{{{SVG_NS}}}circle[@id='lower-earth-sea']")
    assert sea is not None
    assert float(sea.attrib["r"]) == pytest.approx(35.0)

    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-element-lower-earth']")
    assert clip is not None
    clip_shape = clip.find(f"{{{SVG_NS}}}circle")
    assert clip_shape is not None
    assert float(clip_shape.attrib["r"]) == pytest.approx(38.05)

    border = root.find(f".//{{{SVG_NS}}}g[@id='outer-border']")
    assert border is not None
    border_shape = border.find(f"{{{SVG_NS}}}circle")
    assert border_shape is not None
    assert float(border_shape.attrib["r"]) == pytest.approx(38.8)
    assert float(border_shape.attrib["stroke-width"]) == pytest.approx(1.5)
    assert 40.0 - 1.2 - 1.5 / 2.0 == pytest.approx(38.05)
