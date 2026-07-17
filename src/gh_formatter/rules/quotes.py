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
    values keep their plain style. A value containing the configured quote
    character is wrapped in the opposite one instead, so nested quotes read
    naturally ('say "hi"') rather than being escaped. ruamel falls back to
    double quoting automatically when a value cannot be represented in
    single quotes (for example because it contains a newline), so the
    conversion is always safe.
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
            if not isinstance(value, _QUOTED_TYPES):
                continue
            desired = _preferred_class(str(value), target)
            if not isinstance(value, desired):
                container[key] = desired(str(value))


def _preferred_class(value: str, target: type) -> type:
    """The configured quote class, or the opposite one to avoid escaping.

    When the value contains the configured quote character but not the
    other, the other is used; when it contains both, escaping is
    unavoidable and the configured style wins.
    """
    if target is DoubleQuotedScalarString:
        if '"' in value and "'" not in value:
            return SingleQuotedScalarString
    elif "'" in value and '"' not in value:
        return DoubleQuotedScalarString
    return target
