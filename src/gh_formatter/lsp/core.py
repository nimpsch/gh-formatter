"""Pure, pygls-free helpers behind the LSP server's request handlers.

Kept separate from server.py so these can be unit-tested without the
optional `pygls`/`lsprotocol` dependency installed, and so the actual
protocol glue in server.py stays a thin translation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ruamel.yaml.error import MarkedYAMLError, StreamMark

from gh_formatter.config import Config
from gh_formatter.core.context import Context
from gh_formatter.core.diagnostics import Diagnostic
from gh_formatter.core.pipeline import Engine


@dataclass(frozen=True)
class ParseErrorLocation:
    """1-based location of a YAML syntax error, plus its message."""

    line: int | None
    column: int | None
    message: str


@dataclass(frozen=True)
class FormatOutcome:
    """Result of running the formatting pipeline over in-memory text."""

    formatted_text: str | None  # None when parse_error is set
    diagnostics: list[Diagnostic] = field(default_factory=list)
    parse_error: ParseErrorLocation | None = None


def run_pipeline(
    engine: Engine, content: str, file_path: str | None, config: Config
) -> FormatOutcome:
    """Runs `Engine.format_string` over in-memory text, never raising.

    Mirrors app/service.py's process_file error handling, but returns the
    formatted text directly instead of writing it to disk -- the right
    shape for an editor's live (possibly unsaved) buffer.
    """
    context = Context(file_path, config)
    try:
        formatted = engine.format_string(content, context)
    except MarkedYAMLError as e:
        line, column = _mark_location(e.problem_mark)
        return FormatOutcome(
            formatted_text=None,
            diagnostics=context.diagnostics,
            parse_error=ParseErrorLocation(line, column, str(e.problem or e)),
        )
    return FormatOutcome(formatted, context.diagnostics)


def _mark_location(mark: StreamMark | None) -> tuple[int | None, int | None]:
    """A ruamel mark's 1-based (line, column), or (None, None) if absent."""
    if mark is None:
        return None, None
    return mark.line + 1, mark.column + 1


def diagnostic_to_lsp_range(
    line: int | None, column: int | None, source_lines: list[str]
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Converts a 1-based (line, column) point into a 0-based LSP range.

    gh-formatter diagnostics are point locations, not spans. The range is
    extended to the end of its source line so the squiggle is actually
    visible instead of a single, easy-to-miss character; a missing or
    out-of-bounds location falls back to a single character at (0, 0).

    Returns ((start_line, start_char), (end_line, end_char)), 0-based.
    """
    if line is None or column is None:
        return (0, 0), (0, 1)

    line_index = line - 1
    if line_index < 0 or line_index >= len(source_lines):
        return (0, 0), (0, 1)

    start_char = max(column - 1, 0)
    end_char = max(len(source_lines[line_index].rstrip("\n\r")), start_char + 1)
    return (line_index, start_char), (line_index, end_char)
