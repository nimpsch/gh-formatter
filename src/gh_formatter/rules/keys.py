"""Rule: enforce standard key ordering in workflows and actions."""

from ruamel.yaml.comments import CommentedMap

from gh_formatter.comments import (
    promote_step_lead_comments,
    reorder_commented_map,
)
from gh_formatter.context import Context
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import get_map, get_seq

INPUT_KEY_ORDER = [
    "description",
    "required",
    "default",
    "type",
    "options",
    "deprecationMessage",
]

OUTPUT_KEY_ORDER = [
    "description",
    "value",
]

RUNS_KEY_ORDER = [
    "using",
    "main",
    "pre",
    "pre-if",
    "post",
    "post-if",
    "steps",
    "image",
    "entrypoint",
    "args",
    "env",
]

# Workflow triggers whose inputs/outputs/secrets definitions get reordered.
DEFINITION_TRIGGERS = ("workflow_dispatch", "workflow_call")


class KeyOrderingRule(BaseRule):
    @property
    def id(self) -> str:
        return "key-ordering"

    @property
    def description(self) -> str:
        return "Enforce standard key ordering in workflows and actions"

    def should_run(self, context: Context) -> bool:
        return True

    def apply(self, data: CommentedMap, context: Context) -> None:
        if context.file_type == "workflow":
            self._format_workflow(data, context)
        elif context.file_type == "action":
            self._format_action(data, context)

    def _format_workflow(self, data: CommentedMap, context: Context) -> None:
        config = context.config
        _reorder(data, config.key_order_workflow, context)

        on_map = get_map(data, "on")
        if on_map is not None:
            for trigger in DEFINITION_TRIGGERS:
                trigger_map = get_map(on_map, trigger)
                if trigger_map is None:
                    continue
                _reorder_definitions(
                    get_map(trigger_map, "inputs"), INPUT_KEY_ORDER, context
                )
                _reorder_definitions(
                    get_map(trigger_map, "outputs"), OUTPUT_KEY_ORDER, context
                )
                # workflow_call secrets share the input definition shape
                _reorder_definitions(
                    get_map(trigger_map, "secrets"), INPUT_KEY_ORDER, context
                )

        jobs_map = get_map(data, "jobs")
        if jobs_map is not None:
            for job_def in jobs_map.values():
                if isinstance(job_def, CommentedMap) and not context.is_ignored(
                    job_def
                ):
                    _reorder(job_def, config.key_order_job, context)
                    _reorder_steps(job_def, config.key_order_step, context)

    def _format_action(self, data: CommentedMap, context: Context) -> None:
        config = context.config
        _reorder(data, config.key_order_action, context)

        _reorder_definitions(get_map(data, "inputs"), INPUT_KEY_ORDER, context)
        _reorder_definitions(
            get_map(data, "outputs"), OUTPUT_KEY_ORDER, context
        )

        runs_map = get_map(data, "runs")
        if runs_map is not None and not context.is_ignored(runs_map):
            _reorder(runs_map, RUNS_KEY_ORDER, context)
            # Composite actions carry their steps under runs
            _reorder_steps(runs_map, config.key_order_step, context)


def _reorder(mapping: CommentedMap, order: list[str], context: Context) -> None:
    """Reorders a mapping unless a directive froze any of its keys."""
    if context.is_ignored(mapping) or context.has_frozen_keys(mapping):
        return
    reorder_commented_map(mapping, order)


def _reorder_definitions(
    definitions: CommentedMap | None, order: list[str], context: Context
) -> None:
    """Reorders the keys of each definition in an inputs/outputs map."""
    if definitions is None or context.is_ignored(definitions):
        return
    for definition in definitions.values():
        if isinstance(definition, CommentedMap):
            _reorder(definition, order, context)


def _reorder_steps(
    container: CommentedMap, order: list[str], context: Context
) -> None:
    """Reorders the keys of each step in the container's steps sequence."""
    steps = get_seq(container, "steps")
    if steps is None:
        return
    for step in steps:
        if isinstance(step, CommentedMap):
            _reorder(step, order, context)
    promote_step_lead_comments(container)
