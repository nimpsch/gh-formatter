"""Formatting a single file: read, format, and (optionally) write back.

This module is frontend-agnostic: it never prints and never exits. The CLI
(and any future GUI / editor extension / GitHub Action frontend) consumes
FileResult values and decides how to present them.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ruamel.yaml.error import MarkedYAMLError, StreamMark

from gh_formatter.app.planning import ProjectPlan
from gh_formatter.config import Config
from gh_formatter.core.context import Context
from gh_formatter.core.diagnostics import Diagnostic, Severity
from gh_formatter.core.pipeline import Engine
from gh_formatter.io.files import read_source, write_source


class FileStatus(Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    ERROR = "error"


@dataclass
class FileResult:
    status: FileStatus
    message: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # Location of `message` itself, when it's a single located failure (a
    # YAML syntax error) rather than a per-diagnostic finding.
    line: int | None = None
    column: int | None = None

    @property
    def warnings(self) -> list[str]:
        """Warning messages, in the order they were recorded."""
        return [
            d.message
            for d in self.diagnostics
            if d.severity is Severity.WARNING
        ]

    @property
    def errors(self) -> list[str]:
        """Error messages, in the order they were recorded."""
        return [
            d.message for d in self.diagnostics if d.severity is Severity.ERROR
        ]


def _mark_location(mark: StreamMark | None) -> tuple[int | None, int | None]:
    """A ruamel mark's 1-based (line, column), or (None, None) if absent."""
    if mark is None:
        return None, None
    return mark.line + 1, mark.column + 1


def process_file(
    file_path: Path,
    engine: Engine,
    config: Config,
    check: bool,
    show_diff: bool,
    plan: ProjectPlan | None = None,
) -> FileResult:
    """Processes a single file, formatting it or checking for changes."""
    try:
        source = read_source(file_path, config)
    except Exception as e:
        return FileResult(FileStatus.ERROR, f"Failed to read file: {e}")

    context = Context(str(file_path), config)
    context.project_plan = plan

    try:
        formatted = engine.format_string(source.content, context)
    except MarkedYAMLError as e:
        line, column = _mark_location(e.problem_mark)
        return FileResult(
            FileStatus.ERROR,
            f"Invalid YAML: {e.problem or e}",
            context.diagnostics,
            line,
            column,
        )
    except Exception as e:
        return FileResult(
            FileStatus.ERROR,
            f"Failed to parse/format file: {e}",
            context.diagnostics,
        )

    if source.content == formatted and not source.needs_newline_fix:
        return FileResult(
            FileStatus.UNCHANGED, "Already formatted", context.diagnostics
        )

    if show_diff:
        diff = difflib.unified_diff(
            source.content.splitlines(keepends=True),
            formatted.splitlines(keepends=True),
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
        )
        return FileResult(
            FileStatus.CHANGED, "".join(diff), context.diagnostics
        )

    if check:
        return FileResult(
            FileStatus.CHANGED, "Needs formatting", context.diagnostics
        )

    try:
        write_source(file_path, formatted, source.newline)
    except Exception as e:
        return FileResult(
            FileStatus.ERROR, f"Failed to write file: {e}", context.diagnostics
        )

    return FileResult(
        FileStatus.CHANGED, "Formatted successfully", context.diagnostics
    )
