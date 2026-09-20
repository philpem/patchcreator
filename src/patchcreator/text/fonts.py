"""Deterministic local font discovery for text outlining.

PatchCreator never vendors fonts.  A request is resolved to one concrete local
font file (and collection face, where applicable) before shaping.  Callers that
need fully reproducible output can bypass discovery by supplying ``path``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
import sys
from typing import Iterable, Iterator

from fontTools.ttLib import TTCollection, TTFont, TTLibError


class FontResolutionError(ValueError):
    pass


_WEIGHT_NAMES = {
    "thin": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "normal": 400,
    "regular": 400,
    "book": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}

_GENERIC_FAMILIES = {
    "sans serif": ("DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial"),
    "serif": ("DejaVu Serif", "Noto Serif", "Liberation Serif", "Times New Roman"),
    "monospace": ("DejaVu Sans Mono", "Noto Sans Mono", "Liberation Mono", "Courier New"),
}

_SUPPORTED_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc"}


def _normalise_name(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _normalise_style(value: str) -> str:
    text = _normalise_name(value)
    if text in {"italic", "oblique"}:
        return "italic"
    return "normal"


def _normalise_weight(value: int | str) -> int:
    if isinstance(value, int):
        if 1 <= value <= 1000:
            return value
        raise FontResolutionError("font weight must be between 1 and 1000")
    text = _normalise_name(str(value)).replace(" ", "")
    if text.isdigit():
        return _normalise_weight(int(text))
    try:
        return _WEIGHT_NAMES[text]
    except KeyError as exc:
        raise FontResolutionError(f"unsupported font weight {value!r}") from exc


@dataclass(frozen=True)
class FontRequest:
    family: str = "sans-serif"
    weight: int | str = 400
    style: str = "normal"
    path: str | Path | None = None
    fallback_families: tuple[str, ...] = ()

    @property
    def numeric_weight(self) -> int:
        return _normalise_weight(self.weight)

    @property
    def canonical_style(self) -> str:
        return _normalise_style(self.style)


@dataclass(frozen=True)
class FontFaceInfo:
    path: Path
    face_index: int
    family: str
    subfamily: str
    weight: int
    style: str
    units_per_em: int


@dataclass(frozen=True)
class ResolvedFont:
    request: FontRequest
    face: FontFaceInfo
    substitutions: tuple[str, ...] = ()

    @property
    def substituted(self) -> bool:
        return bool(self.substitutions)


def default_font_directories() -> tuple[Path, ...]:
    """Return platform-appropriate local font roots in deterministic order."""

    home = Path.home()
    candidates: list[Path] = []
    if sys.platform.startswith("linux"):
        candidates.extend(
            [
                home / ".local/share/fonts",
                home / ".fonts",
                Path("/usr/local/share/fonts"),
                Path("/usr/share/fonts"),
            ]
        )
    elif sys.platform == "darwin":
        candidates.extend(
            [
                home / "Library/Fonts",
                Path("/Library/Fonts"),
                Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
            ]
        )
    elif os.name == "nt":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        candidates.extend([home / "AppData/Local/Microsoft/Windows/Fonts", windir / "Fonts"])

    result: list[Path] = []
    seen: set[Path] = set()
    for item in candidates:
        item = item.expanduser()
        if item in seen or not item.is_dir():
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def _name(font: TTFont, ids: tuple[int, ...]) -> str | None:
    table = font.get("name")
    if table is None:
        return None
    for name_id in ids:
        records = [record for record in table.names if record.nameID == name_id]
        records.sort(key=lambda record: (record.platformID != 3, record.langID not in {0, 0x409}))
        for record in records:
            try:
                value = record.toUnicode().strip()
            except Exception:
                continue
            if value:
                return value
    return None


def _face_info(font: TTFont, path: Path, face_index: int) -> FontFaceInfo:
    family = _name(font, (16, 1)) or path.stem
    subfamily = _name(font, (17, 2)) or "Regular"
    head = font.get("head")
    units_per_em = int(getattr(head, "unitsPerEm", 1000))
    os2 = font.get("OS/2")
    weight = int(getattr(os2, "usWeightClass", 400))
    italic = False
    if os2 is not None:
        italic = bool(int(getattr(os2, "fsSelection", 0)) & 0x01)
    post = font.get("post")
    italic = italic or bool(float(getattr(post, "italicAngle", 0.0)))
    if not italic:
        italic = any(word in _normalise_name(subfamily).split() for word in ("italic", "oblique"))
    return FontFaceInfo(
        path=path,
        face_index=face_index,
        family=family,
        subfamily=subfamily,
        weight=weight,
        style="italic" if italic else "normal",
        units_per_em=units_per_em,
    )


def _faces_in_file(path: Path) -> tuple[FontFaceInfo, ...]:
    try:
        if path.suffix.casefold() in {".ttc", ".otc"}:
            collection = TTCollection(str(path), lazy=True)
            try:
                return tuple(_face_info(font, path, index) for index, font in enumerate(collection.fonts))
            finally:
                collection.close()
        font = TTFont(str(path), lazy=True)
        try:
            return (_face_info(font, path, 0),)
        finally:
            font.close()
    except (OSError, TTLibError, ValueError):
        return ()


def _font_files(directories: Iterable[Path]) -> Iterator[Path]:
    for directory in directories:
        try:
            paths = sorted(directory.rglob("*"), key=lambda value: str(value).casefold())
        except OSError:
            continue
        for path in paths:
            if path.is_file() and path.suffix.casefold() in _SUPPORTED_SUFFIXES:
                yield path


@lru_cache(maxsize=16)
def _font_index(directory_names: tuple[str, ...]) -> tuple[FontFaceInfo, ...]:
    faces: list[FontFaceInfo] = []
    for path in _font_files(Path(name) for name in directory_names):
        faces.extend(_faces_in_file(path))
    return tuple(faces)


def _candidate_family_names(request: FontRequest) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_family in (request.family, *request.fallback_families):
        family = raw_family.strip()
        candidates = _GENERIC_FAMILIES.get(_normalise_name(family), (family,))
        for candidate in candidates:
            normalised = _normalise_name(candidate)
            if normalised in seen:
                continue
            seen.add(normalised)
            result.append(candidate)
    return tuple(result)


def _select_face(faces: Iterable[FontFaceInfo], request: FontRequest) -> FontFaceInfo | None:
    wanted_weight = request.numeric_weight
    wanted_style = request.canonical_style
    priorities = {
        _normalise_name(family): index
        for index, family in enumerate(_candidate_family_names(request))
    }
    candidates = [face for face in faces if _normalise_name(face.family) in priorities]
    if not candidates:
        return None

    return min(
        candidates,
        key=lambda face: (
            priorities[_normalise_name(face.family)],
            1 if face.style != wanted_style else 0,
            abs(face.weight - wanted_weight),
            str(face.path).casefold(),
            face.face_index,
        ),
    )


def _substitution_notes(request: FontRequest, face: FontFaceInfo) -> tuple[str, ...]:
    notes: list[str] = []
    requested_family = _normalise_name(request.family)
    if requested_family in _GENERIC_FAMILIES:
        notes.append(f"generic family {request.family!r} resolved to {face.family!r}")
    elif _normalise_name(face.family) != requested_family:
        notes.append(f"font family {request.family!r} substituted with {face.family!r}")
    if face.style != request.canonical_style:
        notes.append(f"font style {request.canonical_style!r} substituted with {face.style!r}")
    if face.weight != request.numeric_weight:
        notes.append(f"font weight {request.numeric_weight} substituted with {face.weight}")
    return tuple(notes)


def resolve_font(
    request: FontRequest,
    *,
    search_directories: Iterable[str | Path] | None = None,
) -> ResolvedFont:
    """Resolve ``request`` to one concrete local font face.

    An explicit ``request.path`` is authoritative and avoids environment-based
    family discovery.  Otherwise only the requested family and explicit
    fallbacks are considered; PatchCreator will not silently pick an unrelated
    font merely because it happens to be installed.
    """

    if request.path is not None:
        path = Path(request.path).expanduser().resolve()
        if not path.is_file():
            raise FontResolutionError(f"font file does not exist: {path}")
        faces = _faces_in_file(path)
        if not faces:
            raise FontResolutionError(f"font file is unreadable or unsupported: {path}")
        face = min(
            faces,
            key=lambda item: (
                1 if item.style != request.canonical_style else 0,
                abs(item.weight - request.numeric_weight),
                item.face_index,
            ),
        )
        return ResolvedFont(request=request, face=face, substitutions=_substitution_notes(request, face))

    directories = (
        tuple(Path(value).expanduser().resolve() for value in search_directories)
        if search_directories is not None
        else default_font_directories()
    )
    existing = tuple(path for path in directories if path.is_dir())
    if not existing:
        raise FontResolutionError(
            "no font directories are available; provide an explicit font file for reproducible text outlining"
        )
    faces = _font_index(tuple(str(path) for path in existing))
    face = _select_face(faces, request)
    if face is None:
        searched = ", ".join(str(path) for path in existing)
        requested = ", ".join(_candidate_family_names(request))
        raise FontResolutionError(
            f"could not resolve font family {request.family!r} (candidates: {requested}); "
            f"searched: {searched}; provide an explicit font file or install the requested family"
        )
    return ResolvedFont(request=request, face=face, substitutions=_substitution_notes(request, face))


def open_ttfont(font: ResolvedFont, *, lazy: bool = True) -> TTFont:
    """Open the resolved face through FontTools.

    The caller owns the returned ``TTFont`` and should call ``close()`` when
    finished.  Keeping the object out of ``ResolvedFont`` makes the resolved
    value immutable, serialisable and safe to cache.
    """

    try:
        return TTFont(str(font.face.path), fontNumber=font.face.face_index, lazy=lazy)
    except (OSError, TTLibError) as exc:
        raise FontResolutionError(f"cannot open resolved font {font.face.path}: {exc}") from exc
