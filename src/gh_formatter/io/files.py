"""Reading and writing workflow files with line-ending awareness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gh_formatter.config import Config, LineEndings


@dataclass(frozen=True, slots=True)
class SourceFile:
    """A workflow file's decoded text plus its write-back policy."""

    content: str
    newline: str
    # True when the configured "lf" policy alone requires a rewrite (the
    # text may be unchanged but the CRLF endings still must be converted).
    needs_newline_fix: bool


def read_source(path: Path, config: Config) -> SourceFile:
    """Reads a file, normalizing to LF in memory and recording the policy.

    "preserve" keeps the file's existing line endings on write instead of
    letting Python translate to the platform default.
    """
    raw = path.read_bytes()
    if config.line_endings == LineEndings.LF:
        newline = "\n"
    else:
        newline = "\r\n" if b"\r\n" in raw else "\n"
    needs_newline_fix = config.line_endings == LineEndings.LF and b"\r\n" in raw
    content = raw.decode("utf-8").replace("\r\n", "\n")
    return SourceFile(content, newline, needs_newline_fix)


def write_source(path: Path, text: str, newline: str) -> None:
    """Writes formatted text back with the recorded line-ending policy."""
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)
