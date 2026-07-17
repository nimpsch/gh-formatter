"""Inline directives that let developers disable formatting.

Supported (yamllint-style) directives, written as YAML comments:

* ``# gh-formatter:disable-file`` -- skip the whole file.
* ``# gh-formatter:disable`` / ``# gh-formatter:enable`` -- skip every line
  in the region between the two directives.
* ``# gh-formatter:disable-line`` -- skip the line the directive sits on
  (when trailing a key) or the next content line (when on its own line).

"Skip" means the affected YAML nodes are exempt from the tree rules
(renaming, reordering, casing, list style, quotes, whitespace). The file is
still parsed and re-dumped, so the base indentation always applies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ruamel.yaml.comments import CommentedMap, CommentedSeq

if TYPE_CHECKING:
    from gh_formatter.core.context import Context

# Matches `# gh-formatter:disable`, `# gh-formatter: enable`,
# `# gh-formatter disable-line`, etc. Longer keywords first so `disable`
# does not shadow `disable-file`/`disable-line`.
_DIRECTIVE_RE = re.compile(
    r"#\s*gh-formatter[:\s]\s*(disable-file|disable-line|disable|enable)\b"
)


def scan_disabled(content: str) -> tuple[bool, set[int]]:
    """Returns (disable_whole_file, set of 1-based disabled line numbers)."""
    disable_file = False
    disabled: set[int] = set()
    region = False

    lines = content.split("\n")
    for number, line in enumerate(lines, start=1):
        match = _match_directive(line)
        directive = match.group(1) if match else None

        if directive == "enable":
            region = False
            continue

        if region:
            disabled.add(number)

        if directive == "disable-file":
            disable_file = True
        elif directive == "disable":
            region = True
            disabled.add(number)
        elif directive == "disable-line":
            assert match is not None
            if line[: match.start()].strip():
                disabled.add(number)  # trailing directive: this line
            else:
                target = _next_content_line(lines, number)
                if target is not None:
                    disabled.add(target)

    return disable_file, disabled


def _match_directive(line: str) -> re.Match[str] | None:
    """Matches a directive comment, ignoring directive-shaped strings.

    A real YAML comment's ``#`` sits at the start of the line or after
    whitespace. A match preceded by any other character (for example the
    quote in ``echo "# gh-formatter:disable"`` inside a run block) is
    script content, not a directive. A directive on its own line inside a
    script (e.g. a bash comment) is still indistinguishable by text scan
    and remains a known limitation.
    """
    match = _DIRECTIVE_RE.search(line)
    if match is None:
        return None
    if match.start() > 0 and line[match.start() - 1] not in " \t":
        return None
    return match


def _next_content_line(lines: list[str], after: int) -> int | None:
    """First line number after `after` (1-based) that carries real content."""
    for index in range(after, len(lines)):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            return index + 1
    return None


def mark_disabled_nodes(
    data: CommentedMap, disabled: set[int], context: Context
) -> None:
    """Freezes keys/items whose source line is disabled, on the context."""
    if disabled:
        _walk(data, disabled, context)


def _walk(node: object, disabled: set[int], context: Context) -> None:
    if isinstance(node, CommentedMap):
        lc_data = getattr(node.lc, "data", None) or {}
        for key in list(node.keys()):
            value = node[key]
            info = lc_data.get(key)
            line = info[0] + 1 if info else None
            if line is not None and line in disabled:
                # Freeze the key (covers rename/reorder/casing and scalar
                # values) and ignore its subtree wholesale.
                context.freeze_key(node, key)
                if isinstance(value, (CommentedMap, CommentedSeq)):
                    context.ignore_node(value)
                continue
            _walk(value, disabled, context)
    elif isinstance(node, CommentedSeq):
        lc_data = getattr(node.lc, "data", None) or {}
        for index, item in enumerate(node):
            info = lc_data.get(index)
            line = info[0] + 1 if info else None
            if line is not None and line in disabled:
                if isinstance(item, (CommentedMap, CommentedSeq)):
                    context.ignore_node(item)
                continue
            _walk(item, disabled, context)
