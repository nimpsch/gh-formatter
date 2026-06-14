"""Formatting engine: parse, apply tree rules, dump, post-process."""

from ruamel.yaml.comments import CommentedMap

from gh_formatter.context import Context
from gh_formatter.directives import mark_disabled_nodes, scan_disabled
from gh_formatter.postprocess import BasePostProcessor, BlankLinesProcessor
from gh_formatter.rules.base import BaseRule
from gh_formatter.rules.callers import CallerInputNamingRule
from gh_formatter.rules.inputs import InputNamingRule
from gh_formatter.rules.jobs import JobNamingRule
from gh_formatter.rules.keys import KeyOrderingRule
from gh_formatter.rules.lists import ListStyleRule
from gh_formatter.rules.names import CapitalizeNamesRule
from gh_formatter.rules.quotes import QuoteStyleRule
from gh_formatter.rules.style import StyleRule
from gh_formatter.utils import dump_yaml, load_yaml


def default_rules() -> list[BaseRule]:
    """The built-in tree rules, in execution order."""
    return [
        KeyOrderingRule(),
        InputNamingRule(),
        CallerInputNamingRule(),
        JobNamingRule(),
        CapitalizeNamesRule(),
        ListStyleRule(),
        StyleRule(),
        QuoteStyleRule(),
    ]


def default_postprocessors() -> list[BasePostProcessor]:
    """The built-in text post-processors, in execution order."""
    return [BlankLinesProcessor()]


class Engine:
    """Runs the formatting pipeline over a YAML document.

    The pipeline has two stages: tree rules (BaseRule) transform the
    parsed YAML structure, then post-processors (BasePostProcessor)
    adjust the serialized text. Every stage can be disabled per-id via
    the `rules` config option.
    """

    def __init__(
        self,
        rules: list[BaseRule] | None = None,
        postprocessors: list[BasePostProcessor] | None = None,
    ):
        self.rules = default_rules() if rules is None else rules
        self.postprocessors = (
            default_postprocessors()
            if postprocessors is None
            else postprocessors
        )

    def format_string(self, content: str, context: Context) -> str:
        """Formats a raw YAML string by parsing, running rules, and dumping."""
        if not content.strip():
            return content

        # A whole-file directive short-circuits every rule.
        disable_file, disabled_lines = scan_disabled(content)
        if disable_file:
            return content

        data = load_yaml(content)

        # If root is not a mapping (empty or unusual file), leave it alone.
        if not isinstance(data, CommentedMap):
            return content

        mark_disabled_nodes(data, disabled_lines, context)

        config = context.config

        for rule in self.rules:
            if config.rule_enabled(rule.id) and rule.should_run(context):
                rule.apply(data, context)

        formatted = dump_yaml(
            data,
            indent=config.indent,
            sequence_indent=config.sequence_indent,
            sequence_offset=config.sequence_offset,
        )

        # ruamel does not round-trip an explicit document start marker
        if content.lstrip().startswith("---") and not formatted.startswith(
            "---"
        ):
            formatted = "---\n" + formatted

        for processor in self.postprocessors:
            if config.rule_enabled(processor.id) and processor.should_run(
                context
            ):
                formatted = processor.apply(formatted, context)

        return formatted
