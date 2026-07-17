"""Rule: wrap bare `if:` conditions in ${{ }} for a consistent style."""

from ruamel.yaml.comments import CommentedMap

from gh_formatter.core.context import Context
from gh_formatter.core.rules.base import BaseRule
from gh_formatter.core.tree import get_map, get_seq


class IfExpressionRule(BaseRule):
    """Normalizes job and step `if:` conditions to the ${{ }} form.

    GitHub lets you omit ${{ }} around an `if:` expression, so the same
    condition is often written both ways across a repo. This rule wraps any
    bare condition (one that does not already contain ${{) so every `if:`
    reads the same -- which also sidesteps the YAML gotcha where a condition
    starting with `!` must be wrapped.
    """

    @property
    def id(self) -> str:
        return "if-expressions"

    @property
    def description(self) -> str:
        return "Wrap bare `if:` conditions in ${{ }}"

    def should_run(self, context: Context) -> bool:
        return True

    def apply(self, data: CommentedMap, context: Context) -> None:
        if context.file_type == "workflow":
            jobs = get_map(data, "jobs")
            if jobs is None:
                return
            for job in jobs.values():
                if isinstance(job, CommentedMap) and not context.is_ignored(
                    job
                ):
                    _wrap_if(job, context)
                    _wrap_step_ifs(job, context)
        else:
            runs = get_map(data, "runs")
            if runs is not None and not context.is_ignored(runs):
                _wrap_step_ifs(runs, context)


def _wrap_step_ifs(container: CommentedMap, context: Context) -> None:
    """Wraps the `if:` of every step under the container's steps sequence."""
    steps = get_seq(container, "steps")
    if steps is None:
        return
    for step in steps:
        if isinstance(step, CommentedMap) and not context.is_ignored(step):
            _wrap_if(step, context)


def _wrap_if(mapping: CommentedMap, context: Context) -> None:
    """Wraps a single mapping's `if:` value in ${{ }} when it is bare."""
    if context.is_frozen(mapping, "if"):
        return
    value = mapping.get("if")
    if not isinstance(value, str):
        return  # leave YAML booleans (if: true) and missing keys alone
    text = value.strip()
    if not text or "${{" in text:
        return  # already wrapped (or partially), assume intentional
    mapping["if"] = f"${{{{ {text} }}}}"
