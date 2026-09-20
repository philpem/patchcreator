from __future__ import annotations

from patchcreator.gui import PreviewSession


_DOCUMENT = """version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: artwork
    elements:
      - id: border
        type: border
        inset: 2
        stroke: {width: 0.5}
        clip: {target: none}
"""


def test_preview_accepts_null_border_lengths_from_live_yaml_edit():
    session = PreviewSession(_DOCUMENT)
    good = session.render()
    assert good.valid and good.svg is not None

    session.set_text(_DOCUMENT.replace("inset: 2", "inset:").replace("width: 0.5", "width:"))
    edited = session.render()

    assert edited.valid
    assert edited.error is None
    assert edited.svg is not None


def test_preview_keeps_last_valid_result_for_invalid_border_length():
    session = PreviewSession(_DOCUMENT)
    good = session.render()
    assert good.valid and good.svg is not None

    session.set_text(_DOCUMENT.replace("inset: 2", "inset: invalid"))
    broken = session.render()

    assert not broken.valid
    assert broken.error is not None
    assert "border inset must be a millimetre length" in broken.error
    assert broken.svg == good.svg
    assert broken.tree == good.tree
