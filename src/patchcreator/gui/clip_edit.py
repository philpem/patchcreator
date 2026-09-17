"""Round-trip YAML helpers for GUI safe-margin and clip editing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ruamel.yaml.comments import CommentedMap

from .source_edit import SourceEditError, _dump, _find_element, _load


MarginMode = Literal["fixed", "percent"]


@dataclass(frozen=True)
class SafeMarginState:
    mode: MarginMode
    value: float
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class ClipState:
    element_id: str
    explicit: bool
    target: str = "inherit"
    enabled: bool = True
    inset: float = 0.0


def _number(value: float | int | str, *, name: str, nonnegative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceEditError(f"{name} must be a number") from exc
    if nonnegative and result < 0:
        raise SourceEditError(f"{name} must not be negative")
    return result


def safe_margin_state(text: str) -> SafeMarginState:
    """Read the canvas safe margin, including schema-default fixed zero."""

    _, root = _load(text)
    canvas = root.get("canvas")
    if not isinstance(canvas, CommentedMap):
        raise SourceEditError("design canvas must be a YAML mapping")
    margin = canvas.get("safe_margin")
    if margin is None:
        return SafeMarginState("fixed", 0.0)
    if not isinstance(margin, CommentedMap):
        raise SourceEditError("canvas safe_margin must be a YAML mapping")
    if "fixed" in margin:
        return SafeMarginState(
            "fixed",
            _number(margin["fixed"], name="safe margin", nonnegative=True),
        )
    if "percent" in margin:
        minimum = margin.get("min")
        maximum = margin.get("max")
        return SafeMarginState(
            "percent",
            _number(margin["percent"], name="safe margin percent", nonnegative=True),
            None if minimum is None else _number(minimum, name="safe margin minimum", nonnegative=True),
            None if maximum is None else _number(maximum, name="safe margin maximum", nonnegative=True),
        )
    raise SourceEditError("canvas safe_margin must contain fixed or percent")


def set_safe_margin(
    text: str,
    *,
    mode: MarginMode,
    value: float | int | str,
    minimum: float | int | str | None = None,
    maximum: float | int | str | None = None,
) -> str:
    """Replace the safe-margin mapping with a schema-valid fixed/percent form."""

    yaml, root = _load(text)
    canvas = root.get("canvas")
    if not isinstance(canvas, CommentedMap):
        raise SourceEditError("design canvas must be a YAML mapping")
    amount = _number(value, name="safe margin", nonnegative=True)
    margin = CommentedMap()
    if mode == "fixed":
        margin["fixed"] = amount
    elif mode == "percent":
        margin["percent"] = amount
        if minimum not in {None, ""}:
            margin["min"] = _number(minimum, name="safe margin minimum", nonnegative=True)
        if maximum not in {None, ""}:
            margin["max"] = _number(maximum, name="safe margin maximum", nonnegative=True)
        if "min" in margin and "max" in margin and margin["min"] > margin["max"]:
            raise SourceEditError("safe margin minimum must not exceed maximum")
    else:
        raise SourceEditError(f"unsupported safe-margin mode {mode!r}")
    canvas["safe_margin"] = margin
    return _dump(yaml, root)


def clip_state(text: str, element_id: str) -> ClipState:
    """Read explicit clip settings, distinguishing omission/inheritance."""

    _, root = _load(text)
    element = _find_element(root, element_id)
    raw = element.get("clip")
    if raw is None:
        return ClipState(element_id=element_id, explicit=False)
    if not isinstance(raw, CommentedMap):
        raise SourceEditError(f"element {element_id!r} clip must be a YAML mapping")
    return ClipState(
        element_id=element_id,
        explicit=True,
        target=str(raw.get("target", "inherit")),
        enabled=bool(raw.get("enabled", True)),
        inset=_number(raw.get("inset", 0.0), name="clip inset"),
    )


def _validate_clip_target(target: str) -> str:
    value = target.strip()
    if value in {"inherit", "none", "patch", "safe-area"}:
        return value
    if value.startswith("custom:") and value.removeprefix("custom:").strip():
        return value
    raise SourceEditError(
        "clip target must be inherit, none, patch, safe-area or custom:<element-id>"
    )


def set_element_clip(
    text: str,
    element_id: str,
    *,
    explicit: bool,
    target: str = "inherit",
    enabled: bool = True,
    inset: float | int | str = 0.0,
) -> str:
    """Set or remove one element's explicit clip mapping."""

    yaml, root = _load(text)
    element = _find_element(root, element_id)
    if not explicit:
        element.pop("clip", None)
        return _dump(yaml, root)

    mapping = CommentedMap()
    mapping["target"] = _validate_clip_target(target)
    if not enabled:
        mapping["enabled"] = False
    offset = _number(inset, name="clip inset")
    if offset != 0.0:
        mapping["inset"] = offset
    element["clip"] = mapping
    return _dump(yaml, root)
