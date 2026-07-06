"""Rule: keep local `uses:` callers' with-keys consistent with their target.

The behaviour is controlled by the ``caller_inputs`` config option:

* ``error`` (default) -- a with-key that is not a declared input of the local
  target is reported as an error, to be fixed by hand in both files.
* ``fix`` -- the caller's keys are renamed to the matching declared input
  (at the user's own risk).
* ``ignore`` -- caller inputs are left alone.

Only local references (`uses: ./...`) whose target is part of the same run
are considered; marketplace actions are never touched.
"""

from collections.abc import Iterator
from pathlib import Path

from ruamel.yaml.comments import CommentedMap

from gh_formatter.context import Context
from gh_formatter.project import find_repo_root, resolve_local_uses
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import get_map, get_seq, rename_commented_map_keys

# A local caller: its `uses:` value, its `with:` map, and the candidate
# target files the `uses:` resolves to.
Caller = tuple[str, CommentedMap, list[Path]]


class CallerInputRule(BaseRule):
    """Validates or fixes local `uses:` with-keys per the caller_inputs mode."""

    @property
    def id(self) -> str:
        return "caller-inputs"

    @property
    def description(self) -> str:
        return "Check/fix local uses: with-keys against the target's inputs"

    def should_run(self, context: Context) -> bool:
        plan = context.project_plan
        return (
            plan is not None
            and bool(plan.input_names)
            and context.config.caller_inputs != "ignore"
        )

    def apply(self, data: CommentedMap, context: Context) -> None:
        plan = context.project_plan
        repo_root = find_repo_root(context.file_path)
        if plan is None or repo_root is None:
            return

        fix = context.config.caller_inputs == "fix"
        for uses, with_map, candidates in iter_local_callers(data, repo_root):
            declared = plan.input_names_for(candidates)
            if declared is None:
                continue  # not a local target in this run: cannot check
            if fix:
                _fix_with_keys(with_map, declared, uses, context)
            else:
                _report_with_keys(with_map, declared, uses, context)


def iter_local_callers(data: CommentedMap, repo_root: Path) -> Iterator[Caller]:
    """Yields every `uses: ./...` call that has a `with:` block."""
    jobs = get_map(data, "jobs")
    if jobs is not None:
        for job in jobs.values():
            if isinstance(job, CommentedMap):
                yield from _callers_in_job(job, repo_root)

    # Composite actions call local actions from runs.steps.
    runs = get_map(data, "runs")
    if runs is not None:
        yield from _step_callers(runs, repo_root)


def _callers_in_job(job: CommentedMap, repo_root: Path) -> Iterator[Caller]:
    yield from _caller(job, repo_root)  # job-level reusable workflow call
    yield from _step_callers(job, repo_root)  # step-level action calls


def _step_callers(container: CommentedMap, repo_root: Path) -> Iterator[Caller]:
    steps = get_seq(container, "steps")
    if steps is None:
        return
    for step in steps:
        if isinstance(step, CommentedMap):
            yield from _caller(step, repo_root)


def _caller(mapping: CommentedMap, repo_root: Path) -> Iterator[Caller]:
    uses = mapping.get("uses")
    with_map = get_map(mapping, "with")
    if isinstance(uses, str) and with_map is not None:
        yield uses, with_map, resolve_local_uses(uses, repo_root)


def _fix_with_keys(
    with_map: CommentedMap, declared: set[str], uses: str, context: Context
) -> None:
    """Renames caller keys to the declared input they most likely mean.

    Keys with no recognizable counterpart cannot be fixed automatically and
    are still reported as errors -- the workflow would fail on GitHub.
    """
    renames: dict[str, str] = {}
    for key in list(with_map):
        if key in declared:
            continue
        match = _closest_input(key, declared)
        if match is None:
            context.add_error(
                f"with: input '{key}' is not declared by local target "
                f"'{uses}' and has no close match - fix it manually"
            )
            continue
        if match in with_map:
            context.add_warning(
                f"Skipped fixing '{key}' in with: of '{uses}': "
                f"'{match}' is already present"
            )
            continue
        renames[key] = match

    if renames:
        rename_commented_map_keys(with_map, renames)


def _report_with_keys(
    with_map: CommentedMap, declared: set[str], uses: str, context: Context
) -> None:
    """Reports each caller key that is not a declared input as an error."""
    for key in with_map:
        if key in declared:
            continue
        match = _closest_input(key, declared)
        hint = f" (did you mean '{match}'?)" if match else ""
        context.add_error(
            f"with: input '{key}' is not declared by local target "
            f"'{uses}'{hint} - fix it in both files"
        )


def _closest_input(key: str, declared: set[str]) -> str | None:
    """A declared input matching `key` apart from casing/separators, if any."""
    target = _slug(key)
    for name in declared:
        if _slug(name) == target:
            return name
    return None


def _slug(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "")
