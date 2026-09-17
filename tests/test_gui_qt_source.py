from __future__ import annotations

from pathlib import Path


def test_optional_qt_frontend_source_compiles_without_importing_qt():
    """Core CI should at least syntax-check the optional PySide6 module."""

    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "patchcreator"
        / "gui"
        / "qt_app.py"
    )
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
