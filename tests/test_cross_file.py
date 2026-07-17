"""Tests for cross-file input rename propagation (uses: ./... callers)."""

import pytest

from gh_formatter.app.planning import (
    build_project_plan,
    find_repo_root,
    resolve_local_uses,
)
from gh_formatter.app.service import process_file
from gh_formatter.config import Config
from gh_formatter.core.pipeline import Engine


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
    _format_all(repo, Config({"caller_inputs": "fix"}))

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
    _format_all(repo, Config({"caller_inputs": "fix"}))

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


def _errors_for(repo, target_name, config=None):
    """Returns the lint errors emitted while processing `target_name`."""
    config = config or Config()
    engine = Engine()
    files = sorted(repo.rglob("*.yml"))
    plan = build_project_plan(files, config)
    errors: list[str] = []
    for f in files:
        result = process_file(
            f, engine, config, check=True, show_diff=False, plan=plan
        )
        if f.name == target_name:
            errors = result.errors
    return errors


def test_caller_undeclared_input_errors(repo):
    """A with: key the local target does not declare is a (default) error."""
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123
      bogus-input: nope
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert any("bogus-input" in e for e in errors)
    # The valid input is not reported.
    assert not any("'commit-sha' is not" in e for e in errors)


def test_caller_input_casing_mismatch_suggests(repo):
    """A near-miss (casing/separator) yields a did-you-mean suggestion."""
    # Target already declares the canonical name; the caller drifted to
    # camelCase. There is no rename to propagate, so the mismatch persists
    # and is reported with a suggestion.
    template = repo / ".github" / "workflows" / "template.yml"
    template.write_text(
        """name: Template
on:
  workflow_call:
    inputs:
      commit-sha:
        type: string
jobs:
  run:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commitSha: abc123
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert any("commitSha" in e and "commit-sha" in e for e in errors)


def test_caller_fix_mode_renames_mismatch(repo):
    """In fix mode the caller's drifted key is renamed instead of erroring."""
    template = repo / ".github" / "workflows" / "template.yml"
    template.write_text(
        """name: Template
on:
  workflow_call:
    inputs:
      commit-sha:
        type: string
jobs:
  run:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    caller_path = repo / ".github" / "workflows" / "caller.yml"
    caller_path.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commitSha: abc123
""",
        encoding="utf-8",
    )
    _format_all(repo, Config({"caller_inputs": "fix"}))
    caller = caller_path.read_text(encoding="utf-8")
    assert "commit-sha: abc123" in caller
    assert "commitSha" not in caller


def test_caller_ignore_mode_is_silent(repo):
    """In ignore mode a mismatch is neither fixed nor reported."""
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      bogus-input: nope
""",
        encoding="utf-8",
    )
    errors = _errors_for(
        repo, "caller.yml", Config({"caller_inputs": "ignore"})
    )
    assert errors == []


def test_caller_marketplace_uses_not_validated(repo):
    """Non-local (marketplace) calls are never validated."""
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          anything-goes: true
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert not any("anything-goes" in e for e in errors)


def test_caller_non_local_references_never_validated(repo):
    """Only `uses: ./...` is checked: remote reusable workflows, versioned
    marketplace actions, and docker:// references are all left alone."""
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  remote_reusable:
    uses: octo-org/other-repo/.github/workflows/deploy.yml@main
    with:
      undeclared-remote-input: x
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: docker://alpine:3.19
        with:
          args: whatever
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert errors == []


def test_caller_fix_mode_errors_on_unfixable_key(repo):
    """A key with no close match cannot be auto-fixed and stays an error."""
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      totally-unknown: x
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml", Config({"caller_inputs": "fix"}))
    assert any("totally-unknown" in e for e in errors)


def test_caller_zero_input_target_is_checked(repo):
    """Passing inputs to a callable target that declares none is an error."""
    template = repo / ".github" / "workflows" / "template.yml"
    template.write_text(
        """name: Template
on:
  workflow_call: {}
jobs:
  run:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      anything: x
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert any("anything" in e for e in errors)


def test_non_callable_target_not_checked(repo):
    """A plain workflow (no workflow_call) cannot be input-checked."""
    template = repo / ".github" / "workflows" / "template.yml"
    template.write_text(
        """name: Template
on: push
jobs:
  run:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      anything: x
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert errors == []


def _write_deploy_template(repo):
    (repo / ".github" / "workflows" / "template.yml").write_text(
        """name: Template
on:
  workflow_call:
    inputs:
      commit-sha:
        type: string
        required: true
      dry-run:
        type: boolean
        required: false
        default: false
    secrets:
      deploy-token:
        required: true
jobs:
  run:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )


def test_missing_optional_input_is_reported(repo):
    """Every declared input must be passed, defaults notwithstanding."""
    _write_deploy_template(repo)
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123
    secrets:
      deploy-token: ${{ secrets.TOKEN }}
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert any("dry-run" in e and "not passed explicitly" in e for e in errors)


def test_missing_secret_is_reported_and_inherit_accepted(repo):
    _write_deploy_template(repo)
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123
      dry-run: true
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert any(
        "secrets: 'deploy-token'" in e and "not passed" in e for e in errors
    )

    # `secrets: inherit` forwards everything and satisfies the check.
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123
      dry-run: true
    secrets: inherit
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert errors == []


def test_explicit_inputs_check_can_be_disabled(repo):
    _write_deploy_template(repo)
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123
""",
        encoding="utf-8",
    )
    errors = _errors_for(
        repo, "caller.yml", Config({"require_explicit_inputs": False})
    )
    assert errors == []


def test_drifted_key_reported_once_not_twice(repo):
    """A casing-drifted key yields one mismatch error with a suggestion --
    not an additional 'not passed explicitly' error for the same input."""
    template = repo / ".github" / "workflows" / "template.yml"
    template.write_text(
        """name: Template
on:
  workflow_call:
    inputs:
      commit-sha:
        type: string
jobs:
  run:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    caller = repo / ".github" / "workflows" / "caller.yml"
    caller.write_text(
        """name: Caller
on: push
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commitSha: abc123
""",
        encoding="utf-8",
    )
    errors = _errors_for(repo, "caller.yml")
    assert (
        len([e for e in errors if "commit-sha" in e or "commitSha" in e]) == 1
    )
    assert any("did you mean 'commit-sha'" in e for e in errors)
