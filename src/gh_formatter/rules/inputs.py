"""Rule: standardize input name casing and update references."""

from collections.abc import Iterator
from functools import partial

from ruamel.yaml.comments import CommentedMap

from gh_formatter.casing import compute_safe_renames
from gh_formatter.context import Context
from gh_formatter.references import (
    replace_expression_references,
    transform_strings_in_place,
)
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import get_map, rename_commented_map_keys

# Expression prefixes under which inputs are referenced.
INPUT_REFERENCE_PREFIXES = ("inputs", "github.event.inputs")

# Workflow triggers that can declare inputs.
INPUT_TRIGGERS = ("workflow_dispatch", "workflow_call")


def find_input_maps(
    data: CommentedMap, context: Context
) -> Iterator[CommentedMap]:
    """Yields every inputs map the current file type can declare."""
    if context.file_type == "action":
        inputs_map = get_map(data, "inputs")
        if inputs_map is not None:
            yield inputs_map
        return

    on_map = get_map(data, "on")
    if on_map is None:
        return
    for trigger in INPUT_TRIGGERS:
        trigger_map = get_map(on_map, trigger)
        if trigger_map is not None:
            inputs_map = get_map(trigger_map, "inputs")
            if inputs_map is not None:
                yield inputs_map


def plan_input_renames(data: CommentedMap, context: Context) -> dict[str, str]:
    """Computes the input renames this file would receive, without applying.

    Used both by InputNamingRule itself and by the project-level planner
    that propagates renames to callers in other files; both must agree.
    """
    renames: dict[str, str] = {}
    for inputs_map in find_input_maps(data, context):
        if context.is_ignored(inputs_map):
            continue
        renames.update(_renames_for_inputs_map(inputs_map, context))
    return renames


def _renames_for_inputs_map(
    inputs_map: CommentedMap, context: Context
) -> dict[str, str]:
    """Safe renames for one inputs map, skipping directive-frozen keys."""
    renames = compute_safe_renames(
        list(inputs_map.keys()),
        context.config.input_casing,
        context,
        "input",
        preserve_uppercase=context.config.preserve_uppercase_names,
    )
    return {
        old: new
        for old, new in renames.items()
        if not context.is_frozen(inputs_map, old)
    }


class InputNamingRule(BaseRule):
    @property
    def id(self) -> str:
        return "input-naming"

    @property
    def description(self) -> str:
        return "Standardize input casings and rename internal input references"

    def should_run(self, context: Context) -> bool:
        return True

    def apply(self, data: CommentedMap, context: Context) -> None:
        for inputs_map in find_input_maps(data, context):
            if context.is_ignored(inputs_map):
                continue
            renames = _renames_for_inputs_map(inputs_map, context)
            if not renames:
                continue

            rename_commented_map_keys(inputs_map, renames)

            for old_name, new_name in renames.items():
                transform_strings_in_place(
                    data,
                    partial(
                        replace_expression_references,
                        prefixes=INPUT_REFERENCE_PREFIXES,
                        old_name=old_name,
                        new_name=new_name,
                    ),
                )
