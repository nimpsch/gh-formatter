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
from gh_formatter.directives import mark_disabled_nodes, scan_disabled
from gh_formatter.rules.inputs import callable_input_names, plan_input_renames
from gh_formatter.utils import load_yaml

WORKFLOW_SUFFIXES = (".yml", ".yaml")


@dataclass
class ProjectPlan:
    """Each local target's canonical (post-format) declared input names.

    Callers are checked/fixed against these names; see CallerInputRule.
    """

    input_names: dict[Path, set[str]] = field(default_factory=dict)

    def input_names_for(self, candidates: list[Path]) -> set[str] | None:
        """Declared input names of the first known candidate, else None.

        None means no candidate is a local target in this run, so the caller
        cannot be checked.
        """
        for candidate in candidates:
            if candidate in self.input_names:
                return self.input_names[candidate]
        return None


def build_project_plan(files: list[Path], config: Config) -> ProjectPlan:
    """Records each local target's canonical declared input names."""
    plan = ProjectPlan()
    if config.caller_inputs == "ignore":
        return plan  # no cross-file checking needed

    naming_on = config.rule_enabled("input-naming")
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
            disable_file, disabled_lines = scan_disabled(content)
            if disable_file:
                continue  # a disabled file is never a checkable target
            data = load_yaml(content)
        except Exception:
            continue  # unreadable/unparsable files are reported later
        if not isinstance(data, CommentedMap):
            continue

        # Throwaway context only used to detect the file type, directives,
        # and the renames the definition itself will receive.
        context = Context(str(file_path), config)
        mark_disabled_nodes(data, disabled_lines, context)
        declared = callable_input_names(data, context)
        if declared is None:
            continue  # not callable; its callers cannot be input-checked
        # Store canonical (post-rename) names so they match callers once the
        # definition's own inputs have been formatted. An empty set is
        # recorded too: passing inputs to a zero-input target is an error.
        renames = plan_input_renames(data, context) if naming_on else {}
        plan.input_names[file_path.resolve()] = {
            renames.get(name, name) for name in declared
        }

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
