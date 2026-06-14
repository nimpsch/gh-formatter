"""Project-level planning for cross-file input rename propagation.

When a formatting run renames the inputs of a reusable workflow or a
local action, every caller inside the same repository references those
inputs through `uses: ./...` plus a `with:` block. The plan built here
records the renames per target file so the caller side can be updated
consistently — but only for targets that are part of the same run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml.comments import CommentedMap

from gh_formatter.config import Config
from gh_formatter.context import Context
from gh_formatter.rules.inputs import plan_input_renames
from gh_formatter.utils import load_yaml

WORKFLOW_SUFFIXES = (".yml", ".yaml")


@dataclass
class ProjectPlan:
    """Planned input renames per resolved target file path."""

    input_renames: dict[Path, dict[str, str]] = field(default_factory=dict)

    def renames_for(self, candidates: list[Path]) -> dict[str, str]:
        """Returns the renames of the first candidate present in the plan."""
        for candidate in candidates:
            renames = self.input_renames.get(candidate)
            if renames:
                return renames
        return {}


def build_project_plan(files: list[Path], config: Config) -> ProjectPlan:
    """Computes the input renames every file in the run will receive."""
    plan = ProjectPlan()
    if not config.rule_enabled("input-naming"):
        return plan

    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
            data = load_yaml(content)
        except Exception:
            continue  # unreadable/unparsable files are reported later
        if not isinstance(data, CommentedMap):
            continue

        # Throwaway context: warnings are emitted again (and surfaced)
        # when the file itself is formatted.
        context = Context(str(file_path), config)
        renames = plan_input_renames(data, context)
        if renames:
            plan.input_renames[file_path.resolve()] = renames

    return plan


def find_repo_root(file_path: str | None) -> Path | None:
    """Finds the repository root that `uses: ./...` paths are relative to."""
    if not file_path:
        return None
    for ancestor in Path(file_path).resolve().parents:
        if (ancestor / ".github").is_dir() or (ancestor / ".git").exists():
            return ancestor
    return None


def resolve_local_uses(uses: str, repo_root: Path) -> list[Path]:
    """Returns candidate definition files for a local `uses: ./...` ref.

    A reference ending in .yml/.yaml is a reusable workflow file; anything
    else is an action directory whose definition is action.yml or
    action.yaml.
    """
    if not uses.startswith("./"):
        return []
    target = repo_root / uses[2:].strip("/")
    if target.suffix in WORKFLOW_SUFFIXES:
        return [target.resolve()]
    return [
        (target / "action.yml").resolve(),
        (target / "action.yaml").resolve(),
    ]
