"""Discovery of workflow and action files on disk."""

import os
import sys
from pathlib import Path

# Common directories to skip during recursive search
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
}

ACTION_FILE_NAMES = ("action.yml", "action.yaml")
YAML_SUFFIXES = (".yml", ".yaml")


def find_yaml_files(paths: list[str]) -> list[Path]:
    """Finds all workflow and action files recursively under the given paths.

    Files passed directly are always included; directories are walked for
    `action.yml`/`action.yaml` files and YAML files under
    `.github/workflows/`.
    """
    resolved: set[Path] = set()

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            print(f"Error: Path '{raw_path}' does not exist.", file=sys.stderr)
            continue

        if path.is_file():
            resolved.add(path.resolve())
        elif path.is_dir():
            resolved.update(_walk_directory(path))

    return sorted(resolved)


def _walk_directory(directory: Path) -> set[Path]:
    found: set[Path] = set()

    for root, dirs, files in os.walk(directory):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        is_workflow_dir = ".github/workflows" in Path(root).as_posix()

        for file in files:
            name = file.lower()
            if name in ACTION_FILE_NAMES or (
                is_workflow_dir and name.endswith(YAML_SUFFIXES)
            ):
                found.add((Path(root) / file).resolve())

    return found
