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


def test_cli_export_refuses_unimplemented_destructive_modes(tmp_path: Path, capsys):
    source = tmp_path / "master.svg"
    source.write_text(
        f'<svg xmlns="{SVG_NS}" width="80mm" height="80mm" viewBox="0 0 80 80"><text>LIVE</text></svg>',
        encoding="utf-8",
    )

    assert main(["export", str(source), "--text", "paths"]) == 2
    assert "text-to-path" in capsys.readouterr().err

    assert main(["export", str(source), "--knockout"]) == 2
    assert "knockout" in capsys.readouterr().err
