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

from gh_formatter.app.planning import ProjectPlan
from gh_formatter.config import Config
from gh_formatter.core.context import Context
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
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
    except Exception as e:
        return FileResult(
            FileStatus.ERROR,
            f"Failed to parse/format file: {e}",
            context.warnings,
            context.errors,
        )

    if source.content == formatted and not source.needs_newline_fix:
        return FileResult(
            FileStatus.UNCHANGED,
            "Already formatted",
            context.warnings,
            context.errors,
        )

    if show_diff:
        diff = difflib.unified_diff(
            source.content.splitlines(keepends=True),
            formatted.splitlines(keepends=True),
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
        )
        return FileResult(
            FileStatus.CHANGED, "".join(diff), context.warnings, context.errors
        )

    if check:
        return FileResult(
            FileStatus.CHANGED,
            "Needs formatting",
            context.warnings,
            context.errors,
        )

    try:
        write_source(file_path, formatted, source.newline)
    except Exception as e:
        return FileResult(
            FileStatus.ERROR,
            f"Failed to write file: {e}",
            context.warnings,
            context.errors,
        )

    return FileResult(
        FileStatus.CHANGED,
        "Formatted successfully",
        context.warnings,
        context.errors,
    )
