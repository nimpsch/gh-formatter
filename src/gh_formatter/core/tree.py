"""Typed helpers for navigating and mutating the parsed YAML tree."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gh_formatter.core.context import Context


def get_map(parent: Any, key: str) -> CommentedMap | None:
    """Returns parent[key] if it is a CommentedMap, else None."""
    if not isinstance(parent, dict):
        return None
    value = parent.get(key)
    return value if isinstance(value, CommentedMap) else None


def get_seq(parent: Any, key: str) -> CommentedSeq | None:
    """Returns parent[key] if it is a CommentedSeq, else None."""
    if not isinstance(parent, dict):
        return None
    value = parent.get(key)
    return value if isinstance(value, CommentedSeq) else None


def key_location(mapping: Any, key: Any) -> tuple[int, int] | None:
    """The 1-based (line, column) a mapping's key was written at, if known."""
    lc_data = getattr(getattr(mapping, "lc", None), "data", None)
    info = lc_data.get(key) if lc_data else None
    if info is None:
        return None
    return info[0] + 1, info[1] + 1


def node_location(node: Any) -> tuple[int, int] | None:
    """The 1-based (line, column) a mapping/sequence itself starts at."""
    lc = getattr(node, "lc", None)
    if lc is None or lc.line is None:
        return None
    return lc.line + 1, lc.col + 1


def restyle_scalar(original: str, new: str) -> str:
    """Wraps `new` in the same scalar style class as `original`.

    ruamel represents quoted/literal/folded scalars with str subclasses;
    assigning a plain str would lose the original style on dump.
    """
    cls = type(original)
    if cls is str:
        return new
    try:
        return cls(new)
    except TypeError:
        return new


def rename_commented_map_keys(
    data: CommentedMap, renames: dict[str, str]
) -> None:
    """Renames keys in-place, preserving order and attached comments."""
    if not renames:
        return

    keys = list(data.keys())
    values = {k: data[k] for k in keys}
    ca_items = dict(data.ca.items)
    top_comment = data.ca.comment

    data.clear()
    data.ca.items.clear()
    data.ca.comment = top_comment

    for key in keys:
        new_key = renames.get(key, key)
        data[new_key] = values[key]
        if key in ca_items:
            data.ca.items[new_key] = ca_items[key]


def iter_tree_slots(
    node: Any, context: Context
) -> Iterator[tuple[Any, Any, Any]]:
    """Yields ``(container, key_or_index, value)`` for every writable slot.

    Walks mappings and sequences depth-first, skipping directive-frozen keys
    and ignored subtrees. A rule can mutate ``container[key]`` in place while
    iterating, since each level is snapshotted before traversal.
    """
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if context.is_frozen(node, key) or context.is_ignored(value):
                continue
            yield node, key, value
            yield from iter_tree_slots(value, context)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if context.is_ignored(value):
                continue
            yield node, index, value
            yield from iter_tree_slots(value, context)
