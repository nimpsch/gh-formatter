"""Configuration loading, validation, and typed access."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any, TypeVar, cast

from ruamel.yaml import YAML


class Casing(StrEnum):
    """Naming convention for renamed identifiers (inputs, jobs)."""

    DASH = "dash-case"
    SNAKE = "snake_case"


class ListStyle(StrEnum):
    """YAML style for trigger filter lists under `on:`."""

    FLOW = "flow"
    BLOCK = "block"


class LineEndings(StrEnum):
    """Line-ending policy for written files."""

    PRESERVE = "preserve"
    LF = "lf"


class QuoteStyle(StrEnum):
    """Normalization target for already-quoted scalars."""

    PRESERVE = "preserve"
    SINGLE = "single"
    DOUBLE = "double"


class CallerInputsMode(StrEnum):
    """How caller with:/secrets: keys are checked against local targets."""

    IGNORE = "ignore"
    ERROR = "error"
    FIX = "fix"


DEFAULT_CONFIG: dict[str, Any] = {
    "indent": 2,
    # List items are indented one level under their key, with the dash
    # offset two spaces in (steps:\n  - name: ...) rather than sitting
    # flush under the key.
    "sequence_indent": 4,  # Indentation for list item content
    "sequence_offset": 2,  # Dash offset for list items
    # "dash-case" (e.g. my-input) or "snake_case" (e.g. my_input)
    "input_casing": "dash-case",
    "job_casing": "snake_case",
    # When true, env-var style names (SERVER_IMAGE) keep their uppercase
    # form and only get separators normalized to underscores. When false
    # (default), they are renamed to the configured casing like any name.
    "preserve_uppercase_names": False,
    # "preserve" keeps each file's existing line endings; "lf" rewrites
    # every formatted file with Unix line endings.
    "line_endings": "preserve",
    # Make a yamllint config the source of truth for the settings the two
    # tools share (currently indentation), so a format never produces output
    # the linter rejects. false (default) ignores yamllint; true discovers
    # a .yamllint(.yml/.yaml) in the working directory; a string uses that
    # explicit yamllint config path.
    "defer_to_yamllint": False,
    # Quote style for already-quoted scalars: "double" (default) and
    # "single" normalize every quoted scalar to that character; "preserve"
    # leaves each scalar's existing quoting untouched. Plain (unquoted)
    # scalars are never force-quoted.
    "quote_style": "double",
    # How to handle a caller's with: keys that don't match a LOCAL reusable
    # workflow/action's declared inputs (uses: ./...):
    #   "error" (default): report the mismatch and fail the run
    #   "fix":             rename the caller's keys to match (at own risk)
    #   "ignore":          leave caller inputs alone
    "caller_inputs": "error",
    # Require callers to pass every input/secret a LOCAL target declares,
    # even optional ones with defaults, so the call site is self-documenting.
    # `secrets: inherit` satisfies the secrets side. Only active while
    # caller_inputs is not "ignore".
    "require_explicit_inputs": True,
    # "flow" ([a, b]) or "block" (- a\n- b)
    "list_style": "block",
    # Mapping blocks whose entries are sorted alphabetically (their order
    # never carries meaning). Empty list disables sorting entirely.
    "alphabetize": ["env", "inputs", "outputs", "secrets", "with"],
    "blank_line_between_steps": True,
    "blank_line_between_jobs": True,
    # Trigger filter keys under `on:` whose values are normalized to lists
    "list_keys": [
        "branches",
        "branches-ignore",
        "tags",
        "tags-ignore",
        "paths",
        "paths-ignore",
        "types",
        "workflows",
    ],
    "key_order_workflow": [
        "name",
        "run-name",
        "on",
        "concurrency",
        "permissions",
        "env",
        "defaults",
        "jobs",
    ],
    "key_order_action": [
        "name",
        "description",
        "author",
        "inputs",
        "outputs",
        "runs",
        "branding",
    ],
    "key_order_job": [
        "name",
        "if",
        "needs",
        "runs-on",
        "env",
        # strategy before the call payload (uses/with) it parameterizes
        "strategy",
        "uses",
        "with",
        "secrets",
        "permissions",
        "environment",
        "concurrency",
        "container",
        "services",
        "outputs",
        "defaults",
        "timeout-minutes",
        "continue-on-error",
        "steps",
    ],
    "key_order_step": [
        "name",
        "id",
        "if",
        "env",
        "uses",
        "continue-on-error",
        "working-directory",
        "shell",
        "timeout-minutes",
        # The step body (script or action arguments) always comes last.
        "run",
        "with",
    ],
    # Per-rule toggles, e.g. {"capitalize-names": false}
    "rules": {},
}


class ConfigError(ValueError):
    """Raised when a configuration file or value is invalid."""


class Config:
    """Validated formatter configuration.

    Accepts a raw option mapping (e.g. parsed from a config file), merges it
    over the defaults, and validates every value eagerly so that bad
    configuration fails with a clear message instead of misbehaving deep
    inside a rule.
    """

    def __init__(self, data: dict[str, Any] | None = None):
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError(
                "Configuration must be a mapping of option names to values, "
                f"got {type(data).__name__}."
            )

        unknown = sorted(set(data) - set(DEFAULT_CONFIG))
        if unknown:
            raise ConfigError(
                f"Unknown configuration option(s): {', '.join(unknown)}. "
                f"Valid options: {', '.join(sorted(DEFAULT_CONFIG))}."
            )

        merged = {**DEFAULT_CONFIG, **data}

        self.indent = _require_int(merged, "indent", minimum=1)
        self.sequence_indent = _require_int(
            merged, "sequence_indent", minimum=1
        )
        self.sequence_offset = _require_int(
            merged, "sequence_offset", minimum=0
        )
        self.input_casing = _require_enum(merged, "input_casing", Casing)
        self.job_casing = _require_enum(merged, "job_casing", Casing)
        self.preserve_uppercase_names = _require_bool(
            merged, "preserve_uppercase_names"
        )
        self.line_endings = _require_enum(merged, "line_endings", LineEndings)
        self.quote_style = _require_enum(merged, "quote_style", QuoteStyle)
        self.caller_inputs = _require_enum(
            merged, "caller_inputs", CallerInputsMode
        )
        self.require_explicit_inputs = _require_bool(
            merged, "require_explicit_inputs"
        )
        self.list_style = _require_enum(merged, "list_style", ListStyle)
        self.alphabetize = _require_str_list(merged, "alphabetize")
        self.blank_line_between_steps = _require_bool(
            merged, "blank_line_between_steps"
        )
        self.blank_line_between_jobs = _require_bool(
            merged, "blank_line_between_jobs"
        )
        self.list_keys = _require_str_list(merged, "list_keys")
        self.key_order_workflow = _require_str_list(
            merged, "key_order_workflow"
        )
        self.key_order_action = _require_str_list(merged, "key_order_action")
        self.key_order_job = _require_str_list(merged, "key_order_job")
        self.key_order_step = _require_str_list(merged, "key_order_step")
        self.rules = _require_rule_toggles(merged, "rules")

        # yamllint, when deferred to, wins over the indentation set above.
        self.defer_to_yamllint, self._yamllint_config = _require_yamllint_ref(
            merged, "defer_to_yamllint"
        )
        if self.defer_to_yamllint:
            self._apply_yamllint_overrides()

        if self.sequence_offset >= self.sequence_indent:
            raise ConfigError(
                "'sequence_offset' must be smaller than 'sequence_indent' "
                f"(got offset={self.sequence_offset}, "
                f"indent={self.sequence_indent})."
            )

    def _apply_yamllint_overrides(self) -> None:
        """Overrides indentation with values derived from a yamllint config."""
        from gh_formatter.yamllint_sync import (
            find_yamllint_config,
            indentation_overrides,
        )

        path = self._yamllint_config or find_yamllint_config()
        if path is None:
            raise ConfigError(
                "defer_to_yamllint is enabled but no yamllint config "
                "(.yamllint, .yamllint.yaml, or .yamllint.yml) was found. "
                "Set defer_to_yamllint to an explicit path instead."
            )
        for key, value in indentation_overrides(path).items():
            setattr(self, key, value)

    def rule_enabled(self, rule_id: str) -> bool:
        """Returns whether the rule/post-processor with this id is enabled."""
        return self.rules.get(rule_id, True)

    @classmethod
    def load(cls, config_path: str | None = None) -> Config:
        """Loads config from a path or default locations.

        Raises ConfigError if an explicitly given path does not exist or any
        found file cannot be parsed or contains invalid values.
        """
        if config_path:
            if not os.path.exists(config_path):
                raise ConfigError(f"Config file not found: {config_path}")
            return cls(cls._load_file(config_path))

        defaults = [".gh-formatter.yml", ".gh-formatter.yaml", "pyproject.toml"]
        for path in defaults:
            if os.path.exists(path):
                data = cls._load_file(path)
                if data:
                    return cls(data)

        return cls()

    @classmethod
    def _load_file(cls, path: str) -> dict[str, Any] | None:
        try:
            if path.endswith(".toml"):
                import tomllib  # Python 3.11+

                with open(path, "rb") as f:
                    toml_data = tomllib.load(f)
                # Config resides under [tool.gh-formatter]
                return cast(
                    "dict[str, Any] | None",
                    toml_data.get("tool", {}).get("gh-formatter"),
                )

            yaml = YAML(typ="safe")
            with open(path, encoding="utf-8") as f:
                return cast("dict[str, Any] | None", yaml.load(f))
        except OSError as e:
            raise ConfigError(f"Cannot read config file '{path}': {e}") from e
        except Exception as e:
            raise ConfigError(f"Cannot parse config file '{path}': {e}") from e


def _require_int(data: dict[str, Any], key: str, minimum: int) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"'{key}' must be an integer, got {value!r}.")
    if value < minimum:
        raise ConfigError(f"'{key}' must be >= {minimum}, got {value}.")
    return int(value)


def _require_bool(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be a boolean, got {value!r}.")
    return value


def _require_yamllint_ref(
    data: dict[str, Any], key: str
) -> tuple[bool, str | None]:
    """Parses defer_to_yamllint: bool (auto-discover) or path string.

    Returns (enabled, explicit_path_or_None).
    """
    value = data[key]
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str) and value:
        return True, value
    raise ConfigError(
        f"'{key}' must be a boolean or a path to a yamllint config, "
        f"got {value!r}."
    )


_E = TypeVar("_E", bound=StrEnum)


def _require_enum(data: dict[str, Any], key: str, enum_type: type[_E]) -> _E:
    value = data[key]
    try:
        return enum_type(value)
    except ValueError:
        choices = ", ".join(member.value for member in enum_type)
        raise ConfigError(
            f"'{key}' must be one of {choices}, got {value!r}."
        ) from None


def _require_str_list(data: dict[str, Any], key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ConfigError(f"'{key}' must be a list of strings, got {value!r}.")
    return list(value)


def _require_rule_toggles(data: dict[str, Any], key: str) -> dict[str, bool]:
    value = data[key]
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, bool) for k, v in value.items()
    ):
        raise ConfigError(
            f"'{key}' must map rule ids to booleans, "
            f"e.g. {{capitalize-names: false}}, got {value!r}."
        )
    return dict(value)
