from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from patchcreator.svg import export as export_module
from patchcreator.svg.export import ExportOptions, export_svg_text
from patchcreator.svg.text_outline import (
    FontResolution,
    TextOutlineError,
    TextOutlineResult,
    _resolve_fonts,
    outline_text_with_inkscape,
)

SVG_NS = "http://www.w3.org/2000/svg"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"


def _root(body: str) -> ET.Element:
    return ET.fromstring(
        f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">{body}</svg>'
    )


def test_font_preflight_resolves_requested_family(monkeypatch):
    monkeypatch.setattr(
        "patchcreator.svg.text_outline._fontconfig_match",
        lambda executable, family, *, weight, style: (
            "DejaVu Sans",
            "Bold Oblique",
            "/fonts/DejaVuSans-BoldOblique.ttf",
        ),
    )
    root = _root(
        '<text id="title" font-family="DejaVu Sans" font-weight="700" '
        'font-style="italic">PATCH</text>'
    )
    resolutions, warnings = _resolve_fonts(root, allow_substitution=False, fc_match="fc-match")
    assert len(resolutions) == 1
    assert resolutions[0].resolved_family == "DejaVu Sans"
    assert resolutions[0].resolved_style == "Bold Oblique"
    assert not resolutions[0].substituted
    assert warnings == ()


def test_font_preflight_reports_or_rejects_substitution(monkeypatch):
    monkeypatch.setattr(
        "patchcreator.svg.text_outline._fontconfig_match",
        lambda executable, family, *, weight, style: (
            "Noto Sans",
            "Regular",
            "/fonts/NotoSans-Regular.ttf",
        ),
    )
    root = _root('<text id="title" font-family="Missing Mission Font">PATCH</text>')

    with pytest.raises(TextOutlineError, match="allow-font-substitution"):
        _resolve_fonts(root, allow_substitution=False, fc_match="fc-match")

    resolutions, warnings = _resolve_fonts(root, allow_substitution=True, fc_match="fc-match")
    assert resolutions[0].substituted
    assert resolutions[0].resolved_family == "Noto Sans"
    assert any("font substitution" in warning for warning in warnings)


def test_text_to_path_requires_inkscape_when_live_text_exists(monkeypatch):
    monkeypatch.setattr("patchcreator.svg.text_outline.shutil.which", lambda executable: None)
    with pytest.raises(TextOutlineError, match="requires Inkscape"):
        outline_text_with_inkscape(_root('<text id="title">PATCH</text>'))


def test_text_to_path_noops_without_text_even_without_inkscape(monkeypatch):
    monkeypatch.setattr("patchcreator.svg.text_outline.shutil.which", lambda executable: None)
    root = _root('<circle cx="40" cy="40" r="10"/>')
    result = outline_text_with_inkscape(root)
    assert result.root is root
    assert result.converted_text_count == 0


def test_export_outlines_before_removing_text_baseline(monkeypatch):
    seen_baseline = False

    def fake_outline(root, *, allow_substitution=False):
        nonlocal seen_baseline
        baseline = root.find(f".//{{{SVG_NS}}}path[@id='title-baseline']")
        seen_baseline = baseline is not None
        text = root.find(f".//{{{SVG_NS}}}text[@id='title-text']")
        assert text is not None
        parent = next(parent for parent in root.iter() if text in list(parent))
        index = list(parent).index(text)
        parent.remove(text)
        parent.insert(
            index,
            ET.Element(
                f"{{{SVG_NS}}}path",
                {"id": "title-text", "d": "M 10,10 L 20,10 L 20,15 Z", "fill": "#ffffff"},
            ),
        )
        return TextOutlineResult(
            root=root,
            converted_text_count=1,
            font_resolutions=(
                FontResolution(
                    element_id="title-text",
                    requested_families=("DejaVu Sans",),
                    requested_weight="700",
                    requested_style="normal",
                    resolved_family="DejaVu Sans",
                    resolved_style="Bold",
                    font_file="/fonts/DejaVuSans-Bold.ttf",
                ),
            ),
        )

    monkeypatch.setattr(export_module, "outline_text_with_inkscape", fake_outline)
    svg = f'''<svg xmlns="{SVG_NS}" xmlns:patchcreator="{PATCHCREATOR_NS}"
      width="80mm" height="80mm" viewBox="0 0 80 80">
      <path id="title-baseline" d="M10,40 A30,30 0 0 1 70,40"
            patchcreator:construction-role="text-baseline"/>
      <text id="title-text" font-family="DejaVu Sans" font-weight="700">
        <textPath href="#title-baseline" startOffset="50%">PATCH</textPath>
      </text>
    </svg>'''
    result = export_svg_text(svg, options=ExportOptions(text_mode="paths"))
    root = ET.fromstring(result.svg)

    assert seen_baseline
    assert result.outlined_text_count == 1
    assert root.find(f".//{{{SVG_NS}}}text") is None
    assert root.find(f".//{{{SVG_NS}}}path[@id='title-text']") is not None
    assert root.find(f".//*[@id='title-baseline']") is None
