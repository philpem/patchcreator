import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import QApplication

from patchcreator.gui.drag_edit import viewport_to_canvas
from patchcreator.gui.qt_app import DragSvgWidget


@pytest.mark.parametrize("width,height", [(800, 400), (400, 800)])
def test_preview_circle_stays_round_and_matches_pointer_mapping(width, height):
    app = QApplication.instance() or QApplication([])
    widget = DragSvgWidget()
    widget.resize(width, height)
    widget.load(QByteArray(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><circle cx="40" cy="40" r="39" fill="black"/></svg>'))
    widget.show()
    app.processEvents()
    try:
        assert widget.renderer().aspectRatioMode() == Qt.AspectRatioMode.KeepAspectRatio
        image = widget.grab().toImage()
        cx, cy = width // 2, height // 2
        black_x = [x for x in range(width) if image.pixelColor(x, cy).red() < 10]
        black_y = [y for y in range(height) if image.pixelColor(cx, y).red() < 10]
        assert abs(len(black_x) - len(black_y)) <= 2
        point = viewport_to_canvas(min(black_x), cy, viewport_width=width, viewport_height=height,
                                   canvas_width=80, canvas_height=80)
        assert point == pytest.approx((1, 40), abs=.3)
    finally:
        widget.close()
