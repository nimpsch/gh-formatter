"""Built-in formatting rules."""

from gh-formatter.rules.base import BaseRule
from gh-formatter.rules.callers import CallerInputNamingRule
from gh-formatter.rules.inputs import InputNamingRule
from gh-formatter.rules.jobs import JobNamingRule
from gh-formatter.rules.keys import KeyOrderingRule
from gh-formatter.rules.lists import ListStyleRule
from gh-formatter.rules.names import CapitalizeNamesRule
from gh-formatter.rules.style import StyleRule

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
