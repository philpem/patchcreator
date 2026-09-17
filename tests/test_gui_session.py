from __future__ import annotations

from pathlib import Path

from patchcreator.gui import PreviewSession

_VALID = """version: 0.1
canvas: {shape: circle, diameter: 80}
layers:
  - id: artwork
    label: Artwork
    elements:
      - id: formation
        type: group
        label: Formation
        visible: false
        elements:
          - id: marker
            type: star
            label: Guide star
"""


def test_preview_session_renders_through_normal_pipeline_and_builds_tree():
    session = PreviewSession(_VALID)
    result = session.render()

    assert result.valid
    assert result.error is None
    assert result.svg is not None
    assert '<svg' in result.svg
    assert session.last_valid_svg == result.svg

    assert len(result.tree) == 1
    layer = result.tree[0]
    assert (layer.id, layer.label, layer.kind, layer.visible) == (
        "artwork",
        "Artwork",
        "layer",
        True,
    )
    group = layer.children[0]
    assert (group.id, group.label, group.kind, group.visible) == (
        "formation",
        "Formation",
        "group",
        False,
    )
    marker = group.children[0]
    assert (marker.id, marker.label, marker.kind, marker.visible) == (
        "marker",
        "Guide star",
        "star",
        True,
    )


def test_invalid_edit_keeps_last_valid_preview_and_tree_visible():
    session = PreviewSession(_VALID)
    good = session.render()
    assert good.svg is not None
    assert good.tree

    session.set_text("version: [not valid")
    broken = session.render()

    assert not broken.valid
    assert broken.error
    assert broken.svg == good.svg
    assert broken.tree == good.tree
    assert session.last_valid_svg == good.svg
    assert session.last_valid_tree == good.tree
    assert session.dirty


def test_session_load_save_and_source_directory(tmp_path: Path):
    source = tmp_path / "design.yaml"
    source.write_text(_VALID, encoding="utf-8")

    session = PreviewSession()
    result = session.load(source)
    assert result.valid
    assert session.source_path == source
    assert not session.dirty

    session.set_text(_VALID.replace("diameter: 80", "diameter: 70"))
    destination = tmp_path / "copy.yaml"
    saved = session.save(destination)

    assert saved == destination
    assert destination.read_text(encoding="utf-8") == session.text
    assert session.source_path == destination
    assert not session.dirty


def test_unsaved_session_requires_save_destination():
    session = PreviewSession(_VALID)
    try:
        session.save()
    except ValueError as exc:
        assert "no destination" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
