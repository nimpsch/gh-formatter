"""Rule: propagate input renames to local `uses:` callers."""

from pathlib import Path

from ruamel.yaml.comments import CommentedMap

from gh_formatter.context import Context
from gh_formatter.project import ProjectPlan, find_repo_root, resolve_local_uses
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import get_map, get_seq, rename_commented_map_keys


class CallerInputNamingRule(BaseRule):
    """Renames `with:` keys for calls into local workflows and actions.

    When the same formatting run renames the inputs of a reusable workflow
    or action referenced via `uses: ./...`, the caller's `with:` block is
    updated to match. Targets outside the run are never touched, so a
    partial run cannot desynchronize caller and definition.
    """

    @property
    def id(self) -> str:
        return "caller-input-naming"

    @property
    def description(self) -> str:
        return (
            "Rename with: keys of local uses: calls whose target inputs "
            "were renamed"
        )

    def should_run(self, context: Context) -> bool:
        plan = context.project_plan
        return plan is not None and bool(plan.input_renames)

    def apply(self, data: CommentedMap, context: Context) -> None:
        plan = context.project_plan
        repo_root = find_repo_root(context.file_path)
        if plan is None or repo_root is None:
            return

        jobs_map = get_map(data, "jobs")
        if jobs_map is not None:
            for job_def in jobs_map.values():
                if isinstance(job_def, CommentedMap):
                    # Job-level uses: reusable workflow call
                    self._rename_with_keys(job_def, plan, repo_root, context)
                    self._rename_steps(job_def, plan, repo_root, context)

        # Composite actions call local actions from runs.steps
        runs_map = get_map(data, "runs")
        if runs_map is not None:
            self._rename_steps(runs_map, plan, repo_root, context)

    def _rename_steps(
        self,
        container: CommentedMap,
        plan: ProjectPlan,
        repo_root: Path,
        context: Context,
    ) -> None:
        steps = get_seq(container, "steps")
        if steps is None:
            return
        for step in steps:
            if isinstance(step, CommentedMap):
                self._rename_with_keys(step, plan, repo_root, context)

    @staticmethod
    def _rename_with_keys(
        caller: CommentedMap,
        plan: ProjectPlan,
        repo_root: Path,
        context: Context,
    ) -> None:
        uses = caller.get("uses")
        with_map = get_map(caller, "with")
        if not isinstance(uses, str) or with_map is None:
            return

        candidates = resolve_local_uses(uses, repo_root)
        renames = plan.renames_for(candidates)

        applicable: dict[str, str] = {}
        for old_name, new_name in renames.items():
            if old_name not in with_map:
                continue
            if new_name in with_map:
                context.add_warning(
                    f"Skipped renaming '{old_name}' in with: of '{uses}': "
                    f"'{new_name}' is already present"
                )
                continue
            applicable[old_name] = new_name

        if applicable:
            rename_commented_map_keys(with_map, applicable)
