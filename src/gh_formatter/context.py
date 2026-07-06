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
        # Hard lint errors (e.g. a caller input mismatch under the "error"
        # policy); the CLI fails the run when any are present.
        self.errors: list[str] = []
        # Set by the CLI for cross-file rename propagation; None when
        # formatting a file in isolation.
        self.project_plan: ProjectPlan | None = None
        # Populated from inline directives (see directives.py): keys/nodes a
        # developer asked the formatter to leave alone. Keyed by object id so
        # they survive the in-place mutations the rules perform.
        self.frozen_keys: dict[int, set[str]] = {}
        self.ignored_ids: set[int] = set()

    def add_warning(self, message: str) -> None:
        """Records a warning to be surfaced to the user."""
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        """Records a lint error that must be fixed (fails the run)."""
        self.errors.append(message)

    def freeze_key(self, mapping: object, key: str) -> None:
        """Marks a key as exempt from renaming, reordering, and reformatting."""
        self.frozen_keys.setdefault(id(mapping), set()).add(key)

    def is_frozen(self, mapping: object, key: str) -> bool:
        """Whether this key was disabled via an inline directive."""
        return key in self.frozen_keys.get(id(mapping), ())

    def has_frozen_keys(self, mapping: object) -> bool:
        """Whether any key of this mapping was disabled."""
        return bool(self.frozen_keys.get(id(mapping)))

    def ignore_node(self, node: object) -> None:
        """Marks a whole node (and its subtree) as exempt from formatting."""
        self.ignored_ids.add(id(node))

    def is_ignored(self, node: object) -> bool:
        """Whether this node was disabled via an inline directive."""
        return id(node) in self.ignored_ids

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
