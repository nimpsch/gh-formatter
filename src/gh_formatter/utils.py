"""YAML round-trip helpers built on ruamel.yaml.

This module owns the ruamel parser/dumper configuration, small typed
accessors over the parsed tree, and the context-aware tree traversal the
rules share. Comment-token surgery lives in ``comments.py``.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gh_formatter.context import Context


def create_yaml_instance(
    indent: int = 2, sequence_indent: int = 4, sequence_offset: int = 2
) -> YAML:
    """Creates a configured YAML parser/dumper instance."""
    yaml = YAML()
    yaml.preserve_quotes = True
    # In ruamel.yaml, mapping indent controls top-level mapping,
    # sequence controls list item indentation, offset is the indent of dash '-'
    yaml.indent(
        mapping=indent, sequence=sequence_indent, offset=sequence_offset
    )
    yaml.width = (
        4096  # Set large width to avoid automatic wrapping of long lines
    )
    return yaml


def load_yaml(content: str) -> Any:
    """Parses a YAML string into a CommentedMap or CommentedSeq."""
    if not content.strip():
        return CommentedMap()
    return create_yaml_instance().load(content)


def dump_yaml(
    data: Any,
    indent: int = 2,
    sequence_indent: int = 4,
    sequence_offset: int = 2,
) -> str:
    """Serializes a YAML structure to string, maintaining formatting."""
    yaml = create_yaml_instance(indent, sequence_indent, sequence_offset)
    stream = StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()


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
