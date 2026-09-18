"""Runtime version resolution from installed distribution metadata."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version


def resolve_version() -> str:
    """Return the installed PatchCreator version or a source-tree fallback."""

    try:
        return distribution_version("patchcreator")
    except PackageNotFoundError:
        return "0+unknown"
