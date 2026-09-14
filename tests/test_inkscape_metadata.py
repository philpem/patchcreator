import xml.etree.ElementTree as ET

from patchcreator.config.loader import loads_design
from patchcreator.svg.writer import INKSCAPE_NS, SVG_NS, render_design


def test_inkscape_metadata_can_be_disabled_without_changing_layer_structure():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
settings:
  inkscape_metadata: false
layers:
  - id: art
    label: Artwork
    elements:
      - id: rim
        type: border
        clip: {target: none}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    layer = root.find(f".//{{{SVG_NS}}}g[@id='art']")
    element = root.find(f".//{{{SVG_NS}}}g[@id='rim']")
    assert layer is not None and element is not None
    assert f"{{{INKSCAPE_NS}}}groupmode" not in layer.attrib
    assert f"{{{INKSCAPE_NS}}}label" not in layer.attrib
    assert f"{{{INKSCAPE_NS}}}label" not in element.attrib


def test_inkscape_metadata_labels_layers_when_enabled():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
settings:
  inkscape_metadata: true
layers:
  - id: art
    label: Artwork
    elements: []
"""
    )
    root = ET.fromstring(render_design(design).svg)
    layer = root.find(f".//{{{SVG_NS}}}g[@id='art']")
    assert layer is not None
    assert layer.attrib[f"{{{INKSCAPE_NS}}}groupmode"] == "layer"
    assert layer.attrib[f"{{{INKSCAPE_NS}}}label"] == "Artwork"
