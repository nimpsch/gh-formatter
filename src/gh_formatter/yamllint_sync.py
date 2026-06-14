"""Derive gh-formatter settings from a yamllint config.

When ``defer_to_yamllint`` is enabled, yamllint becomes the single source of
truth for the settings the two tools share (currently indentation). This
keeps a formatter run from producing output that the project's linter would
immediately reject.

yamllint's own API is used to read the config so that ``extends:`` chains and
presets resolve exactly the way yamllint itself resolves them.
"""

from __future__ import annotations

import os

from gh_formatter.config import ConfigError

# Standard yamllint config filenames, in yamllint's own discovery order.
YAMLLINT_CONFIG_NAMES = (".yamllint", ".yamllint.yaml", ".yamllint.yml")


def find_yamllint_config(base_dir: str = ".") -> str | None:
    """Returns the first standard yamllint config file in `base_dir`, if any."""
    for name in YAMLLINT_CONFIG_NAMES:
        path = os.path.join(base_dir, name)
        if os.path.isfile(path):
            return path
    return None


def indentation_overrides(config_path: str) -> dict[str, int]:
    """Maps a yamllint config's `indentation` rule to gh-formatter settings.

    Returns a subset of ``indent`` / ``sequence_indent`` / ``sequence_offset``.
    Empty when the yamllint config disables indentation or leaves ``spaces``
    as ``consistent`` (no concrete width to copy).

    Raises ConfigError if yamllint is not installed or the file cannot be read.
    """
    try:
        from yamllint.config import YamlLintConfig
    except ImportError as e:
        raise ConfigError(
            "defer_to_yamllint requires yamllint to be installed "
            "(pip install yamllint)."
        ) from e

    if not os.path.isfile(config_path):
        raise ConfigError(f"yamllint config file not found: {config_path}")

    try:
        conf = YamlLintConfig(file=config_path)
    except Exception as e:
        raise ConfigError(
            f"Cannot parse yamllint config '{config_path}': {e}"
        ) from e

    rule = conf.rules.get("indentation")
    if not isinstance(rule, dict):
        return {}  # indentation checking disabled in yamllint

    spaces = rule.get("spaces")
    if not isinstance(spaces, int) or spaces < 1:
        return {}  # "consistent": no concrete width to mirror

    # Content always sits one space after the dash (offset + 2) so the output
    # also satisfies yamllint's `hyphens` rule (max 1 space after a hyphen).
    overrides: dict[str, int] = {"indent": spaces}
    if rule.get("indent-sequences") is False:
        # Dashes flush with their key: `key:\n- item`.
        overrides["sequence_offset"] = 0
        overrides["sequence_indent"] = 2
    else:
        # Dashes indented one level under their key: `key:\n  - item` (also
        # satisfies yamllint's "consistent"/"whatever" sequence settings).
        overrides["sequence_offset"] = spaces
        overrides["sequence_indent"] = spaces + 2
    return overrides
