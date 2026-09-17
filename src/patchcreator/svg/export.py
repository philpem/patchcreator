"""Conservative compatibility/export pass for editable master SVG artwork.

The master SVG deliberately retains authoring metadata, construction geometry,
Inkscape layers and reusable references. This module produces a second SVG
variant aimed at downstream importers without changing the master document.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from patchcreator.assets.normalize import _flatten_safe_leaf_transforms
from patchcreator.svg.knockout import KnockoutResult, apply_knockout
from patchcreator.svg.text_outline import TextOutlineError, TextOutlineResult, outline_straight_text
from patchcreator.svg.text_path_general import outline_general_text_paths
from patchcreator.svg.text_path_outline import outline_arc_text

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
PATCHCREATOR_NS = "https://philpem.github.io/patchcreator/ns"
XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", SVG_NS)

_URL_REF_RE = re.compile(r"url\(\s*#([^)\s]+)\s*\)")


class CompatibilityExportError(ValueError):
    """Requested compatibility operation cannot be performed safely."""


@dataclass(frozen=True)
class ExportOptions:
    expand_use: bool = True
    flatten_safe_transforms: bool = True
    remove_debug_layer: bool = True
    remove_construction: bool = True
    strip_inkscape_metadata: bool = True
    strip_patchcreator_metadata: bool = True
    prune_unused_defs: bool = True
    text_mode: str = "preserve"
    knockout: bool = False
    font_path: str | Path | None = None
    font_search_paths: tuple[str | Path, ...] = ()

    def __post_init__(self) -> None:
        if self.text_mode not in {"preserve", "paths"}:
            raise ValueError("text_mode must be 'preserve' or 'paths'")


@dataclass(frozen=True)
class ExportResult:
    svg: str
    expanded_use_count: int = 0
    flattened_transform_count: int = 0
    removed_construction_count: int = 0
    removed_debug_layer_count: int = 0
    pruned_defs_count: int = 0
    knockout_changed_fragments: int = 0
    knockout_removed_fragments: int = 0
    outlined_text_count: int = 0
    warnings: tuple[str, ...] = ()


def _q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(name: str) -> str | None:
    if name.startswith("{") and "}" in name:
        return name[1:].split("}", 1)[0]
    return None


def _parse_svg(text: str) -> ET.Element:
    if "<!DOCTYPE" in text.upper():
        raise CompatibilityExportError(
            "SVG files with a DOCTYPE are not accepted for compatibility export"
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise CompatibilityExportError(f"cannot parse SVG: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise CompatibilityExportError("compatibility export input is not an SVG document")
    return root


def _id_index(root: ET.Element) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for element in root.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        if element_id in result:
            raise CompatibilityExportError(f"duplicate SVG id {element_id!r}")
        result[element_id] = element
    return result


def _rewrite_clone_ids(root: ET.Element, prefix: str) -> None:
    id_map: dict[str, str] = {}
    for element in root.iter():
        old = element.get("id")
        if not old:
            continue
        new = f"{prefix}-{old}"
        id_map[old] = new
        element.set("id", new)

    def rewrite(value: str) -> str:
        if value.startswith("#") and value[1:] in id_map:
            value = "#" + id_map[value[1:]]
        return _URL_REF_RE.sub(
            lambda match: f"url(#{id_map.get(match.group(1), match.group(1))})",
            value,
        )

    for element in root.iter():
        for key, value in list(element.attrib.items()):
            element.set(key, rewrite(value))


def _use_href(element: ET.Element) -> str | None:
    return element.get("href") or element.get(_q(XLINK_NS, "href"))


def _clone_use_target(use: ET.Element, target: ET.Element, serial: int) -> ET.Element:
    wrapper = ET.Element(_q(SVG_NS, "g"))
    for key, value in use.attrib.items():
        if key not in {"href", _q(XLINK_NS, "href"), "x", "y", "transform"}:
            wrapper.set(key, value)
    if use.get("transform"):
        wrapper.set("transform", use.get("transform", ""))

    parent = wrapper
    x = use.get("x", "0").strip()
    y = use.get("y", "0").strip()
    if x not in {"", "0", "0.0"} or y not in {"", "0", "0.0"}:
        translated = ET.SubElement(wrapper, _q(SVG_NS, "g"), {"transform": f"translate({x} {y})"})
        parent = translated

    if _local_name(target.tag) == "symbol":
        children = [copy.deepcopy(child) for child in target]
        holder = ET.Element(_q(SVG_NS, "g"))
        for child in children:
            holder.append(child)
        _rewrite_clone_ids(holder, f"compat-use-{serial:04d}")
        for child in list(holder):
            holder.remove(child)
            parent.append(child)
    else:
        clone = copy.deepcopy(target)
        _rewrite_clone_ids(clone, f"compat-use-{serial:04d}")
        parent.append(clone)
    return wrapper


def _expand_internal_uses(root: ET.Element) -> int:
    expanded = 0
    serial = 0
    for _ in range(64):
        index = _id_index(root)
        changed = False

        def visit(parent: ET.Element) -> None:
            nonlocal expanded, serial, changed
            for position, child in list(enumerate(list(parent))):
                if _local_name(child.tag) != "use":
                    visit(child)
                    continue
                href = _use_href(child)
                if not href or not href.startswith("#"):
                    raise CompatibilityExportError(
                        f"cannot expand external or missing <use> reference {href!r}"
                    )
                target_id = href[1:]
                target = index.get(target_id)
                if target is None:
                    raise CompatibilityExportError(
                        f"cannot expand <use>: target {target_id!r} does not exist"
                    )
                if target is child:
                    raise CompatibilityExportError(f"recursive <use> reference {target_id!r}")
                serial += 1
                replacement = _clone_use_target(child, target, serial)
                parent.remove(child)
                parent.insert(position, replacement)
                expanded += 1
                changed = True

        visit(root)
        if not changed:
            return expanded
    raise CompatibilityExportError("<use> expansion exceeded recursion limit")


def _remove_matching(root: ET.Element, predicate) -> int:
    removed = 0

    def visit(parent: ET.Element) -> None:
        nonlocal removed
        for child in list(parent):
            if predicate(child):
                parent.remove(child)
                removed += 1
            else:
                visit(child)

    visit(root)
    return removed


def _remove_debug_layers(root: ET.Element) -> int:
    return _remove_matching(
        root,
        lambda element: element.get("id") == "patchcreator-validation"
        or element.get(_q(PATCHCREATOR_NS, "role")) == "validation-overlay"
        or element.get("data-patchcreator-role") == "validation-overlay",
    )


def _remove_construction_geometry(root: ET.Element) -> int:
    return _remove_matching(
        root,
        lambda element: element.get(_q(PATCHCREATOR_NS, "construction-role")) is not None
        or element.get("data-patchcreator-construction-role") is not None,
    )


def _strip_metadata(root: ET.Element, options: ExportOptions) -> None:
    removable_tag_namespaces: set[str] = set()
    removable_attr_namespaces: set[str] = set()
    if options.strip_inkscape_metadata:
        removable_tag_namespaces.update({INKSCAPE_NS, SODIPODI_NS})
        removable_attr_namespaces.update({INKSCAPE_NS, SODIPODI_NS})
    if options.strip_patchcreator_metadata:
        removable_tag_namespaces.add(PATCHCREATOR_NS)
        removable_attr_namespaces.add(PATCHCREATOR_NS)

    _remove_matching(root, lambda element: _namespace(element.tag) in removable_tag_namespaces)

    for element in root.iter():
        for key in list(element.attrib):
            namespace = _namespace(key)
            if namespace in removable_attr_namespaces:
                del element.attrib[key]
                continue
            if options.strip_patchcreator_metadata and key.startswith("data-patchcreator-"):
                del element.attrib[key]


def _references_in(root: ET.Element, *, include_defs: bool) -> set[str]:
    refs: set[str] = set()

    def visit(element: ET.Element, inside_defs: bool = False) -> None:
        now_defs = inside_defs or _local_name(element.tag) == "defs"
        if include_defs or not now_defs:
            for key, value in element.attrib.items():
                if _local_name(key) == "href" and value.startswith("#"):
                    refs.add(value[1:])
                refs.update(_URL_REF_RE.findall(value))
        for child in element:
            visit(child, now_defs)

    visit(root)
    return refs


def _prune_unused_defs(root: ET.Element) -> int:
    defs_nodes = [element for element in root if _local_name(element.tag) == "defs"]
    if not defs_nodes:
        return 0

    referenced = _references_in(root, include_defs=False)
    changed = True
    while changed:
        changed = False
        index = _id_index(root)
        for target_id in tuple(referenced):
            target = index.get(target_id)
            if target is None:
                continue
            before = len(referenced)
            for element in target.iter():
                for key, value in element.attrib.items():
                    if _local_name(key) == "href" and value.startswith("#"):
                        referenced.add(value[1:])
                    referenced.update(_URL_REF_RE.findall(value))
            changed = changed or len(referenced) != before

    removed = 0
    for defs in defs_nodes:
        for child in list(defs):
            child_id = child.get("id")
            if child_id and child_id not in referenced:
                defs.remove(child)
                removed += 1
    return removed


def export_svg_text(text: str, *, options: ExportOptions | None = None) -> ExportResult:
    options = options or ExportOptions()

    root = _parse_svg(text)
    removed_debug = _remove_debug_layers(root) if options.remove_debug_layer else 0
    expanded = _expand_internal_uses(root) if options.expand_use else 0

    if options.text_mode == "paths":
        try:
            general_path_result = outline_general_text_paths(
                root,
                font_path=options.font_path,
                search_directories=options.font_search_paths or None,
            )
            arc_result = outline_arc_text(
                root,
                font_path=options.font_path,
                search_directories=options.font_search_paths or None,
            )
            straight_result = outline_straight_text(
                root,
                font_path=options.font_path,
                search_directories=options.font_search_paths or None,
            )
            text_result = TextOutlineResult(
                converted_count=(
                    general_path_result.converted_count
                    + arc_result.converted_count
                    + straight_result.converted_count
                ),
                warnings=(
                    general_path_result.warnings
                    + arc_result.warnings
                    + straight_result.warnings
                ),
            )
        except TextOutlineError as exc:
            raise CompatibilityExportError(str(exc)) from exc
    else:
        text_result = TextOutlineResult(converted_count=0)

    # Text outlining deliberately runs before construction removal so both
    # specialised PatchCreator arcs and ordinary textPath baselines can be
    # consumed before authoring-only guides are discarded.
    removed_construction = _remove_construction_geometry(root) if options.remove_construction else 0
    flattened = _flatten_safe_leaf_transforms(root) if options.flatten_safe_transforms else 0

    if options.knockout:
        try:
            knockout_result = apply_knockout(root)
        except ValueError as exc:
            raise CompatibilityExportError(str(exc)) from exc
    else:
        knockout_result = KnockoutResult(changed_fragments=0, removed_fragments=0)

    pruned = _prune_unused_defs(root) if options.prune_unused_defs else 0
    _strip_metadata(root, options)

    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode", xml_declaration=False) + "\n"
    return ExportResult(
        svg=xml,
        expanded_use_count=expanded,
        flattened_transform_count=flattened,
        removed_construction_count=removed_construction,
        removed_debug_layer_count=removed_debug,
        pruned_defs_count=pruned,
        knockout_changed_fragments=knockout_result.changed_fragments,
        knockout_removed_fragments=knockout_result.removed_fragments,
        outlined_text_count=text_result.converted_count,
        warnings=text_result.warnings + knockout_result.warnings,
    )


def export_svg_file(
    source: str | Path,
    output: str | Path,
    *,
    options: ExportOptions | None = None,
) -> ExportResult:
    source_path = Path(source)
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CompatibilityExportError(f"cannot read SVG {source_path}: {exc}") from exc
    result = export_svg_text(text, options=options)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(result.svg, encoding="utf-8")
    return result