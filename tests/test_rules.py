import pytest

from gh_formatter.config import Config
from gh_formatter.context import Context
from gh_formatter.engine import Engine


@pytest.fixture
def engine():
    return Engine()


def test_key_ordering_workflow(engine):
    workflow_yaml = """
jobs:
  build:
    runs-on: ubuntu-latest
on: push
name: Build Workflow
"""
    context = Context(".github/workflows/build.yml", Config())
    formatted = engine.format_string(workflow_yaml, context)

    # Assert that name is first, then on, then jobs (according to default order)
    lines = [line.strip() for line in formatted.splitlines() if line.strip()]
    name_idx = next(i for i, l in enumerate(lines) if l.startswith("name:"))
    on_idx = next(i for i, l in enumerate(lines) if l.startswith("on:"))
    jobs_idx = next(i for i, l in enumerate(lines) if l.startswith("jobs:"))

    assert name_idx < on_idx
    assert on_idx < jobs_idx


def test_key_ordering_action(engine):
    action_yaml = """
runs:
  using: composite
  steps:
    - run: echo
inputs:
  my-input:
    description: Input
name: My Action
"""
    context = Context("action.yml", Config())
    formatted = engine.format_string(action_yaml, context)

    lines = [line.strip() for line in formatted.splitlines() if line.strip()]
    name_idx = next(i for i, l in enumerate(lines) if l.startswith("name:"))
    inputs_idx = next(i for i, l in enumerate(lines) if l.startswith("inputs:"))
    runs_idx = next(i for i, l in enumerate(lines) if l.startswith("runs:"))

    assert name_idx < inputs_idx
    assert inputs_idx < runs_idx


def test_input_naming_dash_case(engine):
    action_yaml = """
name: My Action
inputs:
  my_input:
    description: Camel input
    required: true
runs:
  using: composite
  steps:
    - run: echo "${{ inputs.my_input }}"
"""
    context = Context("action.yml", Config({"input_casing": "dash-case"}))
    formatted = engine.format_string(action_yaml, context)

    assert "my-input:" in formatted
    assert 'echo "${{ inputs.my-input }}"' in formatted
    assert "my_input" not in formatted


def test_input_naming_snake_case(engine):
    action_yaml = """
name: My Action
inputs:
  my-input:
    description: Dash input
runs:
  using: composite
  steps:
    - run: echo "${{ inputs.my-input }}"
"""
    context = Context("action.yml", Config({"input_casing": "snake_case"}))
    formatted = engine.format_string(action_yaml, context)

    assert "my_input:" in formatted
    assert 'echo "${{ inputs.my_input }}"' in formatted
    assert "my-input" not in formatted


def test_job_naming_snake_case(engine):
    workflow_yaml = """
name: Workflow
jobs:
  my-job:
    runs-on: ubuntu-latest
  another-job:
    needs: my-job
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ needs.my-job.outputs.status }}"
"""
    context = Context(
        ".github/workflows/workflow.yml", Config({"job_casing": "snake_case"})
    )
    formatted = engine.format_string(workflow_yaml, context)

    assert "my_job:" in formatted
    assert "needs: my_job" in formatted
    assert "needs.my_job.outputs.status" in formatted
    assert "my-job" not in formatted


def test_quote_style_normalizes_to_double(engine):
    workflow = """name: 'CI Workflow'
on:
  push:
    branches: ['main', 'dev']
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      FOO: 'bar'
    steps:
      - run: echo hi
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    assert 'name: "CI Workflow"' in formatted
    assert 'FOO: "bar"' in formatted
    assert '"main"' in formatted and '"dev"' in formatted
    # plain unquoted scalars are never force-quoted
    assert "runs-on: ubuntu-latest" in formatted
    assert "run: echo hi" in formatted


def test_quote_style_normalizes_to_single(engine):
    workflow = """name: "CI Workflow"
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      FOO: "bar"
    steps:
      - run: echo hi
"""
    context = Context(
        ".github/workflows/ci.yml", Config({"quote_style": "single"})
    )
    formatted = engine.format_string(workflow, context)

    assert "name: 'CI Workflow'" in formatted
    assert "FOO: 'bar'" in formatted


def test_quote_style_preserve_leaves_quotes(engine):
    workflow = """name: 'CI Workflow'
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      FOO: "bar"
"""
    context = Context(
        ".github/workflows/ci.yml", Config({"quote_style": "preserve"})
    )
    formatted = engine.format_string(workflow, context)

    assert "name: 'CI Workflow'" in formatted
    assert 'FOO: "bar"' in formatted


def test_quote_style_keeps_block_scalars(engine):
    """A `run: |` block must never be turned into a quoted scalar."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "hello"
          echo "world"
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    assert "run: |" in formatted
    assert '        echo "hello"' in formatted


def test_style_trim_and_boolean(engine):
    workflow_yaml = """
name: Workflow
jobs:
  build:
    runs-on: ubuntu-latest
    continue-on-error: "true"
    steps:
      - name: Trim space
        run: |
          echo "Hello"
          echo "World"
"""
    context = Context(".github/workflows/workflow.yml", Config())
    formatted = engine.format_string(workflow_yaml, context)

    # Assert continue-on-error converted to boolean true
    assert "continue-on-error: true" in formatted
    # Assert trailing whitespaces trimmed in multi-line block
    assert 'echo "Hello"\n' in formatted
    assert 'echo "World"\n' in formatted
    assert 'echo "Hello"   \n' not in formatted


def test_if_expressions_wrapped(engine):
    workflow = """name: ci
jobs:
  build:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: bare
        if: success()
        run: echo hi
      - name: already
        if: ${{ always() }}
        run: echo bye
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    assert "if: ${{ github.event_name == 'push' }}" in formatted  # job
    assert "if: ${{ success() }}" in formatted  # step, bare -> wrapped
    assert "if: ${{ always() }}" in formatted  # already wrapped, unchanged
    assert formatted.count("${{ always() }}") == 1  # not double-wrapped


def test_if_expressions_skip_booleans_and_toggle(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: literal
        if: true
        run: echo hi
      - name: bare
        if: success()
        run: echo bye
"""
    # Booleans are left alone; the rule can be turned off entirely.
    on = engine.format_string(
        workflow, Context(".github/workflows/ci.yml", Config())
    )
    assert "if: true" in on  # YAML boolean untouched
    assert "if: ${{ success() }}" in on

    off = engine.format_string(
        workflow,
        Context(
            ".github/workflows/ci.yml",
            Config({"rules": {"if-expressions": False}}),
        ),
    )
    assert "if: success()" in off  # left bare when disabled


def test_if_above_id_in_step_order(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - id: step1
        run: echo hi
        if: ${{ success() }}
        name: My step
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)
    # Order: name, if, id, ...
    assert formatted.index("name: My step") < formatted.index("if:")
    assert formatted.index("if:") < formatted.index("id: step1")
