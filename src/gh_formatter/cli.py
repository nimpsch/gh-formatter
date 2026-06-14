"""Command-line interface: argument parsing and orchestration."""

import argparse
import difflib
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from gh-formatter.config import Config, ConfigError
from gh-formatter.context import Context
from gh-formatter.discovery import find_yaml_files
from gh-formatter.engine import Engine
from gh-formatter.project import ProjectPlan, build_project_plan


class FileStatus(Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    ERROR = "error"


@dataclass
class FileResult:
    status: FileStatus
    message: str
    warnings: list[str] = field(default_factory=list)


def process_file(
    file_path: Path,
    engine: Engine,
    config: Config,
    check: bool,
    show_diff: bool,
    plan: ProjectPlan | None = None,
) -> FileResult:
    """Processes a single file, formatting it or checking for changes."""
    try:
        raw = file_path.read_bytes()
    except Exception as e:
        return FileResult(FileStatus.ERROR, f"Failed to read file: {e}")

    # "preserve" keeps the file's existing line endings instead of
    # letting Python translate to the platform default on write.
    if config.line_endings == "lf":
        newline = "\n"
    else:
        newline = "\r\n" if b"\r\n" in raw else "\n"
    needs_newline_fix = config.line_endings == "lf" and b"\r\n" in raw
    content = raw.decode("utf-8").replace("\r\n", "\n")

    context = Context(str(file_path), config)
    context.project_plan = plan

    try:
        formatted_content = engine.format_string(content, context)
    except Exception as e:
        return FileResult(
            FileStatus.ERROR,
            f"Failed to parse/format file: {e}",
            context.warnings,
        )

    if content == formatted_content and not needs_newline_fix:
        return FileResult(
            FileStatus.UNCHANGED, "Already formatted", context.warnings
        )

    if show_diff:
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            formatted_content.splitlines(keepends=True),
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
        )
        return FileResult(FileStatus.CHANGED, "".join(diff), context.warnings)

    if check:
        return FileResult(
            FileStatus.CHANGED, "Needs formatting", context.warnings
        )

    try:
        with open(file_path, "w", encoding="utf-8", newline=newline) as f:
            f.write(formatted_content)
    except Exception as e:
        return FileResult(
            FileStatus.ERROR, f"Failed to write file: {e}", context.warnings
        )

    return FileResult(
        FileStatus.CHANGED, "Formatted successfully", context.warnings
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Format GitHub Actions and Workflows with custom stylesheets"
        )
    )
    parser.add_argument(
        "paths", nargs="*", help="Paths to files or directories to format"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Dry run: Check if files are formatted, exit with 1 "
            "if changes needed, 0 otherwise"
        ),
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help=(
            "Show unified diff of changes, exit with 1 if changes needed, "
            "0 otherwise"
        ),
    )
    parser.add_argument(
        "--config", dest="config_path", help="Path to custom configuration file"
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all available rules and post-processors, then exit",
    )
    return parser


def _list_rules(engine: Engine) -> None:
    print("Rules:")
    for rule in engine.rules:
        print(f"  {rule.id:<20} {rule.description}")
    print("\nPost-processors:")
    for processor in engine.postprocessors:
        print(f"  {processor.id:<20} {processor.description}")
    print(
        "\nDisable any of these via config, e.g.:\n"
        "  rules:\n    capitalize-names: false"
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    engine = Engine()

    if args.list_rules:
        _list_rules(engine)
        sys.exit(0)

    if not args.paths:
        parser.error("paths is required unless --list-rules is given")

    try:
        config = Config.load(args.config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)

    files = find_yaml_files(args.paths)
    if not files:
        print("No GitHub action or workflow files found.")
        sys.exit(0)

    # Plan input renames across the whole run so callers of local
    # workflows/actions (`uses: ./...`) stay consistent with their targets.
    plan = build_project_plan(files, config)

    changed_files = 0
    errors = 0

    print(f"Checking {len(files)} files...")

    for f in files:
        result = process_file(
            f, engine, config, check=args.check, show_diff=args.diff, plan=plan
        )

        rel_path = os.path.relpath(f, os.getcwd())

        if result.status is FileStatus.ERROR:
            errors += 1
            print(f"[ERROR] {rel_path} - {result.message}")
        elif result.status is FileStatus.CHANGED:
            changed_files += 1
            if args.diff:
                print(f"\n--- Diff for {rel_path} ---")
                print(result.message)
            elif args.check:
                print(f"[X] {rel_path} - Needs formatting")
            else:
                print(f"[Fixed] {rel_path} - Formatted in-place")
        elif args.check:
            print(f"[ok] {rel_path}")

        for warning in result.warnings:
            print(f"[warn] {rel_path} - {warning}")

    print("\nSummary:")
    if args.check or args.diff:
        print(f"  {changed_files} files would be formatted.")
    else:
        print(f"  {changed_files} files formatted.")
    print(f"  {len(files) - changed_files - errors} files left unchanged.")
    if errors:
        print(f"  {errors} errors occurred.")

    if changed_files > 0 and (args.check or args.diff):
        sys.exit(1)

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
