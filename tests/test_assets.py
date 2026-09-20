from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from patchcreator.components import ComponentRegistry
from patchcreator.config.loader import DesignLoadError, load_design, loads_design
from patchcreator.svg import export_svg_text
from patchcreator.svg.writer import PATCHCREATOR_NS, SVG_NS, render_design


ASSET_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="100mm" height="50mm" viewBox="0 0 100 50">
  <defs>
    <clipPath id="clip"><rect x="0" y="0" width="100" height="50"/></clipPath>
  </defs>
  <g id="art" transform="translate(5 0)">
    <rect id="body" x="0" y="0" width="100" height="50"
          fill="#123456" clip-path="url(#clip)"
          data-patchcreator-fill-role="primary"/>
    <g inkscape:groupmode="layer" inkscape:label="PatchCreator Anchors" style="display:none">
      <circle id="nose-marker" cx="80" cy="20" r="1"
              data-patchcreator-anchor="nose"/>
    </g>
  </g>
</svg>
"""


def _write_design(
    tmp_path: Path,
    *,
    two_assets: bool = False,
    construction_guides: bool = False,
) -> Path:
    (tmp_path / "mascot.svg").write_text(ASSET_SVG, encoding="utf-8")
    second = """
      - id: mascot2
        type: asset
        source: mascot.svg
        width: 10
        roles: {primary: primary}
        clip: {target: none}
""" if two_assets else ""
    design = tmp_path / "patch.yaml"
    design.write_text(
        f"""
version: 0.1
canvas: {{shape: circle, diameter: 80}}
settings:
  construction_guides: {str(construction_guides).lower()}
palette:
  primary: "#336699"
  primary-light:
    from: primary
    lighten: 0.3
layers:
  - id: art
    elements:
      - id: mascot
        type: asset
        source: mascot.svg
        width: 20
        roles: {{primary: primary-light}}
        clip: {{target: none}}
        position:
          mode: cartesian
          x: 10
          y: 0
          self_anchor: nose
{second}
""",
        encoding="utf-8",
    )
    return design


def test_asset_is_builtin_and_relative_path_resolves_from_design(tmp_path: Path):
    assert "asset" in ComponentRegistry().component_types
    design = load_design(_write_design(tmp_path))
    assert design.source_dir == tmp_path.resolve()

    result = render_design(design)
    root = ET.fromstring(result.svg)
    group = root.find(f".//{{{SVG_NS}}}g[@id='mascot']")
    wrapper = root.find(f".//{{{SVG_NS}}}g[@id='mascot-asset']")
    body = root.find(f".//{{{SVG_NS}}}rect[@id='asset-mascot-body']")
    anchor = root.find(f".//{{{SVG_NS}}}circle[@id='asset-mascot-nose-marker']")
    clip = root.find(f".//{{{SVG_NS}}}clipPath[@id='asset-mascot-clip']")

    assert group is not None and wrapper is not None and body is not None and anchor is not None
    assert clip is not None
    # Source anchor: (80,20), inside translate(5,0), then 0.2 scale and
    # centred 20x10 asset => local anchor (7,-1). Placing that anchor at
    # patch-centred (10,0) therefore translates the scene node to (43,41).
    assert group.attrib["transform"] == "matrix(1 0 0 1 43 41)"
    assert wrapper.attrib["transform"] == "matrix(0.2 0 0 0.2 -10 -5)"
    assert group.attrib[f"{{{PATCHCREATOR_NS}}}asset-anchors"] == "nose"
    assert body.attrib["fill"] == design.palette["primary-light"]
    assert body.attrib["fill"] != design.palette["primary"]
    assert body.attrib["clip-path"] == "url(#asset-mascot-clip)"
    assert "display:none" in anchor.attrib["style"]
    assert anchor.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "asset-anchor-source"


def test_asset_anchor_guides_use_resolved_local_anchor_positions(tmp_path: Path):
    design = load_design(_write_design(tmp_path, construction_guides=True))
    rendered = render_design(design).svg
    root = ET.fromstring(rendered)

    guides = root.find(f".//{{{SVG_NS}}}g[@id='mascot-anchor-guides']")
    marker = root.find(f".//{{{SVG_NS}}}g[@id='mascot-anchor-guide-000']")
    circle = marker.find(f"{{{SVG_NS}}}circle") if marker is not None else None

    assert guides is not None and marker is not None and circle is not None
    assert guides.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "asset-anchors"
    assert marker.attrib[f"{{{PATCHCREATOR_NS}}}construction-role"] == "asset-anchor"
    assert marker.attrib[f"{{{PATCHCREATOR_NS}}}anchor-name"] == "nose"
    # The semantic anchor is transformed into asset-component local mm before
    # the scene placement transform is applied: (80,20) under translate(5,0),
    # then centred/scaled to a 20x10 mm asset -> (7,-1).
    assert (circle.attrib["cx"], circle.attrib["cy"], circle.attrib["r"]) == ("7", "-1", "0.8")

    compat = export_svg_text(rendered)
    assert "mascot-anchor-guides" not in compat.svg
    assert "mascot-anchor-guide-000" not in compat.svg


def test_asset_anchor_guides_are_absent_when_construction_guides_disabled(tmp_path: Path):
    root = ET.fromstring(render_design(load_design(_write_design(tmp_path))).svg)
    assert root.find(f".//{{{SVG_NS}}}g[@id='mascot-anchor-guides']") is None


def test_asset_preserves_root_paint_context_and_resolves_root_roles(tmp_path: Path):
    source = tmp_path / "root-style.svg"
    source.write_text(
        f'''<svg xmlns="{SVG_NS}" width="10mm" height="10mm" viewBox="0 0 10 10"
  fill="url(#root-gradient)" stroke="#0000ff" transform="translate(1 2)"
  data-patchcreator-fill-role="primary">
  <defs><linearGradient id="root-gradient"><stop offset="0" stop-color="#ff0000"/></linearGradient></defs>
  <rect id="body" width="10" height="10" style="fill:#111111;stroke:#222222"
    data-patchcreator-fill-role="primary"/>
  <circle id="anchor" cx="5" cy="5" r="1" data-patchcreator-anchor="centre"/>
</svg>''',
        encoding="utf-8",
    )
    design = loads_design(
        f'''version: 0.1
canvas: {{shape: circle, diameter: 80}}
palette: {{primary: "#00ff00"}}
layers:
  - id: art
    elements:
      - id: root-style
        type: asset
        source: {source}
        width: 10
        roles: {{primary: primary}}
        position: {{mode: cartesian, x: 0, y: 0}}
        clip: {{target: none}}
'''
    )
    root = ET.fromstring(render_design(design).svg)
    wrapper = root.find(f".//{{{SVG_NS}}}g[@id='root-style-asset']")
    body = root.find(f".//{{{SVG_NS}}}rect[@id='asset-root-style-body']")
    gradient = root.find(f".//{{{SVG_NS}}}linearGradient[@id='asset-root-style-root-gradient']")
    assert wrapper is not None and body is not None and gradient is not None
    assert wrapper.attrib["fill"] == "#00ff00"
    assert wrapper.attrib["stroke"] == "#0000ff"
    assert body.attrib["fill"] == "#00ff00"
    assert "fill:#00ff00" in body.attrib["style"]
    assert wrapper.attrib["transform"] == "matrix(1 0 0 1 -4 -3)"


def test_asset_preserves_root_class_for_inherited_stylesheet_paint(tmp_path: Path):
    source = tmp_path / "root-class.svg"
    source.write_text(
        f'''<svg xmlns="{SVG_NS}" width="10mm" height="10mm" viewBox="0 0 10 10"
  class="theme">
  <style>.theme {{ fill: #ff0000; stroke: #0000ff; }}</style>
  <rect id="body" width="10" height="10"/>
</svg>''',
        encoding="utf-8",
    )
    design = loads_design(
        f'''version: 0.1
canvas: {{shape: circle, diameter: 80}}
layers:
  - id: art
    elements:
      - id: root-class
        type: asset
        source: {source}
        width: 10
        clip: {{target: none}}
'''
    )

    root = ET.fromstring(render_design(design).svg)
    wrapper = root.find(f".//{{{SVG_NS}}}g[@id='root-class-asset']")
    stylesheet = wrapper.find(f"{{{SVG_NS}}}style") if wrapper is not None else None

    assert wrapper is not None and stylesheet is not None
    assert wrapper.attrib["class"] == "theme"
    assert ".theme" in (stylesheet.text or "")


def test_multiple_asset_instances_have_collision_safe_ids(tmp_path: Path):
    root = ET.fromstring(render_design(load_design(_write_design(tmp_path, two_assets=True))).svg)
    assert root.find(f".//{{{SVG_NS}}}rect[@id='asset-mascot-body']") is not None
    assert root.find(f".//{{{SVG_NS}}}rect[@id='asset-mascot2-body']") is not None
    first_clip = root.find(f".//{{{SVG_NS}}}rect[@id='asset-mascot-body']").attrib["clip-path"]
    second_clip = root.find(f".//{{{SVG_NS}}}rect[@id='asset-mascot2-body']").attrib["clip-path"]
    assert first_clip == "url(#asset-mascot-clip)"
    assert second_clip == "url(#asset-mascot2-clip)"


def test_derived_palette_colours_are_resolved_for_all_renderers():
    design = loads_design(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette:
  base: "#204060"
  lighter: {from: base, lighten: 0.4}
  darker: {from: base, darken: 0.4}
layers:
  - id: art
    elements:
      - id: light-star
        type: star
        size: 2
        fill: lighter
        clip: {target: none}
"""
    )
    assert design.palette["lighter"].startswith("#")
    assert design.palette["darker"].startswith("#")
    assert design.palette["lighter"] != design.palette["base"]
    assert design.palette["darker"] != design.palette["base"]
    svg = render_design(design).svg
    assert f'fill="{design.palette["lighter"]}"' in svg


def test_palette_derivation_errors_are_source_validation_errors():
    with pytest.raises(DesignLoadError, match="unknown colour"):
        loads_design(
            """
version: 0.1
canvas: {shape: circle, diameter: 80}
palette:
  highlight: {from: missing, lighten: 0.2}
"""
        )


def test_asset_rejects_external_references(tmp_path: Path):
    (tmp_path / "bad.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><image href="photo.png"/></svg>',
        encoding="utf-8",
    )
    design_path = tmp_path / "patch.yaml"
    design_path.write_text(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: bad
        type: asset
        source: bad.svg
        width: 10
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="external reference"):
        render_design(load_design(design_path))


def test_asset_requires_viewbox(tmp_path: Path):
    (tmp_path / "bad.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"><circle cx="5" cy="5" r="5"/></svg>',
        encoding="utf-8",
    )
    design_path = tmp_path / "patch.yaml"
    design_path.write_text(
        """
version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: art
    elements:
      - id: bad
        type: asset
        source: bad.svg
        width: 10
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires a viewBox"):
        render_design(load_design(design_path))
