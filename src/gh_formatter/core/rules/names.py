"""Rule: capitalize display names of workflows, jobs, and steps."""

from ruamel.yaml.comments import CommentedMap

from gh_formatter.core.context import Context
from gh_formatter.core.rules.base import BaseRule
from gh_formatter.core.tree import get_map, get_seq, restyle_scalar


class CapitalizeNamesRule(BaseRule):
    """Capitalizes the first letter of display names only.

    Only the workflow/action name, job names, and step names are touched.
    `name` keys elsewhere (e.g. inside a step's `with:` block) are data —
    such as artifact names — and changing them would alter behavior.
    """

    @property
    def id(self) -> str:
        return "capitalize-names"

    @property
    def description(self) -> str:
        return "Capitalize the first letter of display names"

    def should_run(self, context: Context) -> bool:
        return True

    def apply(self, data: CommentedMap, context: Context) -> None:
        _capitalize_name(data, context)

        if context.file_type == "workflow":
            jobs_map = get_map(data, "jobs")
            if jobs_map is not None:
                for job_def in jobs_map.values():
                    if isinstance(job_def, CommentedMap) and not (
                        context.is_ignored(job_def)
                    ):
                        _capitalize_name(job_def, context)
                        _capitalize_step_names(job_def, context)
        else:
            runs_map = get_map(data, "runs")
            if runs_map is not None and not context.is_ignored(runs_map):
                _capitalize_step_names(runs_map, context)


def _capitalize_name(mapping: CommentedMap, context: Context) -> None:
    if context.is_ignored(mapping) or context.is_frozen(mapping, "name"):
        return
    value = mapping.get("name")
    if isinstance(value, str) and value:
        capitalized = value[0].upper() + value[1:]
        if capitalized != value:
            mapping["name"] = restyle_scalar(value, capitalized)


def _capitalize_step_names(container: CommentedMap, context: Context) -> None:
    steps = get_seq(container, "steps")
    if steps is None:
        return
    for step in steps:
        if isinstance(step, CommentedMap) and not context.is_ignored(step):
            _capitalize_name(step, context)
