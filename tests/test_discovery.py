"""Tests for workflow/action file discovery."""

from pathlib import Path

from gh_formatter.io.discovery import find_yaml_files


def _write(path: Path, content: str = "placeholder: true\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_finds_workflow_files_under_github_workflows(tmp_path):
    _write(tmp_path / ".github" / "workflows" / "ci.yml")
    found = find_yaml_files([str(tmp_path)])
    assert found == [(tmp_path / ".github" / "workflows" / "ci.yml").resolve()]


def test_finds_action_files_anywhere(tmp_path):
    _write(tmp_path / "some-action" / "action.yml")
    _write(tmp_path / "nested" / "deep" / "action.yaml")
    found = find_yaml_files([str(tmp_path)])
    assert found == sorted(
        {
            (tmp_path / "some-action" / "action.yml").resolve(),
            (tmp_path / "nested" / "deep" / "action.yaml").resolve(),
        }
    )


def test_ignores_yaml_files_outside_workflows_and_not_named_action(tmp_path):
    """A plain YAML file elsewhere in the project (docker-compose.yml,
    a Kubernetes manifest, mkdocs.yml, ...) must never be swept in."""
    _write(tmp_path / "docker-compose.yml")
    _write(tmp_path / "deploy" / "kubernetes" / "deployment.yaml")
    _write(tmp_path / "docs" / "mkdocs.yml")
    found = find_yaml_files([str(tmp_path)])
    assert found == []


def test_ignores_sibling_of_workflows_directory(tmp_path):
    """Regression: a directory whose name merely starts with `workflows`
    (`.github/workflows-templates/`) is not the workflows directory --
    matching it via substring containment was the original bug."""
    _write(tmp_path / ".github" / "workflows" / "ci.yml")
    _write(tmp_path / ".github" / "workflows-templates" / "template.yml")
    found = find_yaml_files([str(tmp_path)])
    assert found == [(tmp_path / ".github" / "workflows" / "ci.yml").resolve()]


def test_ignores_yaml_nested_below_workflows_directory(tmp_path):
    """GitHub only treats files directly inside `.github/workflows/` as
    workflows; a nested subdirectory is invisible to it, so gh-formatter
    must not touch YAML placed there either."""
    _write(tmp_path / ".github" / "workflows" / "ci.yml")
    _write(tmp_path / ".github" / "workflows" / "templates" / "nested.yml")
    found = find_yaml_files([str(tmp_path)])
    assert found == [(tmp_path / ".github" / "workflows" / "ci.yml").resolve()]


def test_finds_workflows_in_monorepo_subprojects(tmp_path):
    """A `.github/workflows` directory nested arbitrarily deep (a monorepo
    subproject with its own workflows) is still discovered."""
    _write(tmp_path / "subproject" / ".github" / "workflows" / "ci.yml")
    found = find_yaml_files([str(tmp_path)])
    assert found == [
        (tmp_path / "subproject" / ".github" / "workflows" / "ci.yml").resolve()
    ]


def test_ignores_common_dependency_directories(tmp_path):
    _write(
        tmp_path / "node_modules" / "pkg" / ".github" / "workflows" / "ci.yml"
    )
    _write(tmp_path / ".venv" / "lib" / ".github" / "workflows" / "ci.yml")
    _write(tmp_path / ".git" / ".github" / "workflows" / "ci.yml")
    found = find_yaml_files([str(tmp_path)])
    assert found == []


def test_explicit_file_argument_is_always_included(tmp_path):
    """A file passed directly on the command line is processed regardless
    of its location -- only directory *walks* are scoped to workflows and
    actions. This lets users (and this project's own CI) explicitly format
    an example/showcase file that lives outside .github/workflows."""
    target = tmp_path / "examples" / "showcase.yml"
    _write(target)
    found = find_yaml_files([str(target)])
    assert found == [target.resolve()]


def test_action_file_name_is_case_insensitive(tmp_path):
    _write(tmp_path / "my-action" / "Action.YML")
    found = find_yaml_files([str(tmp_path)])
    assert found == [(tmp_path / "my-action" / "Action.YML").resolve()]
