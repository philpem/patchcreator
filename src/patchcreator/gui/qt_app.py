"""PySide6 application shell for live PatchCreator YAML editing."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QVBoxLayout,
)
from PySide6.QtSvgWidgets import QSvgWidget

from .session import PreviewResult, PreviewSession, SceneTreeItem
from .source_edit import SourceEditError


_DEFAULT_DOCUMENT = """version: 0.1
canvas:
  shape: circle
  diameter: 80
profile:
  intent: standard-patch
layers:
  - id: artwork
    label: Artwork
    elements: []
"""


class MainWindow(QMainWindow):
    def __init__(self, source_path: Path | None = None) -> None:
        super().__init__()
        self.session = PreviewSession(_DEFAULT_DOCUMENT)
        self.setMinimumSize(1150, 650)

        self.scene_tree = QTreeWidget()
        self.scene_tree.setHeaderLabels(["Name", "Type", "ID", "Visible"])
        self.scene_tree.setMinimumWidth(250)
        self.scene_tree.setAlternatingRowColors(True)
        self.scene_tree.currentItemChanged.connect(self._tree_selection_changed)

        self.placement_box = QGroupBox("Placement")
        placement_form = QFormLayout(self.placement_box)
        self.placement_target = QLabel("Select an element")
        self.placement_mode = QComboBox()
        self.placement_mode.addItems(["cartesian", "polar"])
        self.placement_mode.currentTextChanged.connect(self._placement_mode_changed)
        self.placement_first_label = QLabel("x")
        self.placement_second_label = QLabel("y")
        self.placement_first = QLineEdit()
        self.placement_second = QLineEdit()
        self.placement_apply = QPushButton("Apply placement")
        self.placement_apply.clicked.connect(self._apply_placement)
        placement_form.addRow("Element", self.placement_target)
        placement_form.addRow("Mode", self.placement_mode)
        placement_form.addRow(self.placement_first_label, self.placement_first)
        placement_form.addRow(self.placement_second_label, self.placement_second)
        placement_form.addRow(self.placement_apply)
        self._placement_element_id: str | None = None
        self._set_placement_enabled(False)

        self.margin_box = QGroupBox("Canvas safe margin")
        margin_form = QFormLayout(self.margin_box)
        self.margin_mode = QComboBox()
        self.margin_mode.addItems(["fixed", "percent"])
        self.margin_mode.currentTextChanged.connect(self._margin_mode_changed)
        self.margin_value = QLineEdit()
        self.margin_minimum = QLineEdit()
        self.margin_maximum = QLineEdit()
        self.margin_apply = QPushButton("Apply safe margin")
        self.margin_apply.clicked.connect(self._apply_safe_margin)
        margin_form.addRow("Mode", self.margin_mode)
        margin_form.addRow("Value", self.margin_value)
        margin_form.addRow("Minimum", self.margin_minimum)
        margin_form.addRow("Maximum", self.margin_maximum)
        margin_form.addRow(self.margin_apply)
        self._margin_mode_changed("fixed")

        self.clip_box = QGroupBox("Clip")
        clip_form = QFormLayout(self.clip_box)
        self.clip_explicit = QCheckBox("Explicit clip mapping")
        self.clip_explicit.toggled.connect(self._clip_explicit_toggled)
        self.clip_target = QComboBox()
        self.clip_target.setEditable(True)
        self.clip_target.addItems(["inherit", "none", "patch", "safe-area"])
        self.clip_enabled = QCheckBox("Enabled")
        self.clip_enabled.setChecked(True)
        self.clip_inset = QLineEdit("0")
        self.clip_apply = QPushButton("Apply clip")
        self.clip_apply.clicked.connect(self._apply_clip)
        clip_form.addRow(self.clip_explicit)
        clip_form.addRow("Target", self.clip_target)
        clip_form.addRow(self.clip_enabled)
        clip_form.addRow("Inset / outset", self.clip_inset)
        clip_form.addRow(self.clip_apply)
        self._clip_element_id: str | None = None
        self._set_clip_enabled(False)

        self.seed_box = QGroupBox("Starfield seed")
        seed_form = QFormLayout(self.seed_box)
        self.seed_configured = QLabel("—")
        self.seed_resolved = QLabel("—")
        seed_form.addRow("Configured", self.seed_configured)
        seed_form.addRow("Current render", self.seed_resolved)
        seed_buttons = QWidget()
        seed_buttons_layout = QHBoxLayout(seed_buttons)
        seed_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.seed_lock = QPushButton("Lock current")
        self.seed_regenerate = QPushButton("Regenerate")
        self.seed_auto = QPushButton("Auto")
        self.seed_lock.clicked.connect(self._lock_seed)
        self.seed_regenerate.clicked.connect(self._regenerate_seed)
        self.seed_auto.clicked.connect(self._auto_seed)
        seed_buttons_layout.addWidget(self.seed_lock)
        seed_buttons_layout.addWidget(self.seed_regenerate)
        seed_buttons_layout.addWidget(self.seed_auto)
        seed_form.addRow(seed_buttons)
        self._seed_element_id: str | None = None
        self._set_seed_enabled(False, resolved=False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.scene_tree, 1)
        left_layout.addWidget(self.margin_box, 0)
        left_layout.addWidget(self.placement_box, 0)
        left_layout.addWidget(self.clip_box, 0)
        left_layout.addWidget(self.seed_box, 0)

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview = QSvgWidget()
        self.preview.setMinimumSize(320, 320)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumBlockCount(300)
        self.diagnostics.setMaximumHeight(160)

        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.addWidget(left_panel)
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

        view_menu = self.menuBar().addMenu("&View")
        self.validation_action = QAction("Show &validation overlay", self)
        self.validation_action.setCheckable(True)
        self.validation_action.setShortcut("Ctrl+Shift+V")
        self.validation_action.toggled.connect(self._validation_toggled)
        view_menu.addAction(self.validation_action)

        render_action = QAction("&Render now", self)
        render_action.setShortcut("Ctrl+R")
        render_action.triggered.connect(self._render_from_editor)
        self.menuBar().addAction(render_action)

    def _validation_toggled(self, enabled: bool) -> None:
        self.session.set_validation_enabled(enabled)
        self._render_from_editor()

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
        if selected_item is not None:
            self._load_placement_for_item(selected_item)
            self._load_clip_for_item(selected_item)
            self._load_seed_for_item(selected_item)
        else:
            self._placement_element_id = None
            self._set_placement_enabled(False)
            self._clip_element_id = None
            self._set_clip_enabled(False)
            self._seed_element_id = None
            self.seed_configured.setText("—")
            self.seed_resolved.setText("—")
            self._set_seed_enabled(False, resolved=False)

    def _find_tree_item(self, item: QTreeWidgetItem, node_id: str) -> QTreeWidgetItem | None:
        if item.text(2) == node_id:
            return item
        for index in range(item.childCount()):
            found = self._find_tree_item(item.child(index), node_id)
            if found is not None:
                return found
        return None

    def _margin_mode_changed(self, mode: str) -> None:
        percent = mode == "percent"
        self.margin_minimum.setEnabled(percent)
        self.margin_maximum.setEnabled(percent)

    def _load_safe_margin(self) -> None:
        try:
            state = self.session.safe_margin()
        except SourceEditError as exc:
            self.margin_value.setText(str(exc))
            self.margin_mode.setEnabled(False)
            self.margin_value.setEnabled(False)
            self.margin_minimum.setEnabled(False)
            self.margin_maximum.setEnabled(False)
            self.margin_apply.setEnabled(False)
            return

        self.margin_mode.setEnabled(True)
        self.margin_value.setEnabled(True)
        self.margin_apply.setEnabled(True)
        self.margin_mode.blockSignals(True)
        self.margin_mode.setCurrentText(state.mode)
        self.margin_mode.blockSignals(False)
        self.margin_value.setText(str(state.value))
        self.margin_minimum.setText("" if state.minimum is None else str(state.minimum))
        self.margin_maximum.setText("" if state.maximum is None else str(state.maximum))
        self._margin_mode_changed(state.mode)

    def _apply_safe_margin(self) -> None:
        mode = self.margin_mode.currentText()
        try:
            updated = self.session.set_safe_margin(
                mode=mode,  # type: ignore[arg-type]
                value=self.margin_value.text(),
                minimum=self.margin_minimum.text() if mode == "percent" else None,
                maximum=self.margin_maximum.text() if mode == "percent" else None,
            )
        except SourceEditError as exc:
            QMessageBox.warning(self, "Safe-margin edit failed", str(exc))
            return
        self._replace_source_and_render(updated)

    def _set_clip_enabled(self, selected: bool) -> None:
        self.clip_explicit.setEnabled(selected)
        self.clip_apply.setEnabled(selected)
        explicit = selected and self.clip_explicit.isChecked()
        self.clip_target.setEnabled(explicit)
        self.clip_enabled.setEnabled(explicit)
        self.clip_inset.setEnabled(explicit)

    def _clip_explicit_toggled(self, checked: bool) -> None:
        del checked
        self._set_clip_enabled(self._clip_element_id is not None)

    def _load_clip_for_item(self, current: QTreeWidgetItem) -> None:
        self._clip_element_id = None
        if current.text(1) == "layer":
            self.clip_explicit.blockSignals(True)
            self.clip_explicit.setChecked(False)
            self.clip_explicit.blockSignals(False)
            self._set_clip_enabled(False)
            return

        element_id = current.text(2)
        try:
            state = self.session.clip(element_id)
        except SourceEditError:
            self.clip_explicit.blockSignals(True)
            self.clip_explicit.setChecked(False)
            self.clip_explicit.blockSignals(False)
            self._set_clip_enabled(False)
            return

        self._clip_element_id = element_id
        self.clip_explicit.blockSignals(True)
        self.clip_explicit.setChecked(state.explicit)
        self.clip_explicit.blockSignals(False)
        self.clip_target.setCurrentText(state.target)
        self.clip_enabled.setChecked(state.enabled)
        self.clip_inset.setText(str(state.inset))
        self._set_clip_enabled(True)

    def _apply_clip(self) -> None:
        element_id = self._clip_element_id
        if element_id is None:
            return
        try:
            updated = self.session.set_clip(
                element_id,
                explicit=self.clip_explicit.isChecked(),
                target=self.clip_target.currentText(),
                enabled=self.clip_enabled.isChecked(),
                inset=self.clip_inset.text() or "0",
            )
        except SourceEditError as exc:
            QMessageBox.warning(self, "Clip edit failed", str(exc))
            return
        self._replace_source_and_render(updated)

    def _set_placement_enabled(self, enabled: bool) -> None:
        self.placement_mode.setEnabled(enabled)
        self.placement_first.setEnabled(enabled)
        self.placement_second.setEnabled(enabled)
        self.placement_apply.setEnabled(enabled)

    def _placement_mode_changed(self, mode: str) -> None:
        if mode == "polar":
            self.placement_first_label.setText("angle")
            self.placement_second_label.setText("radius")
        else:
            self.placement_first_label.setText("x")
            self.placement_second_label.setText("y")

    def _load_placement_for_item(self, current: QTreeWidgetItem) -> None:
        node_id = current.text(2)
        kind = current.text(1)
        self._placement_element_id = None
        if kind == "layer":
            self.placement_target.setText("Layers are not positioned")
            self._set_placement_enabled(False)
            return
        try:
            placement = self.session.placement(node_id)
        except SourceEditError as exc:
            self.placement_target.setText(str(exc))
            self._set_placement_enabled(False)
            return

        self._placement_element_id = node_id
        self.placement_target.setText(f"{current.text(0)} ({node_id})")
        self._set_placement_enabled(True)
        mode = placement.mode or "cartesian"
        self.placement_mode.blockSignals(True)
        self.placement_mode.setCurrentText(mode)
        self.placement_mode.blockSignals(False)
        self._placement_mode_changed(mode)
        if placement.mode is None:
            self.placement_first.setText("0")
            self.placement_second.setText("0")
        else:
            self.placement_first.setText(placement.first)
            self.placement_second.setText(placement.second)

    def _apply_placement(self) -> None:
        element_id = self._placement_element_id
        if element_id is None:
            return
        try:
            updated = self.session.set_placement(
                element_id,
                mode=self.placement_mode.currentText(),  # type: ignore[arg-type]
                first=self.placement_first.text(),
                second=self.placement_second.text(),
            )
        except SourceEditError as exc:
            QMessageBox.warning(self, "Placement edit failed", str(exc))
            return
        self._replace_source_and_render(updated)

    def _set_seed_enabled(self, enabled: bool, *, resolved: bool) -> None:
        self.seed_lock.setEnabled(enabled and resolved)
        self.seed_regenerate.setEnabled(enabled)
        self.seed_auto.setEnabled(enabled)

    def _load_seed_for_item(self, current: QTreeWidgetItem) -> None:
        self._seed_element_id = None
        if current.text(1) != "starfield":
            self.seed_configured.setText("—")
            self.seed_resolved.setText("—")
            self._set_seed_enabled(False, resolved=False)
            return
        element_id = current.text(2)
        try:
            state = self.session.starfield_seed(element_id)
        except SourceEditError as exc:
            self.seed_configured.setText(str(exc))
            self.seed_resolved.setText("—")
            self._set_seed_enabled(False, resolved=False)
            return
        resolved = self.session.resolved_seed(element_id)
        self._seed_element_id = element_id
        self.seed_configured.setText(state.configured)
        self.seed_resolved.setText(str(resolved) if resolved is not None else "unavailable")
        self._set_seed_enabled(True, resolved=resolved is not None)

    def _replace_source_and_render(self, updated: str) -> None:
        self.editor.blockSignals(True)
        self.editor.setPlainText(updated)
        self.editor.blockSignals(False)
        self._update_title()
        self._show_result(self.session.render())

    def _seed_edit(self, action: str) -> None:
        element_id = self._seed_element_id
        if element_id is None:
            return
        try:
            if action == "lock":
                updated = self.session.lock_current_seed(element_id)
            elif action == "regenerate":
                updated = self.session.regenerate_seed(element_id)
            elif action == "auto":
                updated = self.session.auto_seed(element_id)
            else:  # pragma: no cover
                raise ValueError(action)
        except (SourceEditError, ValueError) as exc:
            QMessageBox.warning(self, "Starfield seed edit failed", str(exc))
            return
        self._replace_source_and_render(updated)

    def _lock_seed(self) -> None:
        self._seed_edit("lock")

    def _regenerate_seed(self) -> None:
        self._seed_edit("regenerate")

    def _auto_seed(self) -> None:
        self._seed_edit("auto")

    def _tree_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._placement_element_id = None
            self._set_placement_enabled(False)
            self._clip_element_id = None
            self._set_clip_enabled(False)
            self._seed_element_id = None
            self._set_seed_enabled(False, resolved=False)
            return
        self._load_placement_for_item(current)
        self._load_clip_for_item(current)
        self._load_seed_for_item(current)
        if current.text(1) == "starfield":
            resolved = self.session.resolved_seed(current.text(2))
            self.statusBar().showMessage(
                f"Selected starfield {current.text(2)} — configured seed: "
                f"{self.seed_configured.text()}; resolved: {resolved if resolved is not None else 'unavailable'}"
            )
        else:
            self.statusBar().showMessage(
                f"Selected {current.text(1)} {current.text(2)} — visible: {current.text(3)}"
            )

    def _show_result(self, result: PreviewResult) -> None:
        if result.svg is not None:
            self.preview.load(QByteArray(result.svg.encode("utf-8")))
        self._load_safe_margin()
        self._refresh_tree(result.tree)

        lines: list[str] = []
        if result.error:
            lines.append(result.error)
        if result.validation_error:
            lines.append(f"validation: {result.validation_error}")
        lines.extend(f"warning: {warning}" for warning in result.warnings)
        report = result.validation_report
        if report is not None:
            profile = f"; profile {result.validation_profile}" if result.validation_profile else ""
            lines.append(
                f"validation: {report.error_count} error(s), {report.warning_count} warning(s), "
                f"{report.info_count} info{profile}"
            )
            lines.extend(finding.format() for finding in report.findings)
        self.diagnostics.setPlainText("\n".join(lines))

        if result.error:
            self.statusBar().showMessage("Preview has errors; showing last valid render and scene tree")
        elif result.validation_error:
            self.statusBar().showMessage("Rendered successfully; validation view unavailable")
        elif report is not None and (report.error_count or report.warning_count):
            self.statusBar().showMessage(
                f"Rendered with {report.error_count + report.warning_count} actionable validation finding(s)"
            )
        elif report is not None:
            self.statusBar().showMessage("Rendered successfully; validation OK")
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
