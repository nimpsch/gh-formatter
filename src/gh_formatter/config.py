"""Configuration loading, validation, and typed access."""

from __future__ import annotations

import os
from typing import Any, cast

from ruamel.yaml import YAML

VALID_CASINGS = ("dash-case", "snake_case")
VALID_LIST_STYLES = ("flow", "block")
VALID_LINE_ENDINGS = ("preserve", "lf")

DEFAULT_CONFIG: dict[str, Any] = {
    "indent": 2,
    "sequence_indent": 2,  # Indentation for list items
    "sequence_offset": 0,  # Dash offset for list items
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
    # "flow" ([a, b]) or "block" (- a\n- b)
    "list_style": "block",
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
        # Reusable workflow call jobs
        "uses",
        "with",
        "secrets",
        "permissions",
        "environment",
        "concurrency",
        "strategy",
        "container",
        "services",
        "outputs",
        "env",
        "defaults",
        "timeout-minutes",
        "continue-on-error",
        # steps last: it is the bulk of the job
        "steps",
    ],
    "key_order_step": [
        "name",
        "id",
        "uses",
        "run",
        "with",
        "env",
        "timeout-minutes",
        "continue-on-error",
        "if",
        "shell",
        "working-directory",
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
        self.input_casing = _require_choice(
            merged, "input_casing", VALID_CASINGS
        )
        self.job_casing = _require_choice(merged, "job_casing", VALID_CASINGS)
        self.preserve_uppercase_names = _require_bool(
            merged, "preserve_uppercase_names"
        )
        self.line_endings = _require_choice(
            merged, "line_endings", VALID_LINE_ENDINGS
        )
        self.list_style = _require_choice(
            merged, "list_style", VALID_LIST_STYLES
        )
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

        if self.sequence_offset >= self.sequence_indent:
            raise ConfigError(
                "'sequence_offset' must be smaller than 'sequence_indent' "
                f"(got offset={self.sequence_offset}, "
                f"indent={self.sequence_indent})."
            )

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
    return value


def _require_bool(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be a boolean, got {value!r}.")
    return value


def _require_choice(
    data: dict[str, Any], key: str, choices: tuple[str, ...]
) -> str:
    value = data[key]
    if value not in choices:
        raise ConfigError(
            f"'{key}' must be one of {', '.join(choices)}, got {value!r}."
        )
    return str(value)


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
