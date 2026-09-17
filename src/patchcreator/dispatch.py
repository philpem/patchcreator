"""Top-level command dispatcher.

The established argparse CLI remains unchanged.  Only the optional GUI command
is intercepted here so Qt is never imported for normal command-line use.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "gui":
        from patchcreator.gui.app import main as gui_main

        return int(gui_main(args[1:]))

    from patchcreator.cli import main as cli_main

    return int(cli_main(args))
