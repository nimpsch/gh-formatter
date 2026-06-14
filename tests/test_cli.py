import subprocess
import sys


def test_cli_help():
    # Run CLI with --help to check that it displays usage information
    result = subprocess.run(
        [sys.executable, "-m", "gh_formatter.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Format GitHub Actions and Workflows" in result.stdout


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
