"""PatchCreator command-line interface.

CLI handlers intentionally stay thin: parsing, scene construction and SVG
writing live in the library so the future GUI can use the same code paths.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from patchcreator import __version__
from patchcreator.assets import AssetReport, inspect_asset, normalize_asset
from patchcreator.components import UnsupportedComponentError
from patchcreator.config.loader import DesignLoadError, load_design
from patchcreator.data import (
    DataSourceError,
    fetch_dataset,
    is_dataset_installed,
    load_data_catalog,
    require_dataset,
    resolve_data_root,
)
from patchcreator.profiles import ProfileError, load_profile_catalog, resolve_profile
from patchcreator.svg.writer import write_design_svg


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        design = load_design(args.design)
        output = Path(args.output) if args.output else Path(args.design).with_suffix(".svg")
        result = write_design_svg(design, output, allow_unsupported=args.allow_unsupported)
    except (DesignLoadError, DataSourceError, UnsupportedComponentError, OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(output)
    return 0


def _not_implemented(command: str) -> int:
    print(f"patchcreator {command}: not implemented yet", file=sys.stderr)
    return 2


def _cmd_check(args: argparse.Namespace) -> int:
    return _not_implemented("check")


def _format_bounds(report: AssetReport) -> str:
    if report.bounds is None:
        return "-"
    bounds = report.bounds
    return (
        f"{bounds.min_x:.6g},{bounds.min_y:.6g} "
        f"{bounds.max_x:.6g},{bounds.max_y:.6g} "
        f"({bounds.width:.6g} x {bounds.height:.6g})"
    )


def _print_asset_report(report: AssetReport) -> None:
    if report.viewbox is None:
        viewbox = "-"
    else:
        viewbox = " ".join(f"{value:.6g}" for value in report.viewbox)
    width, height = report.physical_size_mm
    physical = (
        f"{width:.6g} x {height:.6g} mm"
        if width is not None and height is not None
        else "-"
    )
    print(f"source: {report.source}")
    print(f"viewBox: {viewbox}")
    print(f"physical-size: {physical}")
    print(f"geometry-bounds: {_format_bounds(report)}")
    print(f"anchors: {', '.join(report.anchors) if report.anchors else '-'}")
    print(f"colour-roles: {', '.join(report.colour_roles) if report.colour_roles else '-'}")
    print(f"transforms: {report.transform_count}")
    if report.flattened_transform_count:
        print(f"flattened-transforms: {report.flattened_transform_count}")
    if report.unsupported_geometry:
        print("unsupported-geometry: " + ", ".join(report.unsupported_geometry))


def _cmd_normalize(args: argparse.Namespace) -> int:
    source = Path(args.asset)
    mutating = args.fix_viewbox or args.flatten_safe_transforms
    try:
        if not mutating:
            report = inspect_asset(source)
        else:
            if args.in_place and args.output:
                raise ValueError("--in-place and --output are mutually exclusive")
            if args.in_place:
                destination = source
            elif args.output:
                destination = Path(args.output)
            else:
                raise ValueError(
                    "normalization changes require --output FILE or --in-place; "
                    "omit mutation options for inspection only"
                )
            report = normalize_asset(
                source,
                output=destination,
                fix_viewbox=args.fix_viewbox,
                padding=args.padding,
                flatten_safe_transforms=args.flatten_safe_transforms,
            )
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    _print_asset_report(report)
    return 0


def _profile_catalog(args: argparse.Namespace):
    return load_profile_catalog(args.profile_path or ())


def _cmd_profiles_list(args: argparse.Namespace) -> int:
    try:
        catalog = _profile_catalog(args)
    except ProfileError as exc:
        print(exc, file=sys.stderr)
        return 2
    for entry in catalog.entries():
        marker = " experimental" if entry.profile.experimental else ""
        print(f"{entry.profile.kind:7} {entry.profile.name}{marker}\t{entry.source}")
    return 0


def _cmd_profiles_show(args: argparse.Namespace) -> int:
    try:
        entry = _profile_catalog(args).get(args.kind, args.name)
    except ProfileError as exc:
        print(exc, file=sys.stderr)
        return 2
    profile = entry.profile
    print(f"name: {profile.name}")
    print(f"kind: {profile.kind}")
    print(f"source: {entry.source}")
    print(f"experimental: {str(profile.experimental).lower()}")
    if profile.description:
        print(f"description: {profile.description}")
    print("constraints:")
    for key, value in profile.constraints.model_dump().items():
        if value is not None:
            print(f"  {key}: {str(value).lower() if isinstance(value, bool) else value}")
    return 0


def _cmd_profiles_effective(args: argparse.Namespace) -> int:
    try:
        design = load_design(args.design)
        effective = resolve_profile(design.profile, _profile_catalog(args))
    except (DesignLoadError, OSError, ProfileError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"machine: {effective.machine or '-'}")
    print(f"intent: {effective.intent or '-'}")
    print("constraints:")
    for key, value in effective.constraints.model_dump().items():
        if value is not None:
            print(f"  {key}: {str(value).lower() if isinstance(value, bool) else value}")
    print("sources:")
    for source in effective.sources:
        print(f"  - {source}")
    return 0


def _data_root(args: argparse.Namespace) -> Path:
    return resolve_data_root(args.data_dir)


def _cmd_data_list(args: argparse.Namespace) -> int:
    try:
        catalog = load_data_catalog()
        root = _data_root(args)
    except DataSourceError as exc:
        print(exc, file=sys.stderr)
        return 2
    for source in catalog.entries():
        status = "installed" if is_dataset_installed(source, root=root) else "missing"
        print(f"{status:9} {source.name}\tversion {source.version}\t{source.url}")
    return 0


def _cmd_data_fetch(args: argparse.Namespace) -> int:
    try:
        path = fetch_dataset(args.name, root=_data_root(args), force=args.force)
    except (DataSourceError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(path)
    return 0


def _cmd_data_path(args: argparse.Namespace) -> int:
    try:
        path = require_dataset(args.name, root=_data_root(args))
    except DataSourceError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(path)
    return 0


def _add_profile_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile-path",
        action="append",
        metavar="DIR",
        help="additional profile directory; may be specified more than once",
    )


def _add_data_dir_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        help="external data cache root (overrides PATCHCREATOR_DATA_DIR/XDG cache)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchcreator", description="Build editable mission-patch SVG artwork")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render", help="render a YAML design to SVG")
    render.add_argument("design", help="input YAML design")
    render.add_argument("-o", "--output", help="output SVG path (default: input name with .svg)")
    render.add_argument(
        "--allow-unsupported",
        action="store_true",
        help="skip component types not implemented by the current renderer",
    )
    render.set_defaults(func=_cmd_render)

    check = subparsers.add_parser("check", help="analyse an SVG for embroidery geometry problems")
    check.add_argument("artwork")
    check.set_defaults(func=_cmd_check)

    normalize = subparsers.add_parser("normalize", help="inspect/normalise a reusable SVG asset")
    normalize.add_argument("asset")
    normalize.add_argument("-o", "--output", help="write a normalised copy to FILE")
    normalize.add_argument("--in-place", action="store_true", help="replace the input asset")
    normalize.add_argument(
        "--fix-viewbox",
        action="store_true",
        help="replace viewBox with conservative visible-geometry bounds",
    )
    normalize.add_argument(
        "--padding",
        type=float,
        default=0.0,
        metavar="UNITS",
        help="padding to add around geometry when fixing viewBox",
    )
    normalize.add_argument(
        "--flatten-safe-transforms",
        action="store_true",
        help="bake leaf translate/uniform-scale transforms into supported primitive geometry",
    )
    normalize.set_defaults(func=_cmd_normalize)

    profiles = subparsers.add_parser("profiles", help="inspect embroidery profiles")
    profile_sub = profiles.add_subparsers(dest="profiles_command", required=True)

    profile_list = profile_sub.add_parser("list", help="list available profiles")
    _add_profile_path_argument(profile_list)
    profile_list.set_defaults(func=_cmd_profiles_list)

    profile_show = profile_sub.add_parser("show", help="show one profile")
    profile_show.add_argument("kind", choices=("machine", "intent"))
    profile_show.add_argument("name")
    _add_profile_path_argument(profile_show)
    profile_show.set_defaults(func=_cmd_profiles_show)

    profile_effective = profile_sub.add_parser("effective", help="show effective profile for a design")
    profile_effective.add_argument("design")
    _add_profile_path_argument(profile_effective)
    profile_effective.set_defaults(func=_cmd_profiles_effective)

    data = subparsers.add_parser("data", help="manage explicitly downloaded external datasets")
    data_sub = data.add_subparsers(dest="data_command", required=True)

    data_list = data_sub.add_parser("list", help="list known datasets and installation state")
    _add_data_dir_argument(data_list)
    data_list.set_defaults(func=_cmd_data_list)

    data_fetch = data_sub.add_parser("fetch", help="download and install one named dataset")
    data_fetch.add_argument("name")
    data_fetch.add_argument("--force", action="store_true", help="replace an existing cached copy")
    _add_data_dir_argument(data_fetch)
    data_fetch.set_defaults(func=_cmd_data_fetch)

    data_path = data_sub.add_parser("path", help="print the installed path for one dataset")
    data_path.add_argument("name")
    _add_data_dir_argument(data_path)
    data_path.set_defaults(func=_cmd_data_path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
