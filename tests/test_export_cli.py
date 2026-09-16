from __future__ import annotations

from pathlib import Path

from patchcreator.cli import main

SVG_NS = "http://www.w3.org/2000/svg"


def test_cli_export_writes_default_compatibility_name(tmp_path: Path, capsys):
    source = tmp_path / "master.svg"
    source.write_text(
        f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80"><circle r="2"/></svg>',
        encoding="utf-8",
    )

    assert main(["export", str(source)]) == 0

    output = tmp_path / "master.compat.svg"
    assert output.exists()
    stdout = capsys.readouterr().out
    assert str(output) in stdout
    assert "export:" in stdout


def test_cli_export_text_paths_gives_actionable_missing_inkscape_error(
    tmp_path: Path, capsys, monkeypatch
):
    source = tmp_path / "master.svg"
    source.write_text(
        f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80"><text>LIVE</text></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "patchcreator.svg.text_outline.shutil.which",
        lambda executable: None,
    )

    assert main(["export", str(source), "--text", "paths"]) == 2
    assert "requires Inkscape" in capsys.readouterr().err


def test_cli_export_knockout_applies_boolean_and_reports_counts(tmp_path: Path, capsys):
    source = tmp_path / "master.svg"
    source.write_text(
        f'''<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80">
  <g id="lower" data-patchcreator-overlap-policy="knockout">
    <rect id="lower-shape" x="10" y="10" width="20" height="20" fill="#f00"/>
  </g>
  <g id="upper" data-patchcreator-overlap-policy="allow">
    <rect id="upper-shape" x="20" y="10" width="20" height="20" fill="#fff"/>
  </g>
</svg>''',
        encoding="utf-8",
    )

    assert main(["export", str(source), "--knockout"]) == 0
    output = tmp_path / "master.compat.svg"
    assert output.exists()
    captured = capsys.readouterr()
    assert "knockout-changed=1" in captured.out
    assert "knockout-removed=0" in captured.out
