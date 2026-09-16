"""Font-aware live-text outlining for compatibility export.

PatchCreator deliberately keeps text live in the editable master.  Compatibility
export may optionally ask Inkscape to perform the final text-to-path operation,
using the same Pango/font rendering stack artists see in Inkscape itself.  A
Fontconfig preflight makes missing-family fallback explicit before destructive
conversion occurs.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

_GENERIC_FAMILIES = {
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
    "ui-serif",
    "ui-sans-serif",
    "ui-monospace",
    "ui-rounded",
}


class TextOutlineError(ValueError):
    """Text cannot be converted to paths reproducibly."""


@dataclass(frozen=True)
class FontResolution:
    element_id: str | None
    requested_families: tuple[str, ...]
    requested_weight: str
    requested_style: str
    resolved_family: str
    resolved_style: str
    font_file: str
    substituted: bool = False


@dataclass(frozen=True)
class TextOutlineResult:
    root: ET.Element
    converted_text_count: int
    font_resolutions: tuple[FontResolution, ...] = ()
    warnings: tuple[str, ...] = ()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _style_map(raw: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if not raw:
        return result
    for declaration in raw.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        result[name.strip().lower()] = value.strip()
    return result


def _property(element: ET.Element, name: str, inherited: str | None) -> str | None:
    style = _style_map(element.get("style"))
    if name in style:
        return style[name]
    if element.get(name) is not None:
        return element.get(name)
    return inherited


def _split_families(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ("sans-serif",)
    result: list[str] = []
    for item in raw.split(","):
        family = item.strip().strip("'\"").strip()
        if family:
            result.append(family)
    return tuple(result) or ("sans-serif",)


def _weight_pattern(raw: str) -> str:
    value = raw.strip().lower()
    names = {
        "normal": "regular",
        "bold": "bold",
        "bolder": "bold",
        "lighter": "light",
        "light": "light",
        "semibold": "semibold",
        "semi-bold": "semibold",
        "demibold": "semibold",
        "demi-bold": "semibold",
    }
    if value in names:
        return names[value]
    try:
        numeric = int(float(value))
    except ValueError:
        return value or "regular"
    if numeric >= 700:
        return "bold"
    if numeric >= 600:
        return "semibold"
    if numeric <= 300:
        return "light"
    return "regular"


def _slant_pattern(raw: str) -> str:
    value = raw.strip().lower()
    if value in {"italic", "oblique"}:
        return value
    return "roman"


def _normalise_family(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _fontconfig_match(
    executable: str,
    family: str,
    *,
    weight: str,
    style: str,
) -> tuple[str, str, str]:
    pattern = f"{family}:weight={_weight_pattern(weight)}:slant={_slant_pattern(style)}"
    format_string = "%{family[0]}|%{style[0]}|%{file}\\n"
    try:
        completed = subprocess.run(
            [executable, "-f", format_string, pattern],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TextOutlineError(f"failed to run fontconfig preflight: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit status {completed.returncode}"
        raise TextOutlineError(f"fontconfig preflight failed: {detail}")
    line = next((line for line in completed.stdout.splitlines() if line.strip()), "")
    fields = line.split("|", 2)
    if len(fields) != 3 or not fields[0].strip() or not fields[2].strip():
        raise TextOutlineError(
            f"fontconfig could not resolve font family {family!r}; install the font or choose another family"
        )
    return fields[0].strip(), fields[1].strip(), fields[2].strip()


def _font_requests(root: ET.Element) -> tuple[tuple[str | None, tuple[str, ...], str, str], ...]:
    requests: list[tuple[str | None, tuple[str, ...], str, str]] = []

    def walk(
        element: ET.Element,
        family: str | None,
        weight: str,
        style: str,
    ) -> None:
        current_family = _property(element, "font-family", family)
        current_weight = _property(element, "font-weight", weight) or "normal"
        current_style = _property(element, "font-style", style) or "normal"
        if _local_name(element.tag) == "text":
            requests.append(
                (
                    element.get("id"),
                    _split_families(current_family),
                    current_weight,
                    current_style,
                )
            )
        for child in element:
            walk(child, current_family, current_weight, current_style)

    walk(root, None, "normal", "normal")
    return tuple(requests)


def _resolve_fonts(
    root: ET.Element,
    *,
    allow_substitution: bool,
    fc_match: str,
) -> tuple[tuple[FontResolution, ...], tuple[str, ...]]:
    resolutions: list[FontResolution] = []
    warnings: list[str] = []
    cache: dict[tuple[tuple[str, ...], str, str], tuple[str, str, str, bool]] = {}

    for element_id, families, weight, style in _font_requests(root):
        key = (families, weight, style)
        cached = cache.get(key)
        if cached is None:
            selected: tuple[str, str, str, bool] | None = None
            fallback: tuple[str, str, str] | None = None
            for family in families:
                resolved = _fontconfig_match(fc_match, family, weight=weight, style=style)
                if fallback is None:
                    fallback = resolved
                if _normalise_family(family) in _GENERIC_FAMILIES:
                    selected = (*resolved, False)
                    break
                if _normalise_family(resolved[0]) == _normalise_family(family):
                    # This also models CSS family-list fallback: if an earlier
                    # requested family was missing but this one exists, Pango will
                    # normally settle on the first available family in the list.
                    selected = (*resolved, family != families[0])
                    break
            if selected is None:
                assert fallback is not None
                selected = (*fallback, True)
            cached = selected
            cache[key] = cached

        resolved_family, resolved_style, font_file, substituted = cached
        resolution = FontResolution(
            element_id=element_id,
            requested_families=families,
            requested_weight=weight,
            requested_style=style,
            resolved_family=resolved_family,
            resolved_style=resolved_style,
            font_file=font_file,
            substituted=substituted,
        )
        resolutions.append(resolution)

        first = families[0]
        specific_first = _normalise_family(first) not in _GENERIC_FAMILIES
        exact_first = _normalise_family(resolved_family) == _normalise_family(first)
        if substituted or (specific_first and not exact_first):
            where = f" on text {element_id!r}" if element_id else ""
            message = (
                f"requested font {', '.join(families)!r}{where} resolved to "
                f"{resolved_family!r} ({resolved_style or 'default style'})"
            )
            if not allow_substitution:
                raise TextOutlineError(
                    message
                    + "; install the requested font, choose an installed fallback in the SVG, "
                    "or rerun with --allow-font-substitution"
                )
            warnings.append("font substitution: " + message)

        requested_weight_class = _weight_pattern(weight)
        style_lower = resolved_style.casefold()
        if requested_weight_class in {"bold", "semibold"} and not any(
            token in style_lower for token in ("bold", "demi", "semi")
        ):
            warnings.append(
                f"font style warning: text {element_id or '(unnamed)'} requested weight {weight!r}; "
                f"fontconfig selected {resolved_family!r} style {resolved_style!r}, so Pango may synthesize weight"
            )
        if _slant_pattern(style) in {"italic", "oblique"} and not any(
            token in style_lower for token in ("italic", "oblique")
        ):
            warnings.append(
                f"font style warning: text {element_id or '(unnamed)'} requested style {style!r}; "
                f"fontconfig selected {resolved_family!r} style {resolved_style!r}, so Pango may synthesize slant"
            )

    return tuple(resolutions), tuple(warnings)


def _parse_svg_file(path: Path) -> ET.Element:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise TextOutlineError(f"cannot read Inkscape outlined SVG: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise TextOutlineError("Inkscape text outlining did not produce an SVG document")
    return root


def outline_text_with_inkscape(
    root: ET.Element,
    *,
    allow_substitution: bool = False,
) -> TextOutlineResult:
    """Return a new SVG root with all ``<text>`` converted to ordinary paths.

    Inkscape performs the actual shaping and text-on-path placement.  Fontconfig
    is used first to make family fallback explicit and reproducible instead of
    silently accepting whichever font happens to be installed.
    """
    requests = _font_requests(root)
    if not requests:
        return TextOutlineResult(root=root, converted_text_count=0)

    inkscape = shutil.which(os.environ.get("PATCHCREATOR_INKSCAPE", "inkscape"))
    if inkscape is None:
        raise TextOutlineError(
            "text-to-path export requires Inkscape on PATH; install Inkscape or preserve live text with --text preserve"
        )
    fc_match = shutil.which(os.environ.get("PATCHCREATOR_FC_MATCH", "fc-match"))
    if fc_match is None:
        raise TextOutlineError(
            "text-to-path export requires fontconfig 'fc-match' on PATH for deterministic font resolution"
        )

    resolutions, warnings = _resolve_fonts(
        root,
        allow_substitution=allow_substitution,
        fc_match=fc_match,
    )

    with tempfile.TemporaryDirectory(prefix="patchcreator-text-") as directory:
        source = Path(directory) / "source.svg"
        output = Path(directory) / "outlined.svg"
        source.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
        actions = (
            "select-by-element:text;object-to-path;"
            f"export-filename:{output};export-do"
        )
        try:
            completed = subprocess.run(
                [inkscape, str(source), "--batch-process", f"--actions={actions}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TextOutlineError(f"failed to run Inkscape text outlining: {exc}") from exc
        if completed.returncode != 0 or not output.exists():
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit status {completed.returncode}"
            raise TextOutlineError(f"Inkscape text outlining failed: {detail}")
        outlined = _parse_svg_file(output)

    remaining = [element for element in outlined.iter() if _local_name(element.tag) == "text"]
    if remaining:
        ids = ", ".join(element.get("id") or "(unnamed)" for element in remaining[:5])
        raise TextOutlineError(f"Inkscape left {len(remaining)} live text object(s) after outlining: {ids}")

    return TextOutlineResult(
        root=outlined,
        converted_text_count=len(requests),
        font_resolutions=resolutions,
        warnings=warnings,
    )
