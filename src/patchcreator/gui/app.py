"""Console entry point for the optional PatchCreator GUI."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchcreator-gui", description="Edit PatchCreator YAML with live SVG preview")
    parser.add_argument("design", nargs="?", help="optional YAML design to open")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from .qt_app import run_gui
    except ImportError as exc:
        print(
            "PatchCreator GUI dependencies are not installed. "
            "Install them with: pip install -e '.[gui]'",
            file=sys.stderr,
        )
        print(f"detail: {exc}", file=sys.stderr)
        return 2

    path = Path(args.design) if args.design else None
    return int(run_gui(path))
