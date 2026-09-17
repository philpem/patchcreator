"""Machine-readable schema derived from the authoritative Pydantic design model."""

from __future__ import annotations

import json
from typing import Any

from .schema import DesignSpec

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
DESIGN_SCHEMA_ID = "https://philpem.github.io/patchcreator/schema/design-0.1.json"


def design_json_schema() -> dict[str, Any]:
    """Return JSON Schema for a PatchCreator 0.1 design document.

    Component-specific fields deliberately remain open on ElementSpec because
    PatchCreator components and third-party plugins extend the shared element
    envelope dynamically. Core document/placement/profile structure still comes
    directly from the same Pydantic models used by the YAML loader.
    """

    schema = DesignSpec.model_json_schema()
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": DESIGN_SCHEMA_ID,
        **schema,
    }


def design_json_schema_text() -> str:
    """Return deterministic, human-readable JSON Schema text."""

    return json.dumps(
        design_json_schema(),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
