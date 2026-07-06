"""Built-in formatting rules."""

from gh_formatter.rules.alphabetize import AlphabetizeRule
from gh_formatter.rules.base import BaseRule
from gh_formatter.rules.callers import CallerInputRule
from gh_formatter.rules.if_expressions import IfExpressionRule
from gh_formatter.rules.inputs import InputNamingRule
from gh_formatter.rules.jobs import JobNamingRule
from gh_formatter.rules.keys import KeyOrderingRule
from gh_formatter.rules.lists import ListStyleRule
from gh_formatter.rules.names import CapitalizeNamesRule
from gh_formatter.rules.quotes import QuoteStyleRule
from gh_formatter.rules.style import StyleRule

__all__ = [
    "AlphabetizeRule",
    "BaseRule",
    "CallerInputRule",
    "CapitalizeNamesRule",
    "IfExpressionRule",
    "InputNamingRule",
    "JobNamingRule",
    "KeyOrderingRule",
    "ListStyleRule",
    "QuoteStyleRule",
    "StyleRule",
]
