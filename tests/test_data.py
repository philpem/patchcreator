from __future__ import annotations

import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from patchcreator.cli import main
from patchcreator.data import (
    ChecksumMismatchError,
    DataCatalog,
    DataSource,
    DatasetNotInstalledError,
    fetch_source,
    is_dataset_installed,
    load_data_catalog,
    require_dataset,
    resolve_data_root,
)
import patchcreator.data.catalog as data_catalog


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _source(payload: bytes, *, checksum: str | None = None) -> DataSource:
    return DataSource(
        name="fixture",
        description="test fixture",
        url="https://example.invalid/fixture.zip",
        version="1",
        sha256=checksum,
        archive="zip",
        required_members=("fixture.txt",),
    )


def test_builtin_catalog_declares_natural_earth_without_bundling_payload():
    source = load_data_catalog().get("natural-earth-land-110m")
    assert source.version == "4.0.0"
    assert source.url == "https://naturalearth.s3.amazonaws.com/110m_physical/ne_110m_land.zip"
    assert "ne_110m_land.shp" in source.required_members


def test_data_root_environment_precedence(monkeypatch, tmp_path: Path):
    explicit = tmp_path / "explicit"
    configured = tmp_path / "configured"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("PATCHCREATOR_DATA_DIR", str(configured))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg))
    assert resolve_data_root(explicit) == explicit
    assert resolve_data_root() == configured
    monkeypatch.delenv("PATCHCREATOR_DATA_DIR")
    assert resolve_data_root() == xdg / "patchcreator" / "data"


def test_fetch_source_is_explicit_atomic_and_verifies_checksum(monkeypatch, tmp_path: Path):
    payload = _zip_bytes({"fixture.txt": b"hello"})
    checksum = hashlib.sha256(payload).hexdigest()
    source = _source(payload, checksum=checksum)

    monkeypatch.setattr(
        data_catalog,
        "urlopen",
        lambda request, timeout: io.BytesIO(payload),
    )

    installed = fetch_source(source, root=tmp_path)
    assert installed == tmp_path / "fixture"
    assert (installed / "fixture.txt").read_bytes() == b"hello"
    assert is_dataset_installed(source, root=tmp_path)

    # A valid installed copy is reused and does not touch the network.
    monkeypatch.setattr(
        data_catalog,
        "urlopen",
        lambda request, timeout: (_ for _ in ()).throw(AssertionError("unexpected download")),
    )
    assert fetch_source(source, root=tmp_path) == installed


def test_checksum_mismatch_does_not_install_dataset(monkeypatch, tmp_path: Path):
    payload = _zip_bytes({"fixture.txt": b"hello"})
    source = _source(payload, checksum="0" * 64)
    monkeypatch.setattr(
        data_catalog,
        "urlopen",
        lambda request, timeout: io.BytesIO(payload),
    )
    with pytest.raises(ChecksumMismatchError):
        fetch_source(source, root=tmp_path)
    assert not (tmp_path / "fixture").exists()


def test_require_dataset_never_fetches_implicitly(tmp_path: Path):
    source = DataSource(
        name="fixture",
        description="test fixture",
        url="https://example.invalid/fixture.zip",
        version="1",
        required_members=("fixture.txt",),
    )
    catalog = DataCatalog([source])
    with pytest.raises(DatasetNotInstalledError) as excinfo:
        require_dataset("fixture", root=tmp_path, catalog=catalog)
    assert "patchcreator data fetch fixture" in str(excinfo.value)
    assert not (tmp_path / "fixture").exists()


def test_data_list_cli_requires_no_network(tmp_path: Path, capsys):
    assert main(["data", "list", "--data-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "missing" in output
    assert "natural-earth-land-110m" in output
