"""Derive editable offset clip paths from rendered component silhouettes."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from patchcreator.geometry.boolean import geometry_to_svg_path, offset_geometry
from patchcreator.validation.geometry import iter_visible_fills

SVG_NS = "http://www.w3.org/2000/svg"

_NON_RENDERED = {"defs", "clipPath", "mask", "marker", "metadata", "title", "desc", "symbol"}
_AREA_TAGS = {"g", "svg", "a", "path", "rect", "circle", "ellipse", "polygon", "polyline"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _display_none(element: ET.Element) -> bool:
    if (element.get("display") or "").strip().lower() == "none":
        return True
    style = element.get("style", "")
    for declaration in style.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        if name.strip().lower() == "display" and value.strip().lower() == "none":
            return True
    return False


def _validate_offsettable_subtree(root: ET.Element) -> None:
    """Refuse constructs the analysis silhouette cannot reproduce exactly."""

    def visit(element: ET.Element, hidden: bool, non_rendered: bool) -> None:
        tag = _local_name(element.tag)
        now_hidden = hidden or _display_none(element)
        now_non_rendered = non_rendered or tag in _NON_RENDERED
        if now_hidden or now_non_rendered:
            return

        for attribute in ("clip-path", "mask", "filter"):
            if element.get(attribute) not in {None, "", "none"}:
                raise ValueError(
                    f"cannot offset custom clip geometry containing {attribute}; "
                    "normalize or use an unclipped filled silhouette"
                )

        if tag not in _AREA_TAGS:
            raise ValueError(
                f"cannot offset custom clip geometry containing visible <{tag}>; "
                "use filled path/primitive geometry or normalize the asset first"
            )
        for child in element:
            visit(child, now_hidden, now_non_rendered)

    visit(root, False, False)


def filled_silhouette_local(group: ET.Element) -> BaseGeometry:
    """Return the rendered group's filled silhouette in its own local mm frame.

    The scene-placement transform on the component group is intentionally
    removed; descendant transforms remain part of the authored silhouette.
    """
    clone = copy.deepcopy(group)
    clone.attrib.pop("transform", None)
    clone.attrib.pop("clip-path", None)
    _validate_offsettable_subtree(clone)

    temporary = ET.Element(
        f"{{{SVG_NS}}}svg",
        {"width": "1mm", "height": "1mm", "viewBox": "0 0 1 1"},
    )
    temporary.append(clone)
    geometries = [item.geometry for item in iter_visible_fills(temporary)]
    if not geometries:
        raise ValueError("custom clip target has no supported visible filled geometry to offset")
    result = unary_union(geometries)
    if result.is_empty:
        raise ValueError("custom clip target has an empty filled silhouette")
    return result


def offset_group_svg_path(group: ET.Element, *, inset_mm: float) -> str:
    silhouette = filled_silhouette_local(group)
    offset = offset_geometry(silhouette, inset_mm=inset_mm)
    return geometry_to_svg_path(offset)
