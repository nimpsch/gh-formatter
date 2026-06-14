"""Text post-processors that run on the serialized YAML output.

Post-processors handle purely presentational concerns (like blank lines)
that cannot be expressed in the parsed YAML tree. They run after the
tree rules and the YAML dump, and operate on the canonical text the
dumper produced.
"""

import re
from abc import ABC, abstractmethod

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
        config = context.config
        lines = text.split("\n")
        result: list[str] = []

        # Block scalar tracking: never touch lines inside `run: |` etc.,
        # where text like `steps:` or `- item` is script content.
        in_block_scalar = False
        block_scalar_indent = 0

        in_steps = False
        step_dash_col = 0

        in_jobs = False
        job_indent = config.indent

        for line in lines:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))

            if in_block_scalar:
                if stripped and indent <= block_scalar_indent:
                    in_block_scalar = False
                else:
                    result.append(line)
                    continue

            is_content = bool(stripped) and not stripped.startswith("#")

            if is_content:
                # Leaving the current steps sequence?
                if in_steps and (
                    indent < step_dash_col
                    or (
                        indent == step_dash_col
                        and not _is_sequence_item(stripped)
                        and stripped != "steps:"
                    )
                ):
                    in_steps = False

                # Entering/leaving the root-level jobs block?
                if indent == 0:
                    in_jobs = stripped == "jobs:"

            if stripped == "steps:":
                in_steps = True
                # ruamel places sequence dashes at key indent + offset
                step_dash_col = indent + config.sequence_offset

            elif (
                config.blank_line_between_steps
                and in_steps
                and indent == step_dash_col
                and _is_sequence_item(stripped)
            ):
                _separate_item(result, "steps:")

            elif (
                config.blank_line_between_jobs
                and in_jobs
                and is_content
                and indent == job_indent
                and not _is_sequence_item(stripped)
                and ":" in stripped
            ):
                _separate_item(result, "jobs:")

            result.append(line)

            if is_content and _BLOCK_SCALAR_OPENER.search(stripped):
                in_block_scalar = True
                block_scalar_indent = indent

        return "\n".join(result)


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
