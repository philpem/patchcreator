from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from patchcreator.svg.export import (
    ExportOptions,
    export_svg_file,
    export_svg_text,
)

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_export_expands_internal_use_and_prunes_definition():
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs>
    <g id="glyph"><circle id="dot" cx="0" cy="0" r="2" fill="#fff"/></g>
    <linearGradient id="unused"><stop offset="0" stop-color="#000"/></linearGradient>
  </defs>
  <use id="instance" href="#glyph" x="10" y="20" transform="scale(2)"/>
</svg>"""
    )
    root = _root(result.svg)
    assert result.expanded_use_count == 1
    assert not root.findall(f".//{{{SVG_NS}}}use")
    assert root.find(f".//{{{SVG_NS}}}g[@id='instance']") is not None
    assert root.find(f".//{{{SVG_NS}}}circle") is not None
    assert result.pruned_defs_count >= 1
    assert root.find(f".//*[@id='unused']") is None


def test_export_removes_debug_construction_and_authoring_metadata():
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" xmlns:inkscape="{INKSCAPE_NS}"
  xmlns:patchcreator="{PATCHCREATOR_NS}" width="80mm" height="80mm" viewBox="0 0 80 80"
  patchcreator:design-version="0.1">
  <g id="art" inkscape:groupmode="layer" inkscape:label="Art"
     data-patchcreator-overlap-policy="warn">
    <circle cx="40" cy="40" r="10" fill="#fff"/>
    <path id="baseline" d="M0 0L10 0" patchcreator:construction-role="text-baseline"/>
  </g>
  <g id="patchcreator-validation" inkscape:groupmode="layer"
     patchcreator:role="validation-overlay"><rect width="5" height="5"/></g>
</svg>"""
    )
    root = _root(result.svg)
    assert result.removed_debug_layer_count == 1
    assert result.removed_construction_count == 1
    assert root.find(f".//*[@id='baseline']") is None
    assert root.find(f".//*[@id='patchcreator-validation']") is None
    assert all(not key.startswith("data-patchcreator-") for element in root.iter() for key in element.attrib)
    assert all(not key.startswith("{" + INKSCAPE_NS + "}") for element in root.iter() for key in element.attrib)
    assert all(not key.startswith("{" + PATCHCREATOR_NS + "}") for element in root.iter() for key in element.attrib)


def test_export_preserves_live_text_by_default():
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <text id="title" x="40" y="10">PATCHCREATOR</text>
</svg>"""
    )
    root = _root(result.svg)
    text = root.find(f".//{{{SVG_NS}}}text")
    assert text is not None
    assert text.text == "PATCHCREATOR"


def test_text_to_path_mode_is_noop_without_text():
    svg = f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80"/>'
    result = export_svg_text(svg, options=ExportOptions(text_mode="paths"))
    assert result.outlined_text_count == 0
    assert not _root(result.svg).findall(f".//{{{SVG_NS}}}text")


def test_safe_leaf_transform_is_flattened():
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <rect id="shape" x="1" y="2" width="3" height="4" transform="translate(5 6) scale(2)"/>
</svg>"""
    )
    root = _root(result.svg)
    rect = root.find(f".//{{{SVG_NS}}}rect")
    assert rect is not None
    assert rect.get("transform") is None
    assert result.flattened_transform_count == 1


def test_export_can_keep_metadata_and_use_when_requested():
    result = export_svg_text(
        f"""<svg xmlns="{SVG_NS}" xmlns:inkscape="{INKSCAPE_NS}"
  xmlns:patchcreator="{PATCHCREATOR_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <defs><circle id="dot" r="2"/></defs>
  <use href="#dot" inkscape:label="copy" data-patchcreator-role="demo"/>
</svg>""",
        options=ExportOptions(
            expand_use=False,
            flatten_safe_transforms=False,
            remove_construction=False,
            strip_inkscape_metadata=False,
            strip_patchcreator_metadata=False,
            prune_unused_defs=False,
        ),
    )
    root = _root(result.svg)
    use = root.find(f".//{{{SVG_NS}}}use")
    assert use is not None
    assert use.get(f"{{{INKSCAPE_NS}}}label") == "copy"
    assert use.get("data-patchcreator-role") == "demo"


def test_export_file_keeps_source_unchanged(tmp_path: Path):
    source = tmp_path / "master.svg"
    output = tmp_path / "compat.svg"
    original = f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80"><circle r="2"/></svg>'
    source.write_text(original, encoding="utf-8")

    result = export_svg_file(source, output)

    assert output.read_text(encoding="utf-8") == result.svg
    assert source.read_text(encoding="utf-8") == original
