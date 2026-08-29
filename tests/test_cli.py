import re
import subprocess
import sys

from gh_formatter import __version__


def test_cli_help():
    # Run CLI with --help to check that it displays usage information
    result = subprocess.run(
        [sys.executable, "-m", "gh_formatter.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Format GitHub Actions and Workflows" in result.stdout


def test_cli_version():
    # --version prints the package version and exits 0
    result = subprocess.run(
        [sys.executable, "-m", "gh_formatter.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_cli_formatting(tmp_path):
    # Setup temporary workflow file
    workflow_file = tmp_path / "build.yml"
    # Ensure it lies inside .github/workflows to trigger workflow detection during dir search
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow_file = workflow_dir / "build.yml"

    workflow_file.write_text(
        """
jobs:
  build:
    runs-on: ubuntu-latest
on: push
name: Workflow
""",
        encoding="utf-8",
    )

    # Run check mode - should exit with 1 because it's not formatted (keys are in wrong order)
    result_check = subprocess.run(
        [
            sys.executable,
            "-m",
            "gh_formatter.cli",
            str(workflow_file),
            "--check",
        ],
        capture_output=True,
        text=True,
    )
    assert result_check.returncode == 1
    assert "Needs formatting" in result_check.stdout

    # Run actual format
    result_format = subprocess.run(
        [sys.executable, "-m", "gh_formatter.cli", str(workflow_file)],
        capture_output=True,
        text=True,
    )
    assert result_format.returncode == 0
    assert "Formatted in-place" in result_format.stdout

    # Run check mode again - should exit with 0 now
    result_check_again = subprocess.run(
        [
            sys.executable,
            "-m",
            "gh_formatter.cli",
            str(workflow_file),
            "--check",
        ],
        capture_output=True,
        text=True,
    )
    assert result_check_again.returncode == 0


def test_cli_reports_invalid_yaml_location(tmp_path):
    # An unclosed flow sequence should surface as file:line:col -- the shape
    # editors (e.g. VS Code's terminal) turn into a clickable link.
    workflow_file = tmp_path / "build.yml"
    workflow_file.write_text(
        """name: ci
on:
  push:
    branches: [main
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gh_formatter.cli",
            str(workflow_file),
            "--check",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert re.search(
        r"\[ERROR\] .*build\.yml:\d+:\d+ - Invalid YAML", result.stdout
    )


def test_exit_code():
    import argparse

    from gh_formatter.cli import _Counts, _exit_code

    plain = argparse.Namespace(check=False, diff=False)
    check = argparse.Namespace(check=True, diff=False)

    # Clean run -> success.
    assert _exit_code(_Counts(), plain) == 0
    # Warnings alone never fail the run.
    assert _exit_code(_Counts(warnings=3), plain) == 0
    # Lint errors (e.g. caller-input mismatches) always fail.
    assert _exit_code(_Counts(lint_errors=1), plain) == 1
    # Processing errors fail.
    assert _exit_code(_Counts(errors=1), plain) == 1
    # In --check mode, files needing formatting fail; not in format mode.
    assert _exit_code(_Counts(changed=2), check) == 1
    assert _exit_code(_Counts(changed=2), plain) == 0
