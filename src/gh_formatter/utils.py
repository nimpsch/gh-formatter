"""YAML round-trip helpers built on ruamel.yaml.

This module is the only place that touches ruamel.yaml internals
(comment attachments, line/column info, scalar style classes), so the
rest of the codebase stays insulated from that API.
"""

from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def create_yaml_instance(
    indent: int = 2, sequence_indent: int = 2, sequence_offset: int = 0
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
    sequence_indent: int = 2,
    sequence_offset: int = 0,
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


def reorder_commented_map(
    data: CommentedMap, desired_order: list[str]
) -> CommentedMap:
    """Reorders a CommentedMap in-place while keeping comments associated."""
    if not isinstance(data, CommentedMap):
        return data

    keys = list(data.keys())

    # Skip the rebuild entirely when the order is already correct; the
    # comment extraction below is lossy in edge cases, so a no-op pass
    # must not touch the map at all.
    new_order = [k for k in desired_order if k in keys]
    for k in keys:
        if k not in new_order:
            new_order.append(k)
    if new_order == keys:
        return data

    lc_data = getattr(data.lc, "data", None) or {}

    pre_comments: dict[Any, list[Any]] = {k: [] for k in keys}
    inline_comments: dict[Any, Any] = {k: None for k in keys}
    end_comments = []

    top_comment = data.ca.comment

    for idx, k in enumerate(keys):
        k_line = lc_data.get(k, [0])[0] if k in lc_data else 0
        ca_item = data.ca.items.get(k)
        if not ca_item:
            continue

        # Pre-key comments at index 1
        if ca_item[1]:
            for token in ca_item[1]:
                pre_comments[k].append(token)

        # Comments at index 2 (post-value or pre-next-key)
        if ca_item[2]:
            token = ca_item[2]
            token_line = getattr(token, "line", -1)
            if token_line == k_line:
                inline_comments[k] = token
            else:
                if idx + 1 < len(keys):
                    next_key = keys[idx + 1]
                    pre_comments[next_key].append(token)
                else:
                    end_comments.append(token)

        # Inline comments at index 3
        if ca_item[3]:
            tokens = (
                ca_item[3] if isinstance(ca_item[3], list) else [ca_item[3]]
            )
            for token in tokens:
                inline_comments[k] = token

    # Extract values
    values = {k: data[k] for k in keys}

    # Clear map and comments
    data.clear()
    data.ca.items.clear()
    data.ca.comment = top_comment

    # Re-insert items and apply comments
    for k in new_order:
        data[k] = values[k]

        # Apply pre-comments
        if pre_comments[k]:
            comment_str = "\n".join(
                _comment_text(token) for token in pre_comments[k]
            )
            data.yaml_set_comment_before_after_key(k, before=comment_str)

        # Apply inline comment
        if inline_comments[k]:
            val = inline_comments[k].value.strip()
            if not val.startswith("#"):
                val = f"# {val}"
            data.yaml_add_eol_comment(val, k)

    # Re-attach trailing comments to the new last key by reusing the raw
    # comment tokens (text-based reattachment does not survive dumping).
    if end_comments and keys:
        last_key = new_order[-1]
        item = data.ca.items.setdefault(last_key, [None, None, None, None])
        if item[2] is None:
            item[2] = end_comments[0]

    return data


def _comment_text(token: Any) -> str:
    """Extracts the text of a comment token without the leading '#'."""
    val = str(token.value).strip()
    if val.startswith("#"):
        return val[1:].strip()
    return val
