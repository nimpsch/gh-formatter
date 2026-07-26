"""Structured diagnostics emitted while formatting a file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """How serious a diagnostic is.

    WARNING is informational (the run still succeeds); ERROR must be fixed
    by the user and fails the run.
    """

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single finding surfaced to the user, tied to the file it came from.

    ``line``/``column`` are 1-based (editor convention) and ``None`` when the
    finding has no single YAML location (e.g. a required input that is
    missing entirely).
    """

    severity: Severity
    message: str
    line: int | None = None
    column: int | None = None
