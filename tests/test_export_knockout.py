from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from patchcreator.svg.export import CompatibilityExportError, ExportOptions, export_svg_text
from patchcreator.validation.geometry import iter_visible_fills

SVG_NS = "http://www.w3.org/2000/svg"


def _svg(body: str) -> str:
    return (
        f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">'
        f"{body}</svg>"
    )


def _areas(svg: str) -> dict[str, float]:
    root = ET.fromstring(svg)
    return {
        item.element_id: float(item.geometry.area)
        for item in iter_visible_fills(root)
        if item.element_id is not None
    }


def _knockout(body: str):
    return export_svg_text(
        _svg(body),
        options=ExportOptions(knockout=True),
    )


def test_knockout_subtracts_later_allow_geometry_from_lower_owner():
    result = _knockout(
        '<g id="lower" data-patchcreator-overlap-policy="knockout">'
        '  <rect id="lower-shape" x="0" y="0" width="10" height="10" fill="#f00"/>'
        '</g>'
        '<g id="upper" data-patchcreator-overlap-policy="allow">'
        '  <rect id="upper-shape" x="5" y="0" width="10" height="10" fill="#fff"/>'
        '</g>'
    )
    areas = _areas(result.svg)
    assert areas["lower-shape"] == pytest.approx(50.0)
    assert areas["upper-shape"] == pytest.approx(100.0)
    assert result.knockout_changed_fragments == 1
    assert result.knockout_removed_fragments == 0

    root = ET.fromstring(result.svg)
    lower = root.find(f".//{{{SVG_NS}}}path[@id='lower-shape']")
    assert lower is not None
    assert lower.attrib["fill-rule"] == "evenodd"


def test_knockout_uses_document_space_for_nested_transforms():
    result = _knockout(
        '<g id="lower" data-patchcreator-overlap-policy="knockout" transform="translate(10 10)">'
        '  <rect id="lower-shape" x="0" y="0" width="10" height="10" fill="#f00"/>'
        '</g>'
        '<g id="upper" data-patchcreator-overlap-policy="allow" transform="translate(15 10)">'
        '  <rect id="upper-shape" x="0" y="0" width="10" height="10" fill="#fff"/>'
        '</g>'
    )
    areas = _areas(result.svg)
    assert areas["lower-shape"] == pytest.approx(50.0)
    assert areas["upper-shape"] == pytest.approx(100.0)


def test_knockout_preserves_multipart_lower_geometry():
    result = _knockout(
        '<g id="lower" data-patchcreator-overlap-policy="knockout">'
        '  <path id="lower-shape" fill="#f00" fill-rule="evenodd" '
        '        d="M0 0H10V10H0Z M20 0H30V10H20Z"/>'
        '</g>'
        '<g id="upper" data-patchcreator-overlap-policy="allow">'
        '  <rect id="upper-shape" x="5" y="0" width="10" height="10" fill="#fff"/>'
        '</g>'
    )
    areas = _areas(result.svg)
    assert areas["lower-shape"] == pytest.approx(150.0)
    assert areas["upper-shape"] == pytest.approx(100.0)


def test_multiple_later_occluders_are_unioned_before_subtraction():
    result = _knockout(
        '<g id="lower" data-patchcreator-overlap-policy="knockout">'
        '  <rect id="lower-shape" x="0" y="0" width="10" height="10" fill="#f00"/>'
        '</g>'
        '<g id="upper-a" data-patchcreator-overlap-policy="allow">'
        '  <rect id="upper-a-shape" x="0" y="0" width="2" height="10" fill="#fff"/>'
        '</g>'
        '<g id="upper-b" data-patchcreator-overlap-policy="allow">'
        '  <rect id="upper-b-shape" x="8" y="0" width="2" height="10" fill="#fff"/>'
        '</g>'
    )
    assert _areas(result.svg)["lower-shape"] == pytest.approx(60.0)
    assert result.knockout_changed_fragments == 1


def test_fully_covered_lower_fragment_is_removed():
    result = _knockout(
        '<g id="lower" data-patchcreator-overlap-policy="knockout">'
        '  <rect id="lower-shape" x="2" y="2" width="4" height="4" fill="#f00"/>'
        '</g>'
        '<g id="upper" data-patchcreator-overlap-policy="allow">'
        '  <rect id="upper-shape" x="0" y="0" width="10" height="10" fill="#fff"/>'
        '</g>'
    )
    assert "lower-shape" not in _areas(result.svg)
    assert result.knockout_changed_fragments == 1
    assert result.knockout_removed_fragments == 1


def test_warn_and_avoid_policies_keep_their_existing_precedence_over_knockout():
    # A warn/avoid declaration means the overlap remains diagnostically
    # significant rather than being silently made acceptable by the other
    # object's knockout declaration.  Only allow/knockout pairs are resolved.
    for policy in ("warn", "avoid"):
        result = _knockout(
            '<g id="lower" data-patchcreator-overlap-policy="knockout">'
            '  <rect id="lower-shape" x="0" y="0" width="10" height="10" fill="#f00"/>'
            '</g>'
            f'<g id="upper" data-patchcreator-overlap-policy="{policy}">'
            '  <rect id="upper-shape" x="5" y="0" width="10" height="10" fill="#fff"/>'
            '</g>'
        )
        assert _areas(result.svg)["lower-shape"] == pytest.approx(100.0)
        assert result.knockout_changed_fragments == 0


def test_stroked_lower_geometry_fails_instead_of_changing_stroke_semantics():
    with pytest.raises(CompatibilityExportError, match="stroked filled geometry"):
        _knockout(
            '<g id="lower" data-patchcreator-overlap-policy="knockout">'
            '  <rect x="0" y="0" width="10" height="10" fill="#f00" '
            '        stroke="#000" stroke-width="1"/>'
            '</g>'
            '<g id="upper" data-patchcreator-overlap-policy="allow">'
            '  <rect x="5" y="0" width="10" height="10" fill="#fff"/>'
            '</g>'
        )


def test_unsupported_non_knockout_paint_is_reported_not_silently_dropped():
    result = _knockout(
        '<g id="lower" data-patchcreator-overlap-policy="knockout">'
        '  <rect x="0" y="0" width="10" height="10" fill="#f00"/>'
        '</g>'
        '<g id="label" data-patchcreator-overlap-policy="allow">'
        '  <text x="2" y="5">TEXT</text>'
        '</g>'
    )
    assert result.warnings
    assert "label" in result.warnings[0]
