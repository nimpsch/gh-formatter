"""Identifier casing conversion and collision-safe rename planning."""

import re

from gh_formatter.context import Context

# Split camelCase/PascalCase at word boundaries; keeps acronyms intact
# (myURLInput -> my-URL-Input, not my-U-R-L-Input).
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS = re.compile(r"[\s_]+")
_DASH_RUNS = re.compile(r"-{2,}")

# Entirely uppercase identifiers (env-var style, e.g. SERVER_IMAGE)
_ALL_UPPERCASE = re.compile(r"^[A-Z0-9_-]+$")
_UPPER_SEPARATORS = re.compile(r"[\s_-]+")


def is_uppercase_name(name: str) -> bool:
    """Returns True for env-var style names like SERVER_IMAGE or MM_ENV."""
    return bool(_ALL_UPPERCASE.match(name)) and any(c.isalpha() for c in name)


def normalize_uppercase(name: str) -> str:
    """Normalizes an uppercase identifier to underscore separators.

    SERVER-IMAGE -> SERVER_IMAGE; SERVER_IMAGE stays unchanged.
    """
    cleaned = _UPPER_SEPARATORS.sub("_", name).strip("_")
    return cleaned or name


def format_casing(name: str, target: str) -> str:
    """Converts an identifier to dash-case or snake_case."""
    cleaned = _CAMEL_BOUNDARY.sub("-", name)
    cleaned = _SEPARATORS.sub("-", cleaned).lower()
    cleaned = _DASH_RUNS.sub("-", cleaned).strip("-")
    if not cleaned:
        # Name consists only of separators; leave it untouched.
        return name
    if target == "snake_case":
        return cleaned.replace("-", "_")
    return cleaned


def compute_safe_renames(
    keys: list[str],
    target_casing: str,
    context: Context,
    kind: str,
    preserve_uppercase: bool = False,
) -> dict[str, str]:
    """Plans renames to the target casing, skipping any that would collide.

    A rename is skipped (with a warning) when the formatted name already
    exists among the keys or is produced by another rename — applying it
    would silently overwrite a sibling definition. With
    ``preserve_uppercase``, env-var style names (SERVER_IMAGE) keep their
    uppercase form and only have separators normalized to underscores.
    """
    existing = set(keys)
    renames: dict[str, str] = {}
    targets: set[str] = set()

    for key in keys:
        if preserve_uppercase and is_uppercase_name(key):
            formatted = normalize_uppercase(key)
        else:
            formatted = format_casing(key, target_casing)
        if formatted == key:
            continue
        if formatted in existing or formatted in targets:
            context.add_warning(
                f"Skipped renaming {kind} '{key}' to '{formatted}': "
                "the target name is already in use"
            )
            continue
        renames[key] = formatted
        targets.add(formatted)

    return renames
