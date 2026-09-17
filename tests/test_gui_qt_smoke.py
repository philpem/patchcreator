from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from patchcreator.gui.qt_app import MainWindow


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "trajectory-and-placement.yaml"


def _find_item(window: MainWindow, element_id: str):
    for index in range(window.scene_tree.topLevelItemCount()):
        item = window._find_tree_item(window.scene_tree.topLevelItem(index), element_id)
        if item is not None:
            return item
    raise AssertionError(f"scene-tree item {element_id!r} not found")


def test_headless_gui_opens_example_and_structured_edit_round_trips():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(EXAMPLE)
    window.show()
    app.processEvents()

    try:
        assert window.session.source_path == EXAMPLE
        assert window.preview.renderer().isValid()
        assert window.scene_tree.topLevelItemCount() >= 3

        item = _find_item(window, "rendezvous-orbit")
        window.scene_tree.setCurrentItem(item)
        app.processEvents()

        assert window.placement_apply.isEnabled()
        assert window.placement_mode.currentText() == "cartesian"
        assert window.placement_first.text() == "13"
        assert window.placement_second.text() == "-8"

        original = window.session.text
        window.placement_first.setText("14")
        window.placement_second.setText("-7")
        window._apply_placement()
        app.processEvents()

        assert window.session.text != original
        placement = window.session.placement("rendezvous-orbit")
        assert placement.mode == "cartesian"
        assert placement.first == "14"
        assert placement.second == "-7"
        assert window.preview.renderer().isValid()
        assert _find_item(window, "rendezvous-orbit") is not None
    finally:
        # The edit is intentionally not saved; avoid the interactive close
        # confirmation in the headless test.
        window.session.dirty = False
        window.close()
        app.processEvents()
