from __future__ import annotations

from patchcreator import dispatch


def test_dispatch_forwards_existing_cli_commands(monkeypatch):
    seen: list[list[str]] = []

    def fake_main(argv):
        seen.append(list(argv))
        return 7

    monkeypatch.setattr("patchcreator.cli.main", fake_main)
    assert dispatch.main(["render", "design.yaml"]) == 7
    assert seen == [["render", "design.yaml"]]


def test_dispatch_routes_gui_without_importing_qt(monkeypatch):
    seen: list[list[str]] = []

    def fake_gui_main(argv):
        seen.append(list(argv))
        return 9

    monkeypatch.setattr("patchcreator.gui.app.main", fake_gui_main)
    assert dispatch.main(["gui", "examples/basic-round-patch.yaml"]) == 9
    assert seen == [["examples/basic-round-patch.yaml"]]
