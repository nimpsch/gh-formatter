"""Text post-processors that run on the serialized YAML output.

Post-processors handle purely presentational concerns (like blank lines)
that cannot be expressed in the parsed YAML tree. They run after the
tree rules and the YAML dump, and operate on the canonical text the
dumper produced.
"""

import re
from abc import ABC, abstractmethod

from gh_formatter.config import Config
from gh_formatter.core.context import Context

# A value position opening a block scalar, e.g. `run: |`, `run: |-`,
# `description: >-2`, or a sequence item `- |`. Matched against the
# stripped line of canonical dumper output.
_BLOCK_SCALAR_OPENER = re.compile(r"(?:^|\s)[|>][+-]?[0-9]*(?:\s+#.*)?$")


class BasePostProcessor(ABC):
    """Base class for text-level formatting passes."""

    @property
    @abstractmethod
    def id(self) -> str:
        """A unique string identifier for the post-processor."""

    @property
    @abstractmethod
    def description(self) -> str:
        """A short description of what the post-processor does."""

    @abstractmethod
    def should_run(self, context: Context) -> bool:
        """Determine if this pass applies to the current context."""

    @abstractmethod
    def apply(self, text: str, context: Context) -> str:
        """Transform the serialized YAML text."""


class BlankLinesProcessor(BasePostProcessor):
    """Normalizes blank lines between steps, jobs, and top-level sections.

    Blank lines carry no meaning except as separators between siblings, so
    each tracked scope is normalized to exactly one blank between its
    siblings and none stray inside a sibling's body (whether hand-written
    or left behind by key reordering). Three scopes are tracked, each gated
    by its own config flag: steps, jobs, and top-level sections. A scope
    whose flag is disabled is left exactly as written. Blank lines inside a
    `run:` script (a block scalar) are content and are always preserved.
    """

    @property
    def id(self) -> str:
        return "blank-lines"

    @property
    def description(self) -> str:
        return "Normalize blank lines between steps, jobs, and sections"

    def should_run(self, context: Context) -> bool:
        config = context.config
        return (
            config.blank_line_between_steps
            or config.blank_line_between_jobs
            or config.blank_line_between_sections
        )

    def apply(self, text: str, context: Context) -> str:
        scanner = _BlankLineScanner(context.config)
        return "\n".join(scanner.run(text.split("\n")))


class _BlankLineScanner:
    """Tracks the steps/jobs/block-scalar scope line-by-line.

    The serialized YAML is processed as a flat list of lines; this scanner
    remembers where it is in the document so blank lines are inserted only
    between real steps and jobs -- never inside a `run: |` script, where a
    line like `- item` is just text.
    """

    def __init__(self, config: Config):
        self.config = config
        self.result: list[str] = []
        self.in_block_scalar = False
        self.block_scalar_indent = 0
        self._pending_blanks: list[str] = []
        self.saw_root_key = False
        self.in_steps = False
        self.step_dash_col = 0
        self.in_jobs = False
        self.job_indent = config.indent

    def run(self, lines: list[str]) -> list[str]:
        # A trailing "" from splitting a newline-terminated text is the
        # final-newline artifact, not a blank line: never strip it.
        body, tail = (
            (lines[:-1], [""]) if lines and lines[-1] == "" else (lines, [])
        )
        for line in body:
            self._feed(line)
        return self.result + tail

    def _feed(self, line: str) -> None:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if self._consume_block_scalar(line, stripped, indent):
            return

        is_content = bool(stripped) and not stripped.startswith("#")
        if is_content:
            self._update_scopes(stripped, indent)

        # Blank lines are only ever separators (outside scripts), and the
        # canonical ones are re-inserted below: drop them scope-wise.
        if not stripped and self._should_drop_blank():
            return

        self._maybe_separate(stripped, indent, is_content)
        if is_content and indent == 0 and ":" in stripped:
            if self.saw_root_key and self.config.blank_line_between_sections:
                _insert_blank_before(self.result, indent)
            self.saw_root_key = True
        self.result.append(line)

        if is_content and _BLOCK_SCALAR_OPENER.search(stripped):
            self.in_block_scalar = True
            self.block_scalar_indent = indent

    def _consume_block_scalar(
        self, line: str, stripped: str, indent: int
    ) -> bool:
        """Swallows lines inside a block scalar; returns True when it does.

        Blank lines are held back until the next line shows whether they
        are script content (more block lines follow: keep them) or the
        separator to the next key/step (the block ended: normalize them,
        the canonical separator is re-inserted by the normal pass).
        """
        if not self.in_block_scalar:
            return False
        if not stripped:
            self._pending_blanks.append(line)
            return True
        pending, self._pending_blanks = self._pending_blanks, []
        if indent <= self.block_scalar_indent:
            self.in_block_scalar = False  # dedented out: process normally
            # These trailing blanks separate the block from the next
            # key/step; treat them exactly like any other separator so the
            # scope's flag decides whether they collapse to the canonical
            # single blank or stay untouched.
            if not self._should_drop_blank():
                self.result.extend(pending)
            return False
        # Still inside the block: the blanks were script content.
        self.result.extend(pending)
        self.result.append(line)
        return True

    def _should_drop_blank(self) -> bool:
        """Whether a blank in the current scope is a normalizable separator.

        Each scope is governed by its own flag, so disabling one scope's
        normalization (e.g. ``blank_line_between_steps``) leaves that
        scope's blanks untouched instead of being swept up by another
        scope's flag. The dropped blank's canonical replacement, if any, is
        re-inserted at the next sibling boundary.
        """
        if self.in_steps:
            return self.config.blank_line_between_steps
        if self.in_jobs:
            return self.config.blank_line_between_jobs
        return self.config.blank_line_between_sections

    def _update_scopes(self, stripped: str, indent: int) -> None:
        if self.in_steps and self._is_leaving_steps(stripped, indent):
            self.in_steps = False
        if indent == 0:
            self.in_jobs = stripped == "jobs:"

    def _is_leaving_steps(self, stripped: str, indent: int) -> bool:
        if indent < self.step_dash_col:
            return True
        return (
            indent == self.step_dash_col
            and not _is_sequence_item(stripped)
            and stripped != "steps:"
        )

    def _maybe_separate(
        self, stripped: str, indent: int, is_content: bool
    ) -> None:
        if stripped == "steps:":
            self.in_steps = True
            # ruamel places sequence dashes at key indent + offset
            self.step_dash_col = indent + self.config.sequence_offset
        elif self._starts_new_step(stripped, indent):
            _insert_blank_before(self.result, indent, opener="steps:")
        elif self._starts_new_job(stripped, indent, is_content):
            _insert_blank_before(self.result, indent, opener="jobs:")

    def _starts_new_step(self, stripped: str, indent: int) -> bool:
        return (
            self.config.blank_line_between_steps
            and self.in_steps
            and indent == self.step_dash_col
            and _is_sequence_item(stripped)
        )

    def _starts_new_job(
        self, stripped: str, indent: int, is_content: bool
    ) -> bool:
        return (
            self.config.blank_line_between_jobs
            and self.in_jobs
            and is_content
            and indent == self.job_indent
            and not _is_sequence_item(stripped)
            and ":" in stripped
        )


def _is_sequence_item(stripped: str) -> bool:
    return stripped == "-" or stripped.startswith("- ")


def _insert_blank_before(
    result: list[str], indent: int, opener: str | None = None
) -> None:
    """Inserts one blank line before the element about to be appended.

    A comment line sitting at the same column as the element (a lead-in
    written above it, e.g. ``# explains the next step``) belongs to it, so
    the blank goes above that comment too. A comment indented deeper --
    the previous sibling's own trailing content, e.g. a note inside its
    ``with:`` block -- is not a lead-in and must not be walked past, or its
    separating blank would end up on the wrong side of it and the comment
    would visually attach to this element instead of the previous one.
    Nothing is inserted at the start of the document, when a blank is
    already present, after the ``---`` document marker, or after the
    container opener (``steps:``/``jobs:``, passed as ``opener``) -- in
    those cases there is no prior sibling to separate from.
    """
    insert_at = len(result)
    while insert_at > 0:
        candidate = result[insert_at - 1]
        stripped_candidate = candidate.lstrip()
        if not stripped_candidate.startswith("#"):
            break
        candidate_indent = len(candidate) - len(stripped_candidate)
        if candidate_indent != indent:
            break
        insert_at -= 1
    if insert_at == 0:
        return
    previous = result[insert_at - 1].strip()
    if previous == "" or previous == "---":
        return
    if opener is not None and previous.startswith(opener):
        return
    result.insert(insert_at, "")
