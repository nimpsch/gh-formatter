"""Per-file runtime context shared by all rules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from gh_formatter.config import Config

if TYPE_CHECKING:
    from gh_formatter.project import ProjectPlan

FileType = Literal["workflow", "action"]


class Context:
    """Carries the file path, config, detected file type, and warnings.

    Rules append to ``warnings`` when they skip an unsafe change (for
    example a rename that would collide with an existing key); the CLI
    reports them to the user after processing each file.
    """

    def __init__(self, file_path: str | None, config: Config):
        self.file_path = file_path
        self.config = config
        self.file_type: FileType = self._detect_file_type()
        self.warnings: list[str] = []
        # Set by the CLI for cross-file rename propagation; None when
        # formatting a file in isolation.
        self.project_plan: ProjectPlan | None = None

    def add_warning(self, message: str) -> None:
        """Records a warning to be surfaced to the user."""
        self.warnings.append(message)

    def _detect_file_type(self) -> FileType:
        if not self.file_path:
            return "workflow"  # Default fallback

        path = Path(self.file_path).resolve()

        # Standard workflow location (as_posix always uses forward slashes)
        if ".github/workflows" in path.as_posix():
            return "workflow"

        # Standard action file names
        if path.name in ("action.yml", "action.yaml"):
            return "action"

        # Fall back to filename hints; default to workflow (most common).
        if "workflow" in path.name.lower():
            return "workflow"
        if "action" in path.name.lower():
            return "action"

        return "workflow"
