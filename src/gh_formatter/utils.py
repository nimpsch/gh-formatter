"""YAML round-trip helpers built on ruamel.yaml.

This module is the only place that touches ruamel.yaml internals
(comment attachments, line/column info, scalar style classes), so the
rest of the codebase stays insulated from that API.
"""

from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken


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


def reorder_commented_map(
    data: CommentedMap, desired_order: list[str]
) -> CommentedMap:
    """Reorders a CommentedMap in-place while keeping comments associated.

    ruamel attaches comments to keys in a way that does not survive a naive
    reorder: a key's end-of-line comment *and* the comment block that
    precedes the following key are both stored in a single token on that
    key. This function decomposes those tokens into per-key end-of-line
    comments and per-key "before" comment blocks, reorders, and rebuilds the
    tokens so every comment travels with the line it documents.
    """
    if not isinstance(data, CommentedMap):
        return data

    keys = list(data.keys())

    # Skip the rebuild entirely when the order is already correct so a no-op
    # pass leaves ruamel's original comment attachments perfectly intact.
    new_order = [k for k in desired_order if k in keys]
    for k in keys:
        if k not in new_order:
            new_order.append(k)
    if new_order == keys:
        return data

    # eol[k]: (text, column) of k's end-of-line comment, or None.
    # pre[k]: comment lines (with indentation) that appear before k.
    eol: dict[Any, tuple[str, int] | None] = {k: None for k in keys}
    pre: dict[Any, list[str]] = {k: [] for k in keys}
    trailing: list[str] = []

    for k in keys:
        item = data.ca.items.get(k)
        if item and item[1]:
            for token in item[1]:
                pre[k] = _comment_lines(token.value) + pre[k]

    for idx, k in enumerate(keys):
        item = data.ca.items.get(k)
        if not item or item[2] is None:
            continue
        token = item[2]
        eol_text, following = _split_post_comment(token.value)
        if eol_text is not None:
            eol[k] = (eol_text, getattr(token.start_mark, "column", 0))
        if following:
            if idx + 1 < len(keys):
                pre[keys[idx + 1]] = following + pre[keys[idx + 1]]
            else:
                trailing.extend(following)

    values = {k: data[k] for k in keys}
    top_comment = data.ca.comment

    data.clear()
    data.ca.items.clear()
    data.ca.comment = top_comment

    for k in new_order:
        data[k] = values[k]

    for idx, k in enumerate(new_order):
        next_key = new_order[idx + 1] if idx + 1 < len(new_order) else None
        following = pre[next_key] if next_key is not None else trailing

        value = ""
        column = 0
        if eol[k] is not None:
            text, column = eol[k]  # type: ignore[misc]
            value = text + "\n"
        elif following:
            # Terminate the key's value line before the comment block.
            value = "\n"
        for line in following:
            value += line + "\n"

        if value:
            data.ca.items[k] = [
                None,
                None,
                CommentToken(value, CommentMark(column)),
                None,
            ]

    # Comments before the very first key have no preceding key to ride on,
    # so attach them as the key's own "before" comment block. The comment
    # text already carries its indentation, so the mark column stays 0 to
    # avoid doubling it.
    first = new_order[0]
    if pre[first]:
        value = "".join(line + "\n" for line in pre[first])
        item = data.ca.items.setdefault(first, [None, None, None, None])
        item[1] = [CommentToken(value, CommentMark(0))]

    return data


def _comment_lines(raw: str) -> list[str]:
    """Returns the `#` lines in `raw`, keeping indentation, dropping blanks."""
    return [
        line.rstrip()
        for line in raw.split("\n")
        if line.strip().startswith("#")
    ]


def promote_step_lead_comments(container: CommentedMap) -> None:
    """Lifts comments stuck before a step's first key to above the step.

    After key reordering, a comment a developer wrote between two step keys
    can end up attached to the key that now sorts first, which ruamel cannot
    render on the (otherwise empty) dash line. This moves such comments to
    sit above the step's ``-`` -- the same place ruamel itself relocates
    them on reparse -- so a single formatting pass is idempotent.
    """
    if not isinstance(container, CommentedMap):
        return
    steps = container.get("steps")
    if not isinstance(steps, CommentedSeq):
        return

    for index, step in enumerate(steps):
        if not isinstance(step, CommentedMap):
            continue
        first = next(iter(step), None)
        if first is None:
            continue
        item = step.ca.items.get(first)
        if not item or not item[1]:
            continue
        lines: list[str] = []
        for token in item[1]:
            lines.extend(_comment_lines(token.value))
        if not lines:
            continue

        item[1] = None
        block = "".join(line + "\n" for line in lines)
        if index == 0:
            # A comment before the first step lives on the container's
            # `steps` key (index 3 of its comment slot).
            slot = container.ca.items.setdefault(
                "steps", [None, None, None, None]
            )
            token = CommentToken(block, CommentMark(0))
            slot[3] = [*slot[3], token] if slot[3] else [token]
        else:
            _append_trailing_comment(steps[index - 1], block)


def _append_trailing_comment(prev_step: Any, block: str) -> None:
    """Appends a comment block after the previous step's last key."""
    if not isinstance(prev_step, CommentedMap):
        return
    last = next(reversed(prev_step), None)
    if last is None:
        return
    slot = prev_step.ca.items.setdefault(last, [None, None, None, None])
    current = slot[2]
    base = current.value if current is not None else ""
    if not base:
        base = "\n"  # terminate the previous value's line first
    elif not base.endswith("\n"):
        base += "\n"
    column = getattr(current.start_mark, "column", 0) if current else 0
    slot[2] = CommentToken(base + block, CommentMark(column))


def _split_post_comment(raw: str) -> tuple[str | None, list[str]]:
    """Splits a key's index-2 comment token into (end-of-line, before-next).

    ruamel stores the key's own end-of-line comment (when present, the value
    does not start with a newline) followed by the comment block that
    precedes the next key. Blank lines are dropped; the blank-line
    post-processor re-creates intentional spacing between steps and jobs.
    """
    lines = raw.split("\n")
    eol: str | None = None
    start = 0
    if lines and lines[0].strip().startswith("#"):
        eol = lines[0].strip()
        start = 1
    following = [
        line.rstrip() for line in lines[start:] if line.strip().startswith("#")
    ]
    return eol, following
