"""Rule: normalize already-quoted scalars to a consistent quote style."""

from typing import Any

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import (
    DoubleQuotedScalarString,
    SingleQuotedScalarString,
)

from gh_formatter.context import Context
from gh_formatter.rules.base import BaseRule

# Scalars ruamel tags with an explicit quote style. Plain and block
# (literal/folded) scalars are deliberately excluded so that `run: |`
# blocks and unquoted values are never quoted.
_QUOTED_TYPES = (SingleQuotedScalarString, DoubleQuotedScalarString)

_TARGET_CLASS = {
    "single": SingleQuotedScalarString,
    "double": DoubleQuotedScalarString,
}


class QuoteStyleRule(BaseRule):
    """Rewrites existing single/double quoted scalars to one style.

    Only scalars that are already quoted are touched; plain unquoted
    values keep their plain style. ruamel falls back to double quoting
    automatically when a value cannot be represented in single quotes
    (for example because it contains a newline), so the conversion is
    always safe.
    """

    @property
    def id(self) -> str:
        return "quote-style"

    @property
    def description(self) -> str:
        return "Normalize already-quoted scalars to a single quote style"

    def should_run(self, context: Context) -> bool:
        return context.config.quote_style != "preserve"

    def apply(self, data: CommentedMap, context: Context) -> None:
        target = _TARGET_CLASS[context.config.quote_style]
        _normalize(data, target, context)


def _normalize(data: Any, target: type, context: Context) -> None:
    """Rewraps quoted scalar values/items in `target`, recursing into both."""
    if isinstance(data, dict):
        for key, value in list(data.items()):
            if context.is_frozen(data, key) or context.is_ignored(value):
                continue
            if isinstance(value, _QUOTED_TYPES):
                if not isinstance(value, target):
                    data[key] = target(str(value))
            else:
                _normalize(value, target, context)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            if context.is_ignored(item):
                continue
            if isinstance(item, _QUOTED_TYPES):
                if not isinstance(item, target):
                    data[index] = target(str(item))
            else:
                _normalize(item, target, context)
