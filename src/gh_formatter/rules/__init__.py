"""Built-in formatting rules."""

from gh_formatter.rules.base import BaseRule
from gh_formatter.rules.callers import CallerInputNamingRule
from gh_formatter.rules.inputs import InputNamingRule
from gh_formatter.rules.jobs import JobNamingRule
from gh_formatter.rules.keys import KeyOrderingRule
from gh_formatter.rules.lists import ListStyleRule
from gh_formatter.rules.names import CapitalizeNamesRule
from gh_formatter.rules.style import StyleRule

__all__ = [
    "BaseRule",
    "CallerInputNamingRule",
    "CapitalizeNamesRule",
    "InputNamingRule",
    "JobNamingRule",
    "KeyOrderingRule",
    "ListStyleRule",
    "StyleRule",
]
