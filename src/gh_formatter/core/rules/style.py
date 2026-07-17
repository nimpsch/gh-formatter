"""Rule: clean whitespace in script blocks and normalize booleans."""

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString, PreservedScalarString

from gh_formatter.core.context import Context
from gh_formatter.core.rules.base import BaseRule
from gh_formatter.core.tree import iter_tree_slots

_BLOCK_SCALAR_TYPES = (LiteralScalarString, PreservedScalarString)

# Keys whose string values are normalized to real booleans
_BOOLEAN_KEYS = ("required", "continue-on-error")

_TRUE_VALUES = ("true", "yes", "on")
_FALSE_VALUES = ("false", "no", "off")


class StyleRule(BaseRule):
    @property
    def id(self) -> str:
        return "style"

    @property
    def description(self) -> str:
        return (
            "Trim whitespace and leading blanks in scripts, normalize booleans"
        )

    def should_run(self, context: Context) -> bool:
        return True

    def apply(self, data: CommentedMap, context: Context) -> None:
        for container, key, value in iter_tree_slots(data, context):
            if key in _BOOLEAN_KEYS and isinstance(value, str):
                normalized = _normalize_boolean(value)
                if normalized is not None:
                    container[key] = normalized
            elif isinstance(value, _BLOCK_SCALAR_TYPES):
                container[key] = _clean_block_scalar(value)


def _normalize_boolean(value: str) -> bool | None:
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return None


def _clean_block_scalar(value: str) -> str:
    """Trims trailing whitespace per line and drops leading blank lines.

    A leading blank line is meaningless in a script but forces the YAML
    emitter to write an explicit indentation indicator (``run: |2``), so it
    is removed. The original final newline is kept.
    """
    lines = value.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start == len(lines):
        return value  # nothing but blank lines: leave untouched
    trimmed = "\n".join(line.rstrip() for line in lines[start:])
    if value.endswith("\n"):
        trimmed += "\n"
    return type(value)(trimmed)
