"""Explicit acquisition and cache management for third-party datasets.

PatchCreator never downloads data as a side effect of rendering. Components call
``require_dataset`` and produce an actionable error if the user has not fetched
that dataset explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Iterable
from urllib.request import Request, urlopen
import zipfile

from ruamel.yaml import YAML

_MARKER = ".patchcreator-source.json"


class DataSourceError(RuntimeError):
    """Base class for external-data errors."""


class DatasetNotInstalledError(DataSourceError):
    """Raised when a component requires data which has not been fetched."""


class ChecksumMismatchError(DataSourceError):
    """Raised when a downloaded file does not match its configured checksum."""


@dataclass(frozen=True)
class DataSource:
    name: str
    description: str
    url: str
    version: str
    homepage: str | None = None
    licence: str | None = None
    licence_url: str | None = None
    attribution: str | None = None
    sha256: str | None = None
    archive: str = "zip"
    required_members: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, name: str, raw: dict[str, Any]) -> "DataSource":
        try:
            url = str(raw["url"])
            version = str(raw["version"])
        except KeyError as exc:
            raise DataSourceError(
                f"data source {name!r} is missing required field {exc.args[0]!r}"
            ) from exc

        archive = str(raw.get("archive", "zip"))
        if archive not in {"zip", "file"}:
            raise DataSourceError(
                f"data source {name!r} has unsupported archive type {archive!r}"
            )

        checksum = raw.get("sha256")
        if checksum is not None:
            checksum = str(checksum).lower()
            if len(checksum) != 64 or any(ch not in "0123456789abcdef" for ch in checksum):
                raise DataSourceError(
                    f"data source {name!r} has an invalid SHA-256 checksum"
                )

        members = tuple(str(item) for item in raw.get("required_members", ()))
        for member in members:
            path = PurePosixPath(member)
            if path.is_absolute() or ".." in path.parts:
                raise DataSourceError(
                    f"data source {name!r} has unsafe required member {member!r}"
                )

        return cls(
            name=name,
            description=str(raw.get("description", name)),
            url=url,
            version=version,
            homepage=str(raw["homepage"]) if raw.get("homepage") else None,
            licence=str(raw["licence"]) if raw.get("licence") else None,
            licence_url=str(raw["licence_url"]) if raw.get("licence_url") else None,
            attribution=str(raw["attribution"]) if raw.get("attribution") else None,
            sha256=checksum,
            archive=archive,
            required_members=members,
        )


class DataCatalog:
    def __init__(self, sources: Iterable[DataSource]) -> None:
        self._sources = {source.name: source for source in sources}
        if len(self._sources) != len(tuple(sources)):
            raise DataSourceError("duplicate external data source name")

    def get(self, name: str) -> DataSource:
        try:
            return self._sources[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._sources)) or "(none)"
            raise DataSourceError(
                f"unknown dataset {name!r}; available datasets: {available}"
            ) from exc

    def entries(self) -> tuple[DataSource, ...]:
        return tuple(self._sources[name] for name in sorted(self._sources))


def load_data_catalog() -> DataCatalog:
    """Load the small tracked source manifest shipped with PatchCreator."""
    text = resources.files("patchcreator.data").joinpath("sources.yaml").read_text(
        encoding="utf-8"
    )
    yaml = YAML(typ="safe")
    document = yaml.load(text) or {}
    raw_sources = document.get("sources") or {}
    if not isinstance(raw_sources, dict):
        raise DataSourceError("external data manifest 'sources' must be a mapping")
    return DataCatalog(
        DataSource.from_mapping(str(name), raw)
        for name, raw in raw_sources.items()
        if isinstance(raw, dict)
    )


def resolve_data_root(override: str | Path | None = None) -> Path:
    """Resolve the external-data cache root without creating it."""
    if override is not None:
        return Path(override).expanduser()
    configured = os.environ.get("PATCHCREATOR_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    cache_home = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return cache_home / "patchcreator" / "data"


def _dataset_path(source: DataSource, root: Path) -> Path:
    return root / source.name


def _marker_path(source: DataSource, root: Path) -> Path:
    return _dataset_path(source, root) / _MARKER


def _members_present(source: DataSource, dataset_path: Path) -> bool:
    return all((dataset_path / member).is_file() for member in source.required_members)


def is_dataset_installed(
    source: DataSource | str,
    *,
    root: str | Path | None = None,
    catalog: DataCatalog | None = None,
) -> bool:
    if isinstance(source, str):
        source = (catalog or load_data_catalog()).get(source)
    resolved_root = resolve_data_root(root)
    marker = _marker_path(source, resolved_root)
    if not marker.is_file() or not _members_present(source, marker.parent):
        return False
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return metadata.get("name") == source.name and metadata.get("version") == source.version


def require_dataset(
    name: str,
    *,
    root: str | Path | None = None,
    catalog: DataCatalog | None = None,
) -> Path:
    """Return an installed dataset path, never downloading implicitly."""
    catalog = catalog or load_data_catalog()
    source = catalog.get(name)
    resolved_root = resolve_data_root(root)
    path = _dataset_path(source, resolved_root)
    if not is_dataset_installed(source, root=resolved_root):
        raise DatasetNotInstalledError(
            f"dataset {name!r} is not installed in {resolved_root}; "
            f"run 'patchcreator data fetch {name}'"
        )
    return path


def fetch_dataset(
    name: str,
    *,
    root: str | Path | None = None,
    force: bool = False,
    catalog: DataCatalog | None = None,
) -> Path:
    catalog = catalog or load_data_catalog()
    return fetch_source(catalog.get(name), root=root, force=force)


def fetch_source(
    source: DataSource,
    *,
    root: str | Path | None = None,
    force: bool = False,
) -> Path:
    """Explicitly download and install one source into the cache.

    Downloads are staged under the destination cache, verified, then moved into
    place. Existing valid data is reused unless ``force`` is requested.
    """
    resolved_root = resolve_data_root(root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    target = _dataset_path(source, resolved_root)

    if is_dataset_installed(source, root=resolved_root):
        if not force:
            return target
    elif target.exists() and not force:
        raise DataSourceError(
            f"dataset directory {target} exists but is incomplete or from a different version; "
            "re-run with --force to replace it"
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{source.name}-", dir=resolved_root))
    archive_path = staging / "download"
    payload = staging / "payload"
    backup: Path | None = None

    try:
        actual_sha256 = _download(source.url, archive_path)
        if source.sha256 and actual_sha256 != source.sha256:
            raise ChecksumMismatchError(
                f"SHA-256 mismatch for {source.name!r}: expected {source.sha256}, "
                f"downloaded {actual_sha256}"
            )

        payload.mkdir()
        if source.archive == "zip":
            _extract_zip(archive_path, payload)
        else:
            filename = PurePosixPath(source.url.split("?", 1)[0]).name or "data"
            shutil.copy2(archive_path, payload / filename)

        missing = [member for member in source.required_members if not (payload / member).is_file()]
        if missing:
            raise DataSourceError(
                f"downloaded dataset {source.name!r} is missing expected files: "
                + ", ".join(missing)
            )

        marker = {
            "name": source.name,
            "version": source.version,
            "url": source.url,
            "sha256": actual_sha256,
        }
        (payload / _MARKER).write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if target.exists():
            backup = resolved_root / f".{source.name}-old"
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(target, backup)
        try:
            os.replace(payload, target)
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _download(url: str, destination: Path) -> str:
    digest = hashlib.sha256()
    request = Request(url, headers={"User-Agent": "PatchCreator external-data fetcher"})
    try:
        response = urlopen(request, timeout=60)
    except OSError as exc:
        raise DataSourceError(f"failed to download {url}: {exc}") from exc

    try:
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
    finally:
        response.close()
    return digest.hexdigest()


def _extract_zip(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise DataSourceError(
                        f"refusing unsafe path {member.filename!r} in downloaded ZIP archive"
                    )
            zf.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise DataSourceError("downloaded dataset is not a valid ZIP archive") from exc
