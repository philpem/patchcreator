from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

from patchcreator.config.loader import load_design
from patchcreator.gui.preview import qt_preview_svg
from patchcreator.gui.qt_app import DragSvgWidget
from patchcreator.svg.writer import render_design


def test_preview_actually_paints_curved_text():
    app = QApplication.instance() or QApplication([])
    example = Path(__file__).resolve().parents[1] / "examples/text-layouts.yaml"
    svg = render_design(load_design(example)).svg
    widget = DragSvgWidget()
    widget.resize(600, 600)
    widget.load(QByteArray(qt_preview_svg(svg).encode()))
    widget.show()
    app.processEvents()
    try:
        painted = widget.grab().toImage()
        root = ET.fromstring(svg)
        for parent in root.iter():
            for child in list(parent):
                if child.tag.endswith("}text") and child.find("{http://www.w3.org/2000/svg}textPath") is not None:
                    parent.remove(child)
        widget.load(QByteArray(qt_preview_svg(ET.tostring(root, encoding="unicode")).encode()))
        app.processEvents()
        without_text = widget.grab().toImage()
        # The old preview was pixel-identical with and without curved text.
        assert painted != without_text
        changed = sum(painted.pixel(x, y) != without_text.pixel(x, y)
                      for x in range(100, 500) for y in range(20, 160))
        assert changed > 100
    finally:
        widget.close()
