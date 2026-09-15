"""YAML loading with source-oriented validation diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from .schema import DesignSpec


@dataclass(frozen=True)
class Diagnostic:
    message: str
    path: tuple[str | int, ...] = ()
    line: int | None = None
    column: int | None = None

    def format(self, source: str | None = None) -> str:
        where = source or ""
        if self.line is not None:
            where += f":{self.line}"
            if self.column is not None:
                where += f":{self.column}"
        if self.path:
            dotted = ".".join(str(part) for part in self.path)
            where += (": " if where else "") + dotted
        return f"{where}: {self.message}" if where else self.message


class DesignLoadError(ValueError):
    def __init__(self, source: str | None, diagnostics: Iterable[Diagnostic]):
        self.source = source
        self.diagnostics = tuple(diagnostics)
        super().__init__("\n".join(d.format(source) for d in self.diagnostics))


def _location_for(root: Any, path: tuple[str | int, ...]) -> tuple[int | None, int | None]:
    """Best-effort 1-based location lookup for a Pydantic error path."""
    current = root
    line: int | None = None
    column: int | None = None

    for part in path:
        try:
            if isinstance(current, CommentedMap) and isinstance(part, str):
                pos = current.lc.key(part)
                if pos is not None:
                    line, column = pos[0] + 1, pos[1] + 1
                current = current[part]
            elif isinstance(current, CommentedSeq) and isinstance(part, int):
                pos = current.lc.item(part)
                if pos is not None:
                    line, column = pos[0] + 1, pos[1] + 1
                current = current[part]
            else:
                break
        except (KeyError, IndexError, TypeError):
            break
    return line, column


def _diagnostics_from_validation(root: Any, exc: ValidationError) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for error in exc.errors(include_url=False):
        path = tuple(error.get("loc", ()))
        line, column = _location_for(root, path)
        diagnostics.append(
            Diagnostic(
                message=error["msg"],
                path=path,
                line=line,
                column=column,
            )
        )
    return diagnostics


def loads_design(text: str, *, source: str | None = None) -> DesignSpec:
    yaml = YAML(typ="rt")
    try:
        raw = yaml.load(text)
    except YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        diagnostic = Diagnostic(
            message=str(exc).splitlines()[0],
            line=(mark.line + 1) if mark is not None else None,
            column=(mark.column + 1) if mark is not None else None,
        )
        raise DesignLoadError(source, [diagnostic]) from exc

    if raw is None:
        raise DesignLoadError(source, [Diagnostic("design document is empty")])
    if not isinstance(raw, CommentedMap):
        raise DesignLoadError(source, [Diagnostic("design root must be a YAML mapping")])

    try:
        return DesignSpec.model_validate(raw)
    except ValidationError as exc:
        raise DesignLoadError(source, _diagnostics_from_validation(raw, exc)) from exc


def load_design(path: str | Path) -> DesignSpec:
    path = Path(path)
    design = loads_design(path.read_text(encoding="utf-8"), source=str(path))
    design.set_source_dir(path.parent)
    return design
