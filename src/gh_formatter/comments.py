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
        if token is not None:
            data.ca.items[key] = [None, None, token, None]

    # Comments before the first key have no preceding key to ride on.
    first = new_order[0]
    if layout.pre[first]:
        value = "".join(line + "\n" for line in layout.pre[first])
        item = data.ca.items.setdefault(first, [None, None, None, None])
        item[1] = [CommentToken(value, CommentMark(0))]


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
