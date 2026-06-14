"""Tests for cross-file input rename propagation (uses: ./... callers)."""

import pytest
from gh_formatter.cli import process_file
from gh_formatter.config import Config
from gh_formatter.engine import Engine
from gh_formatter.project import (
    build_project_plan,
    find_repo_root,
    resolve_local_uses,
)


@pytest.fixture
def repo(tmp_path):
    """A minimal repo with a reusable workflow, a local action, and callers."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    action_dir = tmp_path / ".github" / "actions" / "setup"
    action_dir.mkdir(parents=True)

    (workflows / "template.yml").write_text(
        """name: Template
on:
  workflow_call:
    inputs:
      commitSha:
        type: string
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ inputs.commitSha }}"
""",
        encoding="utf-8",
    )

    (action_dir / "action.yml").write_text(
        """name: Setup
inputs:
  nodeVersion:
    description: Node version
runs:
  using: composite
  steps:
    - shell: bash
      run: echo "${{ inputs.nodeVersion }}"
""",
        encoding="utf-8",
    )

    (workflows / "caller.yml").write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commitSha: abc123
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/setup
        with:
          nodeVersion: "20"
""",
        encoding="utf-8",
    )

    return tmp_path


def _format_all(repo, config=None):
    config = config or Config()
    engine = Engine()
    files = sorted(repo.rglob("*.yml"))
    plan = build_project_plan(files, config)
    for f in files:
        process_file(f, engine, config, check=False, show_diff=False, plan=plan)


def test_caller_with_keys_follow_workflow_input_rename(repo):
    _format_all(repo)

    template = (repo / ".github" / "workflows" / "template.yml").read_text(
        encoding="utf-8"
    )
    caller = (repo / ".github" / "workflows" / "caller.yml").read_text(
        encoding="utf-8"
    )

    # Definition renamed
    assert "commit-sha:" in template
    assert "commitSha" not in template
    # Caller's with: key follows
    assert "commit-sha: abc123" in caller
    assert "commitSha" not in caller


def test_caller_with_keys_follow_action_input_rename(repo):
    _format_all(repo)

    action = (repo / ".github" / "actions" / "setup" / "action.yml").read_text(
        encoding="utf-8"
    )
    caller = (repo / ".github" / "workflows" / "caller.yml").read_text(
        encoding="utf-8"
    )

    assert "node-version:" in action
    assert "nodeVersion" not in action
    assert 'node-version: "20"' in caller
    assert "nodeVersion" not in caller


def test_caller_untouched_when_target_not_in_run(repo):
    """Formatting only the caller must not rename its with: keys."""
    config = Config()
    engine = Engine()
    caller_file = repo / ".github" / "workflows" / "caller.yml"
    plan = build_project_plan([caller_file], config)
    process_file(
        caller_file, engine, config, check=False, show_diff=False, plan=plan
    )

    caller = caller_file.read_text(encoding="utf-8")
    assert "commitSha: abc123" in caller
    assert 'nodeVersion: "20"' in caller


def test_external_uses_never_touched(repo):
    """Renames only apply to ./ local references, never to marketplace ones."""
    caller_file = repo / ".github" / "workflows" / "caller.yml"
    caller_file.write_text(
        """name: Caller
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v4
        with:
          nodeVersion: "20"
""",
        encoding="utf-8",
    )
    _format_all(repo)
    caller = caller_file.read_text(encoding="utf-8")
    assert 'nodeVersion: "20"' in caller


def test_find_repo_root(repo):
    workflow = repo / ".github" / "workflows" / "caller.yml"
    assert find_repo_root(str(workflow)) == repo.resolve()
    assert find_repo_root(None) is None


def test_resolve_local_uses(repo):
    root = repo.resolve()
    # Workflow file reference
    assert resolve_local_uses("./.github/workflows/x.yml", root) == [
        root / ".github" / "workflows" / "x.yml"
    ]
    # Action directory reference resolves to both definition names
    candidates = resolve_local_uses("./.github/actions/setup", root)
    assert (root / ".github" / "actions" / "setup" / "action.yml") in candidates
    assert (
        root / ".github" / "actions" / "setup" / "action.yaml"
    ) in candidates
    # Non-local references resolve to nothing
    assert resolve_local_uses("actions/checkout@v4", root) == []
