"""Rule: normalize already-quoted scalars to a consistent quote style."""

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import (
    DoubleQuotedScalarString,
    SingleQuotedScalarString,
)

from gh_formatter.context import Context
from gh_formatter.rules.base import BaseRule
from gh_formatter.utils import iter_tree_slots

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
        for container, key, value in iter_tree_slots(data, context):
            if isinstance(value, _QUOTED_TYPES) and not isinstance(
                value, target
            ):
                container[key] = target(str(value))
