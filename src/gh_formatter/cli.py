"""Command-line interface: argument parsing and orchestration."""

import argparse
import difflib
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from gh_formatter import __version__
from gh_formatter.config import Config, ConfigError
from gh_formatter.context import Context
from gh_formatter.discovery import find_yaml_files
from gh_formatter.engine import Engine
from gh_formatter.project import ProjectPlan, build_project_plan


class FileStatus(Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    ERROR = "error"


@dataclass
class FileResult:
    status: FileStatus
    message: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
            context.errors,
        )

    if content == formatted_content and not needs_newline_fix:
        return FileResult(
            FileStatus.UNCHANGED,
            "Already formatted",
            context.warnings,
            context.errors,
        )

    if show_diff:
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            formatted_content.splitlines(keepends=True),
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
        )
        return FileResult(
            FileStatus.CHANGED, "".join(diff), context.warnings, context.errors
        )

    if check:
        return FileResult(
            FileStatus.CHANGED,
            "Needs formatting",
            context.warnings,
            context.errors,
        )

    try:
        with open(file_path, "w", encoding="utf-8", newline=newline) as f:
            f.write(formatted_content)
    except Exception as e:
        return FileResult(
            FileStatus.ERROR,
            f"Failed to write file: {e}",
            context.warnings,
            context.errors,
        )

    return FileResult(
        FileStatus.CHANGED,
        "Formatted successfully",
        context.warnings,
        context.errors,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Format GitHub Actions and Workflows with custom stylesheets"
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version and exit",
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

    config = _load_config(args.config_path)
    files = find_yaml_files(args.paths)
    if not files:
        print("No GitHub action or workflow files found.")
        sys.exit(0)

    counts = _format_files(files, engine, config, args)
    _print_summary(len(files), counts, args)
    sys.exit(_exit_code(counts, args))


def _load_config(config_path: str | None) -> Config:
    """Loads the config, exiting with code 2 on a configuration error."""
    try:
        return Config.load(config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)


@dataclass
class _Counts:
    """Tallies across a run, used for the summary and exit code."""

    changed: int = 0
    errors: int = 0  # files that failed to read/parse/write
    lint_errors: int = 0  # caller-input (and similar) errors that must be fixed
    warnings: int = 0


def _format_files(
    files: list[Path],
    engine: Engine,
    config: Config,
    args: argparse.Namespace,
) -> _Counts:
    """Processes each file, prints output, and returns the run tallies."""
    # Plan the canonical inputs of local targets so callers can be checked.
    plan = build_project_plan(files, config)

    counts = _Counts()
    print(f"Checking {len(files)} files...")
    for f in files:
        result = process_file(
            f, engine, config, check=args.check, show_diff=args.diff, plan=plan
        )
        rel_path = os.path.relpath(f, os.getcwd())
        _report_file(result, rel_path, args)
        if result.status is FileStatus.ERROR:
            counts.errors += 1
        elif result.status is FileStatus.CHANGED:
            counts.changed += 1
        for error in result.errors:
            counts.lint_errors += 1
            print(f"[error] {rel_path} - {error}")
        for warning in result.warnings:
            counts.warnings += 1
            print(f"[warn] {rel_path} - {warning}")
    return counts


def _report_file(
    result: FileResult, rel_path: str, args: argparse.Namespace
) -> None:
    """Prints the one-line status for a processed file."""
    if result.status is FileStatus.ERROR:
        print(f"[ERROR] {rel_path} - {result.message}")
    elif result.status is FileStatus.CHANGED:
        if args.diff:
            print(f"\n--- Diff for {rel_path} ---")
            print(result.message)
        elif args.check:
            print(f"[X] {rel_path} - Needs formatting")
        else:
            print(f"[Fixed] {rel_path} - Formatted in-place")
    elif args.check:
        print(f"[ok] {rel_path}")


def _print_summary(
    total: int, counts: _Counts, args: argparse.Namespace
) -> None:
    """Prints the run summary."""
    print("\nSummary:")
    if args.check or args.diff:
        print(f"  {counts.changed} files would be formatted.")
    else:
        print(f"  {counts.changed} files formatted.")
    unchanged = total - counts.changed - counts.errors
    print(f"  {unchanged} files left unchanged.")
    if counts.warnings:
        print(f"  {counts.warnings} warnings.")
    if counts.lint_errors:
        print(f"  {counts.lint_errors} errors must be fixed.")
    if counts.errors:
        print(f"  {counts.errors} files could not be processed.")


def _exit_code(counts: _Counts, args: argparse.Namespace) -> int:
    """Returns the process exit code from the run outcome."""
    if counts.changed > 0 and (args.check or args.diff):
        return 1
    if counts.errors or counts.lint_errors:
        return 1
    return 0


if __name__ == "__main__":
    main()
