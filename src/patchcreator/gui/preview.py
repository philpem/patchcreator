"""Prepare an ephemeral SVG for Qt's more limited SVG renderer."""

import xml.etree.ElementTree as ET

from patchcreator.svg.text_path_outline import outline_arc_text


def qt_preview_svg(svg: str) -> str:
    """Outline curved text without changing the editable master or its guides.

    QSvgRenderer accepts documents containing textPath but silently omits the
    text. Work on a separate tree and leave overlays, IDs and placement intact.
    Font/layout errors propagate so the UI can retain its last good preview.
    """
    root = ET.fromstring(svg)
    outline_arc_text(root)
    return ET.tostring(root, encoding="unicode")
