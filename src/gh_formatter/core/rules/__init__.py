"""Built-in formatting rules."""

from gh_formatter.core.rules.alphabetize import AlphabetizeRule
from gh_formatter.core.rules.base import BaseRule
from gh_formatter.core.rules.callers import CallerInputRule
from gh_formatter.core.rules.if_expressions import IfExpressionRule
from gh_formatter.core.rules.inputs import InputNamingRule
from gh_formatter.core.rules.jobs import JobNamingRule
from gh_formatter.core.rules.keys import KeyOrderingRule
from gh_formatter.core.rules.lists import ListStyleRule
from gh_formatter.core.rules.names import CapitalizeNamesRule
from gh_formatter.core.rules.quotes import QuoteStyleRule
from gh_formatter.core.rules.style import StyleRule

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
