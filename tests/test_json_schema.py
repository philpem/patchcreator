from __future__ import annotations

import json

from patchcreator.cli import main
from patchcreator.config import (
    DESIGN_SCHEMA_ID,
    JSON_SCHEMA_DIALECT,
    design_json_schema,
    design_json_schema_text,
)


def test_design_json_schema_is_derived_open_component_schema():
    schema = design_json_schema()

    assert schema["$schema"] == JSON_SCHEMA_DIALECT
    assert schema["$id"] == DESIGN_SCHEMA_ID
    assert schema["title"] == "DesignSpec"

    definitions = schema["$defs"]
    assert "ElementSpec" in definitions
    assert definitions["ElementSpec"]["additionalProperties"] is True

    assert definitions["CartesianPosition"]["properties"]["mode"]["const"] == "cartesian"
    assert definitions["PolarPosition"]["properties"]["mode"]["const"] == "polar"
    assert definitions["RelativePosition"]["properties"]["mode"]["const"] == "relative"
    assert definitions["PathPosition"]["properties"]["mode"]["const"] == "path"

    position_schema = definitions["ElementSpec"]["properties"]["position"]
    encoded = json.dumps(position_schema, sort_keys=True)
    assert '"propertyName": "mode"' in encoded
    assert "#/$defs/CartesianPosition" in encoded
    assert "#/$defs/PolarPosition" in encoded


def test_schema_text_is_deterministic_pretty_json():
    first = design_json_schema_text()
    second = design_json_schema_text()

    assert first == second
    assert first.endswith("\n")
    assert "\n  " in first
    assert json.loads(first)["$id"] == DESIGN_SCHEMA_ID


def test_schema_cli_prints_json_to_stdout(capsys):
    assert main(["schema"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    schema = json.loads(captured.out)
    assert schema["$schema"] == JSON_SCHEMA_DIALECT
    assert schema["$id"] == DESIGN_SCHEMA_ID


def test_schema_cli_writes_output_file(tmp_path, capsys):
    output = tmp_path / "design-schema.json"

    assert main(["schema", "-o", str(output)]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.strip() == str(output)
    assert output.read_text(encoding="utf-8") == design_json_schema_text()
