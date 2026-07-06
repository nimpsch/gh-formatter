"""Comment-preserving surgery on ruamel CommentedMaps.

ruamel attaches a key's end-of-line comment *and* the comment block that
precedes the following key to a single token on that key, which a naive
reorder would scramble. This module isolates that token bookkeeping so the
rules can reorder keys without losing or misplacing comments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken


@dataclass
class _CommentLayout:
    """A CommentedMap's comments, decoupled from key order."""

    # key -> (end-of-line comment text, its column)
    eol: dict[Any, tuple[str, int]] = field(default_factory=dict)
    # key -> comment lines (with indentation) that appear before it
    pre: dict[Any, list[str]] = field(default_factory=dict)
    # comment lines after the last key
    trailing: list[str] = field(default_factory=list)
    # positions (in the original order) followed by a blank separator line;
    # blank lines keep their position while the entries move around them.
    blank_after: set[int] = field(default_factory=set)


def reorder_commented_map(
    data: CommentedMap, desired_order: list[str]
) -> CommentedMap:
    """Reorders a CommentedMap in-place while keeping comments associated."""
    if not isinstance(data, CommentedMap):
        return data

    keys = list(data.keys())
    new_order = _resolve_order(keys, desired_order)
    # A no-op pass leaves ruamel's original comment attachments untouched.
    if new_order == keys:
        return data

    layout = _decompose_comments(data, keys)
    values = {k: data[k] for k in keys}
    top_comment = data.ca.comment

    data.clear()
    data.ca.items.clear()
    data.ca.comment = top_comment
    for key in new_order:
        data[key] = values[key]

    _rebuild_comments(data, new_order, layout)
    return data


def _resolve_order(keys: list[Any], desired_order: list[str]) -> list[Any]:
    """Keys in `desired_order` first, then the rest in their original order."""
    ordered = [k for k in desired_order if k in keys]
    ordered += [k for k in keys if k not in ordered]
    return ordered


def _decompose_comments(data: CommentedMap, keys: list[Any]) -> _CommentLayout:
    """Splits each key's comment token into per-key eol / pre / trailing."""
    layout = _CommentLayout(pre={k: [] for k in keys})

    # Index 1 holds comments attached directly before a key.
    for key in keys:
        item = data.ca.items.get(key)
        if item and item[1]:
            for token in item[1]:
                layout.pre[key] = _comment_lines(token.value) + layout.pre[key]

    # Index 2 holds the key's own eol comment plus the next key's pre-block.
    for idx, key in enumerate(keys):
        item = data.ca.items.get(key)
        if not item or item[2] is None:
            continue
        if item[2].value.endswith("\n\n"):
            layout.blank_after.add(idx)
        eol_text, following = _split_post_comment(item[2].value)
        if eol_text is not None:
            column = getattr(item[2].start_mark, "column", 0)
            layout.eol[key] = (eol_text, column)
        if not following:
            continue
        if idx + 1 < len(keys):
            nxt = keys[idx + 1]
            layout.pre[nxt] = following + layout.pre[nxt]
        else:
            layout.trailing.extend(following)

    return layout


def _rebuild_comments(
    data: CommentedMap, new_order: list[Any], layout: _CommentLayout
) -> None:
    """Re-attaches comment tokens so each rides the line it documents."""
    for idx, key in enumerate(new_order):
        next_key = new_order[idx + 1] if idx + 1 < len(new_order) else None
        following = (
            layout.pre[next_key] if next_key is not None else layout.trailing
        )
        token = _build_post_token(layout.eol.get(key), following)
        if idx in layout.blank_after:
            token = _with_blank_tail(token)
        if token is not None:
            data.ca.items[key] = [None, None, token, None]

    # Comments before the first key have no preceding key to ride on.
    first = new_order[0]
    if layout.pre[first]:
        value = "".join(line + "\n" for line in layout.pre[first])
        item = data.ca.items.setdefault(first, [None, None, None, None])
        item[1] = [CommentToken(value, CommentMark(0))]


def _with_blank_tail(token: CommentToken | None) -> CommentToken:
    """Returns a token that ends with a blank separator line."""
    if token is None:
        return CommentToken("\n\n", CommentMark(0))
    if token.value.endswith("\n\n"):
        return token
    return CommentToken(token.value + "\n", token.start_mark)


def _build_post_token(
    eol: tuple[str, int] | None, following: list[str]
) -> CommentToken | None:
    """Builds an index-2 token: a key's eol comment plus the next key's pre."""
    value = ""
    column = 0
    if eol is not None:
        text, column = eol
        value = text + "\n"
    elif following:
        value = "\n"  # terminate the key's value line before the comment block
    for line in following:
        value += line + "\n"
    if not value:
        return None
    return CommentToken(value, CommentMark(column))


def hoist_dedented_comments(mapping: CommentedMap) -> None:
    """Prepares a mapping's comments so its entries can be reordered safely.

    ruamel attaches a comment written between two map-valued entries to the
    *previous* entry's deepest inner key, and a comment above the first
    entry to the mapping itself -- both invisible to a key reorder, so the
    comment would stay behind or drift. This reattaches such comments as
    proper pre-comments of the entry they document (identified by their
    indentation column), and drops blank separator lines buried inside
    entries. Call it before reordering a mapping.
    """
    keys = list(mapping.keys())
    if not keys:
        return
    _lift_block_lead_comment(mapping, keys[0])

    lc_data = getattr(mapping.lc, "data", None) or {}
    for index, key in enumerate(keys):
        value = mapping[key]
        if not isinstance(value, CommentedMap):
            continue  # scalar/seq entries already attach at the outer level
        next_key = keys[index + 1] if index + 1 < len(keys) else None
        info = lc_data.get(next_key) if next_key is not None else None
        outer_column = info[1] if info is not None else None
        hoisted = _normalize_entry_tail(value, outer_column)
        if hoisted and next_key is not None:
            _prepend_pre_comment(mapping, next_key, hoisted)


def _lift_block_lead_comment(mapping: CommentedMap, first_key: str) -> None:
    """Moves a comment above the first entry onto that entry itself."""
    comment = mapping.ca.comment
    if not comment or not comment[1]:
        return
    lines: list[str] = []
    for token in comment[1]:
        # A token's first line does not embed its indentation (it lives in
        # the start mark); re-add it so the line renders at its column.
        column = getattr(token.start_mark, "column", 0)
        for index, line in enumerate(_comment_lines(token.value)):
            if index == 0 and not line.startswith(" "):
                line = " " * column + line
            lines.append(line)
    # The token list is shared with the parent's attachment slot, so
    # clearing it in place removes the comment from both render paths.
    comment[1].clear()
    if lines:
        _prepend_pre_comment(mapping, first_key, lines)


def _normalize_entry_tail(
    value: CommentedMap, outer_column: int | None
) -> list[str]:
    """Cleans the trailing comment token of a map-valued entry.

    Removes and returns comment lines that belong at the outer key level
    (`outer_column`; None when unknown, e.g. for the last entry) and strips
    blank separator lines, which would otherwise travel with the entry.
    """
    # Descend to the deepest mapping along the last keys; that is where
    # ruamel hangs a comment that trails the whole entry.
    holder = value
    while True:
        last = next(reversed(holder), None)
        if last is None:
            return []
        inner = holder[last]
        if isinstance(inner, CommentedMap) and len(inner):
            holder = inner
            continue
        break

    item = holder.ca.items.get(last)
    if not item or item[2] is None:
        return []
    token = item[2]

    lines = token.value.split("\n")
    eol = lines[0] if lines and lines[0].strip() else None
    # A newline-terminated value yields a final "" artifact, not a blank.
    body = lines[1:-1] if lines and lines[-1] == "" else lines[1:]

    kept: list[str] = []
    hoisted: list[str] = []
    for line in body:
        if not line.strip().startswith("#"):
            continue  # drop blank separator lines buried inside the entry
        indent = len(line) - len(line.lstrip(" "))
        if outer_column is not None and indent <= outer_column:
            hoisted.append(line.rstrip())
        else:
            kept.append(line.rstrip())

    saw_blank = any(not line.strip() for line in body)
    if not hoisted and not saw_blank:
        return hoisted
    item[2] = _build_post_token(
        (eol, token.start_mark.column) if eol else None, kept
    )
    return hoisted


def _prepend_pre_comment(
    mapping: CommentedMap, key: str, lines: list[str]
) -> None:
    """Adds comment lines as a pre-comment (item slot 1) of `key`."""
    value = "".join(line + "\n" for line in lines)
    item = mapping.ca.items.setdefault(key, [None, None, None, None])
    token = CommentToken(value, CommentMark(0))
    item[1] = [*item[1], token] if item[1] else [token]


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
        block = _take_first_key_lead_comment(step)
        if block is None:
            continue
        if index == 0:
            _prepend_before_first_step(container, block)
        else:
            _append_trailing_comment(steps[index - 1], block)


def _take_first_key_lead_comment(step: Any) -> str | None:
    """Removes and returns a step's first-key pre-comment block, if any."""
    if not isinstance(step, CommentedMap):
        return None
    first = next(iter(step), None)
    if first is None:
        return None
    item = step.ca.items.get(first)
    if not item or not item[1]:
        return None
    lines: list[str] = []
    for token in item[1]:
        lines.extend(_comment_lines(token.value))
    if not lines:
        return None
    item[1] = None
    return "".join(line + "\n" for line in lines)


def _prepend_before_first_step(container: CommentedMap, block: str) -> None:
    """Attaches a comment before the first step (on the `steps` key)."""
    slot = container.ca.items.setdefault("steps", [None, None, None, None])
    token = CommentToken(block, CommentMark(0))
    slot[3] = [*slot[3], token] if slot[3] else [token]


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


def _comment_lines(raw: str) -> list[str]:
    """Returns the `#` lines in `raw`, keeping indentation, dropping blanks."""
    return [
        line.rstrip()
        for line in raw.split("\n")
        if line.strip().startswith("#")
    ]


def _split_post_comment(raw: str) -> tuple[str | None, list[str]]:
    """Splits a key's index-2 token into (end-of-line, before-next-key).

    ruamel stores the key's own end-of-line comment (present when the value
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
