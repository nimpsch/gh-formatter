"""Rule: keep local `uses:` callers consistent with their target's interface.

The behaviour is controlled by the ``caller_inputs`` config option:

* ``error`` (default) -- a with-key or secrets-key that is not declared by
  the local target is reported as an error, to be fixed by hand in both
  files.
* ``fix`` -- the caller's keys are renamed to the matching declared name
  (at the user's own risk); keys with no recognizable match still error.
* ``ignore`` -- caller inputs are left alone.

With ``require_explicit_inputs`` (default on), callers must also pass every
input and secret the target declares -- optional ones included -- so the
call site documents the full interface. ``secrets: inherit`` satisfies the
secrets side.

Only local references (`uses: ./...`) whose target is part of the same run
are considered; marketplace actions are never touched.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from ruamel.yaml.comments import CommentedMap

from gh_formatter.core.context import Context
from gh_formatter.core.rules.base import BaseRule
from gh_formatter.core.tree import get_map, get_seq, rename_commented_map_keys

if TYPE_CHECKING:
    from gh_formatter.app.planning import CallerInterface

# A caller mapping (job or step) together with its `uses:` value.
Caller = tuple[CommentedMap, str]


class CallerInputRule(BaseRule):
    """Validates or fixes local `uses:` callers per the caller_inputs mode."""

    @property
    def id(self) -> str:
        return "caller-inputs"

    @property
    def description(self) -> str:
        return "Check/fix local uses: callers against the target's interface"

    def should_run(self, context: Context) -> bool:
        plan = context.project_plan
        return (
            plan is not None
            and bool(plan.input_names or plan.secret_names)
            and context.config.caller_inputs != "ignore"
        )

    def apply(self, data: CommentedMap, context: Context) -> None:
        plan = context.project_plan
        if plan is None:
            return

        for caller, uses in iter_local_callers(data):
            interface = plan.interface_for(uses, context.file_path)
            if interface is None:
                continue  # not a local target in this run: cannot check
            _check_inputs(caller, uses, interface, context)
            _check_secrets(caller, uses, interface, context)


def iter_local_callers(data: CommentedMap) -> Iterator[Caller]:
    """Yields every mapping with a `uses:` reference (jobs and steps)."""
    jobs = get_map(data, "jobs")
    if jobs is not None:
        for job in jobs.values():
            if isinstance(job, CommentedMap):
                yield from _caller(job)
                yield from _step_callers(job)

    # Composite actions call local actions from runs.steps.
    runs = get_map(data, "runs")
    if runs is not None:
        yield from _step_callers(runs)


def _step_callers(container: CommentedMap) -> Iterator[Caller]:
    steps = get_seq(container, "steps")
    if steps is None:
        return
    for step in steps:
        if isinstance(step, CommentedMap):
            yield from _caller(step)


def _caller(mapping: CommentedMap) -> Iterator[Caller]:
    uses = mapping.get("uses")
    if isinstance(uses, str):
        yield mapping, uses


def _check_inputs(
    caller: CommentedMap,
    uses: str,
    interface: CallerInterface,
    context: Context,
) -> None:
    if interface.inputs is None:
        return  # this target's inputs cannot be checked
    with_map = get_map(caller, "with")
    _check_block(with_map, interface.inputs, uses, "with", context)


def _check_secrets(
    caller: CommentedMap,
    uses: str,
    interface: CallerInterface,
    context: Context,
) -> None:
    if interface.secrets is None:
        return  # not a local reusable workflow: no secrets to check
    if isinstance(caller.get("secrets"), str):
        return  # `secrets: inherit` forwards everything
    secrets_map = get_map(caller, "secrets")
    _check_block(secrets_map, interface.secrets, uses, "secrets", context)


def _check_block(
    block: CommentedMap | None,
    declared: set[str],
    uses: str,
    label: str,
    context: Context,
) -> None:
    """Runs the mismatch and completeness checks on one caller block."""
    suggested: set[str] = set()
    if block is not None:
        if context.config.caller_inputs == "fix":
            _fix_keys(block, declared, uses, label, context)
        else:
            suggested = _report_keys(block, declared, uses, label, context)
    if context.config.require_explicit_inputs:
        passed = set(block.keys()) if block is not None else set()
        # A declared name already suggested as the fix for a mismatched key
        # is covered by that error; reporting it as missing too is noise.
        for name in sorted(declared - passed - suggested):
            context.add_error(
                f"{label}: '{name}' declared by local target '{uses}' is "
                f"not passed explicitly - pass it even if a default exists"
            )


def _fix_keys(
    block: CommentedMap,
    declared: set[str],
    uses: str,
    label: str,
    context: Context,
) -> None:
    """Renames caller keys to the declared name they most likely mean.

    Keys with no recognizable counterpart cannot be fixed automatically and
    are still reported as errors -- the workflow would fail on GitHub.
    """
    renames: dict[str, str] = {}
    for key in list(block):
        if key in declared:
            continue
        match = _closest_name(key, declared)
        if match is None:
            context.add_error(
                f"{label}: '{key}' is not declared by local target "
                f"'{uses}' and has no close match - fix it manually"
            )
            continue
        if match in block:
            context.add_warning(
                f"Skipped fixing '{key}' in {label}: of '{uses}': "
                f"'{match}' is already present"
            )
            continue
        renames[key] = match

    if renames:
        rename_commented_map_keys(block, renames)


def _report_keys(
    block: CommentedMap,
    declared: set[str],
    uses: str,
    label: str,
    context: Context,
) -> set[str]:
    """Reports each caller key that is not a declared name as an error.

    Returns the declared names suggested as close matches, so the caller
    can skip redundant missing-name reports for them.
    """
    suggested: set[str] = set()
    for key in block:
        if key in declared:
            continue
        match = _closest_name(key, declared)
        if match is not None:
            suggested.add(match)
        hint = f" (did you mean '{match}'?)" if match else ""
        context.add_error(
            f"{label}: input '{key}' is not declared by local target "
            f"'{uses}'{hint} - fix it in both files"
        )
    return suggested


def _closest_name(key: str, declared: set[str]) -> str | None:
    """A declared name matching `key` apart from casing/separators, if any."""
    target = _slug(key)
    for name in declared:
        if _slug(name) == target:
            return name
    return None


def _slug(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "")
