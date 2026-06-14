"""Rule: trim trailing whitespace in scripts and normalize booleans."""

from typing import Any

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString, PreservedScalarString

from gh_formatter.context import Context
from gh_formatter.rules.base import BaseRule

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
            "Trim trailing whitespace in scripts and normalize simple booleans"
        )

    def should_run(self, context: Context) -> bool:
        return True

    def apply(self, data: CommentedMap, context: Context) -> None:
        _clean_recursively(data, context)


def _clean_recursively(data: Any, context: Context) -> None:
    if isinstance(data, dict):
        for key, value in list(data.items()):
            if context.is_frozen(data, key) or context.is_ignored(value):
                continue
            if key in _BOOLEAN_KEYS and isinstance(value, str):
                normalized = _normalize_boolean(value)
                if normalized is not None:
                    data[key] = normalized
            elif isinstance(value, _BLOCK_SCALAR_TYPES):
                data[key] = _trim_trailing_whitespace(value)
            else:
                _clean_recursively(value, context)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            if context.is_ignored(item):
                continue
            if isinstance(item, _BLOCK_SCALAR_TYPES):
                data[index] = _trim_trailing_whitespace(item)
            else:
                _clean_recursively(item, context)


def _normalize_boolean(value: str) -> bool | None:
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return None


def _trim_trailing_whitespace(value: str) -> str:
    """Trims line-trailing whitespace, keeping the original final newline."""
    trimmed = "\n".join(line.rstrip() for line in value.splitlines())
    if value.endswith("\n"):
        trimmed += "\n"
    return type(value)(trimmed)
