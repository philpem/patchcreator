"""Profile discovery and deterministic profile layering."""

from __future__ import annotations

from dataclasses import dataclass
import os
from importlib.resources import files
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from ruamel.yaml import YAML

from .model import EffectiveProfile, ProfileConstraints, ProfileDefinition

if TYPE_CHECKING:
    from patchcreator.config.schema import ProfileSpec


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogEntry:
    profile: ProfileDefinition
    source: str


class ProfileCatalog:
    """Collection of built-in and user-defined profiles.

    Later sources override earlier sources with the same ``(kind, name)`` key.
    This deliberately lets a user tune a built-in profile locally without
    modifying PatchCreator itself.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], CatalogEntry] = {}

    def add(self, profile: ProfileDefinition, *, source: str) -> None:
        self._entries[(profile.kind, profile.name)] = CatalogEntry(profile, source)

    def get(self, kind: str, name: str) -> CatalogEntry:
        try:
            return self._entries[(kind, name)]
        except KeyError as exc:
            choices = ", ".join(self.names(kind)) or "(none)"
            raise ProfileError(f"unknown {kind} profile {name!r}; available: {choices}") from exc

    def names(self, kind: str | None = None) -> tuple[str, ...]:
        names = {
            name
            for (entry_kind, name) in self._entries
            if kind is None or entry_kind == kind
        }
        return tuple(sorted(names))

    def entries(self) -> tuple[CatalogEntry, ...]:
        return tuple(
            self._entries[key]
            for key in sorted(self._entries, key=lambda item: (item[0], item[1]))
        )


def _read_profile(path: Path, *, source: str | None = None) -> ProfileDefinition:
    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"))
        return ProfileDefinition.model_validate(raw)
    except Exception as exc:
        # Parser, I/O and validation exceptions are wrapped as a stable API.
        raise ProfileError(f"cannot load profile {source or path}: {exc}") from exc


def _load_directory(catalog: ProfileCatalog, directory: Path, *, required: bool = False) -> None:
    if not directory.exists():
        if required:
            raise ProfileError(f"profile directory does not exist: {directory}")
        return
    if not directory.is_dir():
        raise ProfileError(f"profile path is not a directory: {directory}")
    for path in sorted(directory.glob("*.yaml")):
        catalog.add(_read_profile(path), source=str(path))
    for path in sorted(directory.glob("*.yml")):
        catalog.add(_read_profile(path), source=str(path))


def default_user_profile_directory() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "patchcreator" / "profiles"


def environment_profile_directories() -> tuple[Path, ...]:
    value = os.environ.get("PATCHCREATOR_PROFILE_PATH", "")
    if not value:
        return ()
    return tuple(Path(part).expanduser() for part in value.split(os.pathsep) if part)


def load_profile_catalog(extra_directories: Iterable[str | Path] = ()) -> ProfileCatalog:
    catalog = ProfileCatalog()

    defaults = files("patchcreator.profiles").joinpath("defaults")
    for resource in sorted(defaults.iterdir(), key=lambda item: item.name):
        if resource.name.endswith((".yaml", ".yml")):
            raw = resource.read_text(encoding="utf-8")
            yaml = YAML(typ="safe")
            try:
                profile = ProfileDefinition.model_validate(yaml.load(raw))
            except Exception as exc:
                raise ProfileError(f"invalid built-in profile {resource.name}: {exc}") from exc
            catalog.add(profile, source=f"builtin:{resource.name}")

    _load_directory(catalog, default_user_profile_directory())
    for directory in environment_profile_directories():
        _load_directory(catalog, directory, required=True)
    for directory in extra_directories:
        _load_directory(catalog, Path(directory).expanduser(), required=True)
    return catalog


def resolve_profile(spec: "ProfileSpec", catalog: ProfileCatalog | None = None) -> EffectiveProfile:
    catalog = catalog or load_profile_catalog()
    constraints = ProfileConstraints()
    sources: list[str] = []

    if spec.machine:
        entry = catalog.get("machine", spec.machine)
        constraints = constraints.merged(entry.profile.constraints)
        sources.append(entry.source)
    if spec.intent:
        entry = catalog.get("intent", spec.intent)
        constraints = constraints.merged(entry.profile.constraints)
        sources.append(entry.source)

    constraints = constraints.merged(spec.overrides)
    if any(value is not None for value in spec.overrides.model_dump().values()):
        sources.append("document:profile.overrides")

    return EffectiveProfile(
        machine=spec.machine,
        intent=spec.intent,
        constraints=constraints,
        sources=tuple(sources),
    )
