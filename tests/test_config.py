import pytest

from patchcreator.config.loader import DesignLoadError, loads_design


def test_load_minimal_design():
    design = loads_design(
        """
version: 0.1
units: mm
canvas:
  shape: circle
  diameter: 80
  safe_margin:
    fixed: 3
layers: []
"""
    )
    assert str(design.version) == "0.1"
    assert design.canvas.diameter == 80


def test_invalid_canvas_diagnostic_has_source_line():
    with pytest.raises(DesignLoadError) as excinfo:
        loads_design(
            """
version: 0.1
canvas:
  shape: circle
  safe_margin:
    fixed: 3
layers: []
""",
            source="broken.yaml",
        )
    message = str(excinfo.value)
    assert "broken.yaml" in message
    assert "diameter" in message


def test_safe_margin_requires_one_mode():
    with pytest.raises(DesignLoadError):
        loads_design(
            """
version: 0.1
canvas:
  shape: circle
  diameter: 80
  safe_margin:
    fixed: 2
    percent: 5
layers: []
"""
        )
