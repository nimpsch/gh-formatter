from abc import ABC, abstractmethod

from ruamel.yaml.comments import CommentedMap

from gh_formatter.core.context import Context


class BaseRule(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """A unique string identifier for the rule."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A short description of what the rule does."""
        pass

    @abstractmethod
    def should_run(self, context: Context) -> bool:
        """Determine if this rule applies to the current context."""
        pass

    @abstractmethod
    def apply(self, data: CommentedMap, context: Context) -> None:
        """Apply the rule in-place to the parsed YAML CommentedMap."""
        pass
