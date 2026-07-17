"""Rewriting of GitHub Actions expression references inside string values."""

import re
from collections.abc import Callable
from typing import Any

from gh_formatter.core.tree import restyle_scalar


def replace_expression_references(
    text: str, prefixes: tuple[str, ...], old_name: str, new_name: str
) -> str:
    """Replaces ``<prefix>.<old_name>`` and ``<prefix>['<old_name>']``.

    The dotted form requires the old name to end at a word/dash boundary so
    that e.g. renaming ``my-input`` does not clobber ``my-input-extra``.
    """
    escaped_name = re.escape(old_name)
    for prefix in prefixes:
        escaped_prefix = re.escape(prefix)
        text = re.sub(
            rf"\b{escaped_prefix}\.{escaped_name}(?![\w-])",
            f"{prefix}.{new_name}",
            text,
        )
        text = re.sub(
            rf"\b{escaped_prefix}\[(['\"]){escaped_name}\1\]",
            rf"{prefix}[\g<1>{new_name}\g<1>]",
            text,
        )
    return text


def transform_strings_in_place(
    data: Any, transform: Callable[[str], str]
) -> None:
    """Applies a transform to every string value nested in dicts/lists.

    The original scalar style (literal block, quoting, ...) is preserved
    when a value changes.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = _transformed(value, transform)
            else:
                transform_strings_in_place(value, transform)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, str):
                data[index] = _transformed(item, transform)
            else:
                transform_strings_in_place(item, transform)


def _transformed(value: str, transform: Callable[[str], str]) -> str:
    result = transform(value)
    if result == value:
        return value
    return restyle_scalar(value, result)
