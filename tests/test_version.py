from importlib.metadata import PackageNotFoundError, version

import patchcreator
from patchcreator import _version


def test_runtime_version_matches_installed_distribution():
    assert patchcreator.__version__ == version("patchcreator")


def test_runtime_version_has_safe_uninstalled_source_fallback(monkeypatch):
    def missing_distribution(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(_version, "distribution_version", missing_distribution)

    assert _version.resolve_version() == "0+unknown"
