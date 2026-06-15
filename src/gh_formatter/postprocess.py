"""Text post-processors that run on the serialized YAML output.

Post-processors handle purely presentational concerns (like blank lines)
that cannot be expressed in the parsed YAML tree. They run after the
tree rules and the YAML dump, and operate on the canonical text the
dumper produced.
"""

import re
from abc import ABC, abstractmethod

from gh_formatter.config import Config
from gh_formatter.context import Context

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
    """Inserts blank lines between steps and between jobs."""

    @property
    def id(self) -> str:
        return "blank-lines"

    @property
    def description(self) -> str:
        return "Insert blank lines between steps and between jobs"

    def should_run(self, context: Context) -> bool:
        config = context.config
        return config.blank_line_between_steps or config.blank_line_between_jobs

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
        self.in_steps = False
        self.step_dash_col = 0
        self.in_jobs = False
        self.job_indent = config.indent

    def run(self, lines: list[str]) -> list[str]:
        for line in lines:
            self._feed(line)
        return self.result

    def _feed(self, line: str) -> None:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if self._consume_block_scalar(line, stripped, indent):
            return

        is_content = bool(stripped) and not stripped.startswith("#")
        if is_content:
            self._update_scopes(stripped, indent)

        self._maybe_separate(stripped, indent, is_content)
        self.result.append(line)

        if is_content and _BLOCK_SCALAR_OPENER.search(stripped):
            self.in_block_scalar = True
            self.block_scalar_indent = indent

    def _consume_block_scalar(
        self, line: str, stripped: str, indent: int
    ) -> bool:
        """Swallows lines inside a block scalar; returns True when it does."""
        if not self.in_block_scalar:
            return False
        if stripped and indent <= self.block_scalar_indent:
            self.in_block_scalar = False  # dedented out: process normally
            return False
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
