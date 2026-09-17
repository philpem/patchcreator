"""PySide6 application shell for live PatchCreator YAML editing."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QVBoxLayout,
)
from PySide6.QtSvgWidgets import QSvgWidget

from .session import PreviewResult, PreviewSession, SceneTreeItem


_DEFAULT_DOCUMENT = """version: 0.1
canvas:
  shape: circle
  diameter: 80
layers:
  - id: artwork
    label: Artwork
    elements: []
"""


class MainWindow(QMainWindow):
    def __init__(self, source_path: Path | None = None) -> None:
        super().__init__()
        self.session = PreviewSession(_DEFAULT_DOCUMENT)
        self.setMinimumSize(1050, 600)

        self.scene_tree = QTreeWidget()
        self.scene_tree.setHeaderLabels(["Name", "Type", "ID", "Visible"])
        self.scene_tree.setMinimumWidth(230)
        self.scene_tree.setAlternatingRowColors(True)
        self.scene_tree.currentItemChanged.connect(self._tree_selection_changed)

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview = QSvgWidget()
        self.preview.setMinimumSize(320, 320)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumBlockCount(200)
        self.diagnostics.setMaximumHeight(130)

        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(self.scene_tree)
        horizontal.addWidget(self.editor)
        horizontal.addWidget(self.preview)
        horizontal.setStretchFactor(0, 0)
        horizontal.setStretchFactor(1, 1)
        horizontal.setStretchFactor(2, 1)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(horizontal, 1)
        layout.addWidget(self.diagnostics)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._render_from_editor)
        self.editor.textChanged.connect(self._source_changed)

        self._build_actions()

        if source_path is not None:
            self.open_path(source_path)
        else:
            self.editor.setPlainText(self.session.text)
            self.session.dirty = False
            self._render_from_editor()
            self._update_title()

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_dialog)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As…", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        render_action = QAction("&Render now", self)
        render_action.setShortcut("Ctrl+R")
        render_action.triggered.connect(self._render_from_editor)
        self.menuBar().addAction(render_action)

    def _source_changed(self) -> None:
        self.session.set_text(self.editor.toPlainText())
        self._update_title()
        self._timer.start()

    def _render_from_editor(self) -> None:
        self.session.set_text(self.editor.toPlainText())
        self._show_result(self.session.render())

    def _tree_item(self, node: SceneTreeItem) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            [node.label, node.kind, node.id, "yes" if node.visible else "no"]
        )
        for child in node.children:
            item.addChild(self._tree_item(child))
        return item

    def _refresh_tree(self, nodes: tuple[SceneTreeItem, ...]) -> None:
        selected_id = None
        current = self.scene_tree.currentItem()
        if current is not None:
            selected_id = current.text(2)

        self.scene_tree.blockSignals(True)
        self.scene_tree.clear()
        selected_item: QTreeWidgetItem | None = None
        for node in nodes:
            item = self._tree_item(node)
            self.scene_tree.addTopLevelItem(item)
            if selected_id:
                selected_item = selected_item or self._find_tree_item(item, selected_id)
        self.scene_tree.expandAll()
        if selected_item is not None:
            self.scene_tree.setCurrentItem(selected_item)
        for column in range(4):
            self.scene_tree.resizeColumnToContents(column)
        self.scene_tree.blockSignals(False)

    def _find_tree_item(self, item: QTreeWidgetItem, node_id: str) -> QTreeWidgetItem | None:
        if item.text(2) == node_id:
            return item
        for index in range(item.childCount()):
            found = self._find_tree_item(item.child(index), node_id)
            if found is not None:
                return found
        return None

    def _tree_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            return
        self.statusBar().showMessage(
            f"Selected {current.text(1)} {current.text(2)} — "
            f"visible: {current.text(3)}"
        )

    def _show_result(self, result: PreviewResult) -> None:
        if result.svg is not None:
            self.preview.load(QByteArray(result.svg.encode("utf-8")))
        self._refresh_tree(result.tree)

        lines: list[str] = []
        if result.error:
            lines.append(result.error)
        lines.extend(f"warning: {warning}" for warning in result.warnings)
        self.diagnostics.setPlainText("\n".join(lines))

        if result.error:
            self.statusBar().showMessage("Preview has errors; showing last valid render and scene tree")
        elif result.warnings:
            self.statusBar().showMessage(f"Rendered with {len(result.warnings)} warning(s)")
        else:
            self.statusBar().showMessage("Rendered successfully")

    def _update_title(self) -> None:
        marker = "*" if self.session.dirty else ""
        self.setWindowTitle(f"{self.session.display_name}{marker} — PatchCreator")

    def open_dialog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open PatchCreator design",
            str(self.session.source_path.parent if self.session.source_path else Path.cwd()),
            "PatchCreator YAML (*.yaml *.yml);;All files (*)",
        )
        if filename:
            self.open_path(Path(filename))

    def open_path(self, path: Path) -> None:
        try:
            result = self.session.load(path)
        except OSError as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        self.editor.blockSignals(True)
        self.editor.setPlainText(self.session.text)
        self.editor.blockSignals(False)
        self._show_result(result)
        self._update_title()

    def save(self) -> None:
        self.session.set_text(self.editor.toPlainText())
        if self.session.source_path is None:
            self.save_as()
            return
        try:
            path = self.session.save()
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}")
        self._update_title()

    def save_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save PatchCreator design",
            str(self.session.source_path or (Path.cwd() / "patch.yaml")),
            "PatchCreator YAML (*.yaml *.yml);;All files (*)",
        )
        if not filename:
            return
        self.session.set_text(self.editor.toPlainText())
        try:
            path = self.session.save(Path(filename))
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}")
        self._update_title()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API name
        if not self.session.dirty:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "Close without saving your changes?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Discard:
            event.accept()
        else:
            event.ignore()


def run_gui(source_path: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(source_path)
    window.show()
    return int(app.exec())
