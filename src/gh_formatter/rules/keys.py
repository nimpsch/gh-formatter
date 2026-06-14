"""Rule: enforce standard key ordering in workflows and actions."""

from ruamel.yaml.comments import CommentedMap

from gh-formatter.context import Context
from gh-formatter.rules.base import BaseRule
from gh-formatter.utils import get_map, get_seq, reorder_commented_map

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
        reorder_commented_map(data, config.key_order_workflow)

        on_map = get_map(data, "on")
        if on_map is not None:
            for trigger in DEFINITION_TRIGGERS:
                trigger_map = get_map(on_map, trigger)
                if trigger_map is None:
                    continue
                _reorder_definitions(
                    get_map(trigger_map, "inputs"), INPUT_KEY_ORDER
                )
                _reorder_definitions(
                    get_map(trigger_map, "outputs"), OUTPUT_KEY_ORDER
                )
                # workflow_call secrets share the input definition shape
                _reorder_definitions(
                    get_map(trigger_map, "secrets"), INPUT_KEY_ORDER
                )

        jobs_map = get_map(data, "jobs")
        if jobs_map is not None:
            for job_def in jobs_map.values():
                if isinstance(job_def, CommentedMap):
                    reorder_commented_map(job_def, config.key_order_job)
                    _reorder_steps(job_def, config.key_order_step)

    def _format_action(self, data: CommentedMap, context: Context) -> None:
        config = context.config
        reorder_commented_map(data, config.key_order_action)

        _reorder_definitions(get_map(data, "inputs"), INPUT_KEY_ORDER)
        _reorder_definitions(get_map(data, "outputs"), OUTPUT_KEY_ORDER)

        runs_map = get_map(data, "runs")
        if runs_map is not None:
            reorder_commented_map(runs_map, RUNS_KEY_ORDER)
            # Composite actions carry their steps under runs
            _reorder_steps(runs_map, config.key_order_step)


def _reorder_definitions(
    definitions: CommentedMap | None, order: list[str]
) -> None:
    """Reorders the keys of each definition in an inputs/outputs map."""
    if definitions is None:
        return
    for definition in definitions.values():
        if isinstance(definition, CommentedMap):
            reorder_commented_map(definition, order)


def _reorder_steps(container: CommentedMap, order: list[str]) -> None:
    """Reorders the keys of each step in the container's steps sequence."""
    steps = get_seq(container, "steps")
    if steps is None:
        return
    for step in steps:
        if isinstance(step, CommentedMap):
            reorder_commented_map(step, order)
