import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import loads_design
from patchcreator.svg.writer import (
    INKSCAPE_NS,
    PATCHCREATOR_NS,
    SVG_NS,
    render_design,
)


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


def test_explicit_inherit_uses_design_default_clip():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin: {fixed: 3}
settings:
  default_clip: safe-area
layers:
  - id: art
    elements:
      - id: rim
        type: border
        clip: {target: inherit}
"""
    )
    result = render_design(design)
    root = ET.fromstring(result.svg)
    group = root.find(f".//{{{SVG_NS}}}g[@id='rim']")
    assert group is not None
    assert group.attrib["clip-path"] == "url(#clip-safe-area)"


def test_safe_area_clip_can_add_per_element_inset():
    design = loads_design(
        """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin: {fixed: 3}
layers:
  - id: art
    elements:
      - id: rim
        type: border
        clip: {target: safe-area, inset: 2}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    group = root.find(f".//{{{SVG_NS}}}g[@id='rim']")
    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-element-rim']")
    assert group is not None and clip is not None
    assert group.attrib["clip-path"] == "url(#clip-element-rim)"
    circle = clip.find(f"{{{SVG_NS}}}circle")
    assert circle is not None
    assert circle.attrib["r"] == "35"


def test_negative_clip_inset_produces_outset():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: rim
        type: border
        clip: {target: patch, inset: -2}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-element-rim']")
    assert clip is not None
    circle = clip.find(f"{{{SVG_NS}}}circle")
    assert circle is not None
    assert circle.attrib["r"] == "42"


def test_disabled_clip_preserves_patchcreator_metadata_for_editing():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: rim
        type: border
        clip: {target: safe-area, enabled: false, inset: 1.5}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    group = root.find(f".//{{{SVG_NS}}}g[@id='rim']")
    assert group is not None
    assert "clip-path" not in group.attrib
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}clip-target"] == "safe-area"
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}clip-enabled"] == "false"
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}clip-inset-mm"] == "1.5"


def test_custom_clip_references_named_scene_element():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: mask-source
        type: border
        clip: {target: none}
      - id: clipped
        type: border
        clip: {target: "custom:mask-source"}
"""
    )
    root = ET.fromstring(render_design(design).svg)
    group = root.find(f".//{{{SVG_NS}}}g[@id='clipped']")
    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='clip-element-clipped']")
    assert group is not None and clip is not None
    assert group.attrib["clip-path"] == "url(#clip-element-clipped)"
    use = clip.find(f"{{{SVG_NS}}}use")
    assert use is not None
    assert use.attrib["href"] == "#mask-source"


def test_unknown_custom_clip_target_is_rejected():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: clipped
        type: border
        clip: {target: "custom:no-such-object"}
"""
    )
    with pytest.raises(ValueError, match="unknown custom clip target"):
        render_design(design)


def test_custom_clip_inset_is_rejected_until_arbitrary_offsets_exist():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: source
        type: border
        clip: {target: none}
      - id: clipped
        type: border
        clip: {target: "custom:source", inset: 1}
"""
    )
    with pytest.raises(ValueError, match="cannot use inset/outset yet"):
        render_design(design)
