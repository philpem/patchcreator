"""Round-trip YAML helpers used by structured GUI editing.

These helpers deliberately mutate the human-authored YAML source rather than a
second GUI document model.  The edited text is then reparsed by the normal
PatchCreator loader/render pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import re
from typing import Any, Literal

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError


PlacementMode = Literal["cartesian", "polar"]
_NUMBER_RE = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")


class SourceEditError(ValueError):
    pass


@dataclass(frozen=True)
class PlacementState:
    element_id: str
    mode: PlacementMode | None
    first: str = ""
    second: str = ""
    self_anchor: str = "centre"


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    return yaml


def _load(text: str) -> tuple[YAML, CommentedMap]:
    yaml = _yaml()
    try:
        root = yaml.load(text)
    except YAMLError as exc:
        raise SourceEditError(f"cannot edit invalid YAML: {str(exc).splitlines()[0]}") from exc
    if not isinstance(root, CommentedMap):
        raise SourceEditError("design root must be a YAML mapping")
    return yaml, root


def _iter_element_maps(elements: object):
    if not isinstance(elements, CommentedSeq):
        return
    for element in elements:
        if not isinstance(element, CommentedMap):
            continue
        yield element
        yield from _iter_element_maps(element.get("elements"))


def _find_element(root: CommentedMap, element_id: str) -> CommentedMap:
    matches: list[CommentedMap] = []
    layers = root.get("layers")
    if isinstance(layers, CommentedSeq):
        for layer in layers:
            if not isinstance(layer, CommentedMap):
                continue
            for element in _iter_element_maps(layer.get("elements")):
                if element.get("id") == element_id:
                    matches.append(element)
    if not matches:
        raise SourceEditError(f"element {element_id!r} does not exist in the current YAML source")
    if len(matches) > 1:
        raise SourceEditError(f"element id {element_id!r} is duplicated in the current YAML source")
    return matches[0]


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def placement_state(text: str, element_id: str) -> PlacementState:
    """Read the selected element's editable Cartesian/polar position."""

    _, root = _load(text)
    element = _find_element(root, element_id)
    position = element.get("position")
    if position is None:
        return PlacementState(element_id=element_id, mode=None)
    if not isinstance(position, CommentedMap):
        raise SourceEditError(f"element {element_id!r} has a non-mapping position")
    mode = position.get("mode")
    anchor = str(position.get("self_anchor", "centre"))
    if mode == "cartesian":
        return PlacementState(
            element_id=element_id,
            mode="cartesian",
            first=_display(position.get("x", 0)),
            second=_display(position.get("y", 0)),
            self_anchor=anchor,
        )
    if mode == "polar":
        return PlacementState(
            element_id=element_id,
            mode="polar",
            first=_display(position.get("angle", "")),
            second=_display(position.get("radius", "")),
            self_anchor=anchor,
        )
    raise SourceEditError(
        f"element {element_id!r} uses position mode {mode!r}; the GUI editor currently supports only cartesian/polar"
    )


def _editor_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        raise SourceEditError("placement values must not be empty")
    if _NUMBER_RE.fullmatch(value):
        number = float(value)
        return int(number) if number.is_integer() else number
    return value


def set_element_position(
    text: str,
    element_id: str,
    *,
    mode: PlacementMode,
    first: str,
    second: str,
) -> str:
    """Return YAML with one element's Cartesian/polar position updated.

    ``first``/``second`` are x/y in Cartesian mode and angle/radius in polar
    mode. Numeric strings become YAML numbers; unit/percentage/angle strings are
    preserved as strings for the normal schema/unit parser.
    """

    yaml, root = _load(text)
    element = _find_element(root, element_id)
    old = element.get("position")
    old_mode = old.get("mode") if isinstance(old, CommentedMap) else None
    anchor = str(old.get("self_anchor", "centre")) if isinstance(old, CommentedMap) else "centre"

    first_value = _editor_scalar(first)
    second_value = _editor_scalar(second)
    if isinstance(old, CommentedMap) and old_mode == mode:
        position = old
        if mode == "cartesian":
            position["x"] = first_value
            position["y"] = second_value
        else:
            position["angle"] = first_value
            position["radius"] = second_value
    else:
        position = CommentedMap()
        position["mode"] = mode
        if mode == "cartesian":
            position["x"] = first_value
            position["y"] = second_value
        else:
            position["angle"] = first_value
            position["radius"] = second_value
        if anchor != "centre":
            position["self_anchor"] = anchor
        element["position"] = position

    output = StringIO()
    yaml.dump(root, output)
    return output.getvalue()
