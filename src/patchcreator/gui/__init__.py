"""Optional GUI support built on the normal PatchCreator document pipeline.

Importing this package does not require Qt.  The reusable preview session stays
GUI-toolkit independent so tests and future front ends can share it.
"""

from .session import PreviewResult, PreviewSession

__all__ = ["PreviewResult", "PreviewSession"]
