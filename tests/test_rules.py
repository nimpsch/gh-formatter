import pytest

from gh_formatter.config import Config
from gh_formatter.core.context import Context
from gh_formatter.core.pipeline import Engine


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


def test_if_sits_above_step_body(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
        if: ${{ success() }}
        name: My step
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)
    # The gate (`if`) is ordered above the step body (`run`/`uses`).
    assert formatted.index("name: My step") < formatted.index("if:")
    assert formatted.index("if:") < formatted.index("run: echo hi")


def test_alphabetize_sorts_configured_blocks(engine):
    workflow = """name: ci
on:
  workflow_call:
    inputs:
      zeta:
        type: string
      alpha:
        type: string
    secrets:
      Z_TOKEN:
        required: true
      a-token:
        required: false
env:
  ZED: "1"
  ALPHA: "2"
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: octo/repo
          fetch-depth: 0
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    assert formatted.index("alpha:") < formatted.index("zeta:")
    # Case-insensitive: a-token sorts before Z_TOKEN.
    assert formatted.index("a-token:") < formatted.index("Z_TOKEN:")
    assert formatted.index("ALPHA:") < formatted.index("ZED:")
    assert formatted.index("fetch-depth:") < formatted.index("repository:")


def test_alphabetize_comment_travels_with_entry(engine):
    workflow = """name: ci
on:
  workflow_call:
    inputs:
      zeta:
        type: string
      # explains alpha
      alpha:
        type: string
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    # The pre-comment moves with alpha to the top, above its new position.
    assert "# explains alpha\n      alpha:" in formatted
    assert engine.format_string(formatted, context) == formatted


def test_alphabetize_comment_above_nested_entry_travels_with_it(engine):
    # Regression test: a comment above a nested-mapping-valued entry (e.g. a
    # workflow_dispatch input with description/type) used to stay behind at
    # its old position instead of moving with the entry it documents, once
    # that entry stopped being last after sorting.
    workflow = """name: ci
on:
  workflow_dispatch:
    inputs:
      # explains zeta
      zeta:
        description: "Zeta input"
        type: string
      # explains alpha
      alpha:
        description: "Alpha input"
        type: string
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    assert "# explains alpha\n      alpha:" in formatted
    assert "# explains zeta\n      zeta:" in formatted
    assert formatted.index("alpha:") < formatted.index("zeta:")
    assert engine.format_string(formatted, context) == formatted


def test_alphabetize_disabled_via_empty_list(engine):
    workflow = """name: ci
env:
  ZED: "1"
  ALPHA: "2"
jobs:
  build:
    runs-on: ubuntu-latest
"""
    context = Context(".github/workflows/ci.yml", Config({"alphabetize": []}))
    formatted = engine.format_string(workflow, context)
    assert formatted.index("ZED:") < formatted.index("ALPHA:")


def test_nested_quotes_use_opposite_char(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      NESTED: "he said \\"hi\\""
      APOSTROPHE: 'it''s fine'
      BOTH: "mix \\"double\\" and 'single'"
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    # Double quotes inside -> wrapped in single quotes, no escaping.
    assert "NESTED: 'he said \"hi\"'" in formatted
    # Apostrophe inside -> double quotes.
    assert 'APOSTROPHE: "it\'s fine"' in formatted
    # Both kinds present -> configured style wins (escaping unavoidable).
    assert 'BOTH: "mix \\"double\\" and \'single\'"' in formatted


def test_run_and_with_are_last_in_step(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
        shell: bash
        working-directory: .
        name: script step
      - with:
          ref: main
        uses: actions/checkout@v4
        name: action step
"""
    context = Context(".github/workflows/ci.yml", Config())
    formatted = engine.format_string(workflow, context)

    assert formatted.index("shell: bash") < formatted.index("run: echo hi")
    assert formatted.index("working-directory:") < formatted.index(
        "run: echo hi"
    )
    assert formatted.index("uses: actions/checkout@v4") < formatted.index(
        "ref: main"
    )


def test_strategy_before_uses_in_job(engine):
    workflow = """name: ci
jobs:
  fan_out:
    uses: ./x.yml
    with:
      env-name: prod
    strategy:
      matrix:
        region: [eu, us]
"""
    context = Context(
        ".github/workflows/ci.yml", Config({"caller_inputs": "ignore"})
    )
    formatted = engine.format_string(workflow, context)
    assert formatted.index("strategy:") < formatted.index("uses: ./x.yml")
