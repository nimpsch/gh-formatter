"""Rule: sort configured mapping blocks (env, inputs, ...) alphabetically."""

from typing import Any

from ruamel.yaml.comments import CommentedMap

from gh_formatter.comments import (
    hoist_dedented_comments,
    reorder_commented_map,
)
from gh_formatter.context import Context
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import iter_tree_slots


class AlphabetizeRule(BaseRule):
    """Sorts the entries of selected blocks alphabetically.

    Which blocks are sorted is configured via the ``alphabetize`` option
    (by default: env, inputs, outputs, secrets, and with). Only mapping
    values are touched, entry order in these blocks never carries meaning,
    and comments travel with their entry. Runs after the naming rules so
    the sorted order reflects the final key names.
    """

    @property
    def id(self) -> str:
        return "alphabetize"

    @property
    def description(self) -> str:
        return "Sort configured blocks (env, inputs, ...) alphabetically"

    def should_run(self, context: Context) -> bool:
        return bool(context.config.alphabetize)

    def apply(self, data: CommentedMap, context: Context) -> None:
        blocks = set(context.config.alphabetize)
        for _container, key, value in iter_tree_slots(data, context):
            if (
                key in blocks
                and isinstance(value, CommentedMap)
                and not context.has_frozen_keys(value)
            ):
                # A comment between two map-valued entries hangs off the
                # previous entry; reattach it first so it sorts correctly.
                hoist_dedented_comments(value)
                reorder_commented_map(value, _sorted_keys(value))


def _sorted_keys(mapping: CommentedMap) -> list[str]:
    """Keys sorted case-insensitively, with a deterministic tiebreak."""

    def sort_key(key: Any) -> tuple[str, str]:
        text = str(key)
        return (text.lower(), text)

    return [str(key) for key in sorted(mapping.keys(), key=sort_key)]
