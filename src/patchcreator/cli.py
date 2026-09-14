"""PatchCreator command-line interface.

CLI handlers intentionally stay thin: parsing, scene construction and SVG
writing live in the library so the future GUI can use the same code paths.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from patchcreator import __version__
from patchcreator.components import UnsupportedComponentError
from patchcreator.config.loader import DesignLoadError, load_design
from patchcreator.profiles import ProfileError, load_profile_catalog, resolve_profile
from patchcreator.svg.writer import write_design_svg


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        design = load_design(args.design)
        output = Path(args.output) if args.output else Path(args.design).with_suffix(".svg")
        result = write_design_svg(design, output, allow_unsupported=args.allow_unsupported)
    except (DesignLoadError, UnsupportedComponentError, ValueError) as exc:
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


def _cmd_normalize(args: argparse.Namespace) -> int:
    return _not_implemented("normalize")


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
    except (DesignLoadError, ProfileError) as exc:
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


def _add_profile_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile-path",
        action="append",
        metavar="DIR",
        help="additional profile directory; may be specified more than once",
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
