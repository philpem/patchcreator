import xml.etree.ElementTree as ET

from patchcreator.config.loader import loads_design
from patchcreator.svg.writer import INKSCAPE_NS, SVG_NS, render_design


def test_render_circle_background_border_and_clips():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  background: space
  safe_margin:
    fixed: 3
palette:
  space: "#000000"
  border: "#ffc928"
settings:
  default_clip: safe-area
  inkscape_metadata: true
layers:
  - id: border
    label: Border
    elements:
      - id: outer-border
        type: border
        inset: 1.2
        stroke:
          colour: border
          width: 1.5
        clip:
          target: none
"""
    )
    result = render_design(design)
    root = ET.fromstring(result.svg)
    assert root.attrib["width"] == "80mm"
    assert root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-safe-area']") is not None
    layer = root.find(f".//{{{SVG_NS}}}g[@id='border']")
    assert layer is not None
    assert layer.attrib[f"{{{INKSCAPE_NS}}}groupmode"] == "layer"
    border = root.find(f".//{{{SVG_NS}}}g[@id='outer-border']/{{{SVG_NS}}}circle")
    assert border is not None
    assert border.attrib["stroke"] == "#ffc928"


def test_allow_unsupported_records_warning():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
layers:
  - id: art
    elements:
      - id: future-earth
        type: earth
"""
    )
    result = render_design(design, allow_unsupported=True)
    assert result.warnings
    assert "future-earth" in result.warnings[0]
