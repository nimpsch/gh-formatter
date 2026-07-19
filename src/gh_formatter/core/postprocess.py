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
    """Normalizes blank lines between steps and between jobs.

    Inside the jobs/steps scope, blank lines carry no meaning except as
    step/job separators, so stray ones (hand-written between a job's
    settings, or left behind by key reordering) are removed and the
    canonical separators are inserted. Blank lines outside jobs (root
    section separators, `on:` blocks) and inside scripts are untouched.
    """

    @property
    def id(self) -> str:
        return "blank-lines"

    @property
    def description(self) -> str:
        return "Normalize blank lines between steps and between jobs"

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
        if not stripped:
            if self.in_jobs or self.in_steps:
                if (
                    self.config.blank_line_between_steps
                    or self.config.blank_line_between_jobs
                ):
                    return
            elif self.config.blank_line_between_sections:
                return

        self._maybe_separate(stripped, indent, is_content)
        if is_content and indent == 0 and ":" in stripped:
            if self.saw_root_key and self.config.blank_line_between_sections:
                _separate_section(self.result)
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
        separator to the next key/step (the block ended: drop them, the
        canonical separator is re-inserted by the normal pass).
        """
        if not self.in_block_scalar:
            return False
        if not stripped:
            self._pending_blanks.append(line)
            return True
        if indent <= self.block_scalar_indent:
            self.in_block_scalar = False  # dedented out: process normally
            if not (self.in_jobs or self.in_steps):
                # Outside jobs these blanks are section separators: keep.
                self.result.extend(self._pending_blanks)
            self._pending_blanks.clear()
            return False
        self.result.extend(self._pending_blanks)
        self._pending_blanks.clear()
        self.result.append(line)
        return True

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
            _separate_item(self.result, "steps:")
        elif self._starts_new_job(stripped, indent, is_content):
            _separate_item(self.result, "jobs:")

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


def _separate_item(result: list[str], opener: str) -> None:
    """Inserts a blank line before the item the caller is about to append.

    Comment lines directly above the item belong to it, so the blank line
    goes above them. No blank line is inserted for the first item (right
    after the opening `steps:`/`jobs:` key) or when one is already there.
    """
    insert_at = len(result)
    while insert_at > 0 and result[insert_at - 1].lstrip().startswith("#"):
        insert_at -= 1
    if insert_at == 0:
        return
    previous = result[insert_at - 1].strip()
    if previous == "" or previous == opener or previous.startswith(opener):
        return
    result.insert(insert_at, "")


def _separate_section(result: list[str]) -> None:
    """Inserts one blank line before the top-level section being appended.

    Comment lines directly above the section belong to it, so the blank
    goes above them; nothing is inserted right after the document-start
    marker or when a blank is already present.
    """
    insert_at = len(result)
    while insert_at > 0 and result[insert_at - 1].lstrip().startswith("#"):
        insert_at -= 1
    if insert_at == 0:
        return
    previous = result[insert_at - 1].strip()
    if previous == "" or previous == "---":
        return
    result.insert(insert_at, "")
