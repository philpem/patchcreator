"""Optional consumer-level regressions: count glyphs Inkscape actually lays out."""

from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from patchcreator.config.loader import load_design
from patchcreator.svg import export_svg_text
from patchcreator.svg.writer import render_design
from patchcreator.validation.geometry import iter_visible_fills

INKSCAPE = shutil.which("inkscape")
pytestmark = pytest.mark.skipif(INKSCAPE is None, reason="Inkscape is not installed")
SVG = "{http://www.w3.org/2000/svg}"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("example,compat", [
    ("trajectory-and-placement", False),
    ("text-layouts", False),
    ("text-layouts", True),
])
def test_inkscape_places_every_curved_text_glyph(example, compat, tmp_path):
    svg = render_design(load_design(EXAMPLES / f"{example}.yaml")).svg
    if compat:
        svg = export_svg_text(svg).svg
    original = ET.fromstring(svg)
    labels = {
        node.get("id"): node.find(f"{SVG}textPath").text
        for node in original.iter(f"{SVG}text")
        if node.find(f"{SVG}textPath") is not None
    }
    source = tmp_path / "input.svg"
    output = tmp_path / "outlined.svg"
    source.write_text(svg, encoding="utf-8")
    result = subprocess.run([
        INKSCAPE, str(source),
        f"--actions=select-by-element:text;object-to-path;export-filename:{output};export-do",
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    rendered = ET.parse(output).getroot()
    for element_id, text in labels.items():
        group = rendered.find(f".//{SVG}g[@id='{element_id}']")
        assert group is not None, (element_id, result.stderr)
        glyphs = list(group.iter(f"{SVG}path"))
        assert len(glyphs) == len(text.replace(" ", "")), (element_id, text)
        if element_id == "top-title-text":
            ids = {node.get("id") for node in glyphs}
            bounds = [item.geometry.bounds for item in iter_visible_fills(rendered) if item.element_id in ids]
            assert bounds
            assert max(box[3] for box in bounds) < 32  # Curved above the centre, not horizontal at y=40.
