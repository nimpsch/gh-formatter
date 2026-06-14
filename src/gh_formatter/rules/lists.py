"""Rule: normalize trigger filter lists under `on:` to the configured style."""

from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from gh_formatter.context import Context
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import get_map


class ListStyleRule(BaseRule):
    """Applies flow or block style to trigger filter lists.

    Deliberately scoped to the `on:` section: the same key names
    (`branches`, `types`, ...) can appear as plain string inputs inside a
    step's `with:` block, where converting them to lists would change the
    workflow's behavior.
    """

    @property
    def id(self) -> str:
        return "list-style"

    @property
    def description(self) -> str:
        return "Enforce flow or block style on trigger filter lists"

    def should_run(self, context: Context) -> bool:
        return context.file_type == "workflow"

    def apply(self, data: CommentedMap, context: Context) -> None:
        on_map = get_map(data, "on")
        if on_map is None or context.is_ignored(on_map):
            return
        _apply_list_style(
            on_map,
            context.config.list_style,
            set(context.config.list_keys),
            context,
        )


def _apply_list_style(
    data: Any, style: str, list_keys: set[str], context: Context
) -> None:
    """Recursively finds list keys and applies the configured style."""
    if isinstance(data, dict):
        for key, value in list(data.items()):
            if context.is_frozen(data, key) or context.is_ignored(value):
                continue
            if key in list_keys:
                # Promote single string to list
                if isinstance(value, str):
                    value = CommentedSeq([value])
                    data[key] = value

                if isinstance(value, CommentedSeq):
                    if style == "flow":
                        value.fa.set_flow_style()
                    else:
                        value.fa.set_block_style()
            else:
                _apply_list_style(value, style, list_keys, context)
    elif isinstance(data, list):
        for item in data:
            if not context.is_ignored(item):
                _apply_list_style(item, style, list_keys, context)
