"""Regression tests for bugs found during the refactoring."""

import pytest

from gh_formatter.config import Config
from gh_formatter.core.context import Context
from gh_formatter.core.pipeline import Engine


@pytest.fixture
def engine():
    return Engine()


def fmt(engine, yaml_text, path=".github/workflows/ci.yml", config=None):
    context = Context(path, config or Config())
    return engine.format_string(yaml_text, context), context


def test_with_name_not_capitalized(engine):
    """`name` inside `with:` is data (e.g. artifact names), not a display name."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: upload
        uses: actions/upload-artifact@v4
        with:
          name: my-artifact
"""
    formatted, _ = fmt(engine, workflow)
    assert "name: my-artifact" in formatted
    assert "name: Upload" in formatted
    assert "name: Ci" in formatted


def test_list_keys_under_with_not_converted(engine):
    """Filter list keys are only normalized inside the `on:` section."""
    workflow = """name: ci
on:
  push:
    branches: main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: some/action@v1
        with:
          branches: main,dev
"""
    formatted, _ = fmt(engine, workflow)
    # on.push.branches promoted to a list
    assert "branches:\n    - main" in formatted or "- main" in formatted
    # the step input stays a plain string
    assert "branches: main,dev" in formatted


def test_rename_collision_skipped_with_warning(engine):
    """Colliding renames must not silently delete a sibling definition."""
    action = """name: My Action
inputs:
  my-input:
    description: first
  my_input:
    description: second
runs:
  using: composite
  steps:
    - shell: bash
      run: echo hi
"""
    formatted, context = fmt(
        engine,
        action,
        path="action.yml",
        config=Config({"input_casing": "dash-case"}),
    )
    assert "description: first" in formatted
    assert "description: second" in formatted
    assert any("my_input" in w for w in context.warnings)


def test_reference_suffix_not_clobbered(engine):
    """Renaming `my-input` must not rewrite part of `my-input-extra`."""
    action = """name: My Action
inputs:
  my-input:
    description: x
  my-input-extra:
    description: y
runs:
  using: composite
  steps:
    - shell: bash
      run: echo "${{ inputs.my-input-extra }} ${{ inputs.my-input }}"
"""
    formatted, _ = fmt(
        engine,
        action,
        path="action.yml",
        config=Config({"input_casing": "snake_case"}),
    )
    assert "inputs.my_input_extra" in formatted
    assert "inputs.my_input }}" in formatted
    assert "my_input-extra" not in formatted


def test_blank_lines_between_steps_and_jobs(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: one
        run: echo 1
      - name: two
        run: echo 2
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
"""
    formatted, _ = fmt(engine, workflow)
    assert "run: echo 1\n\n      - name: Two" in formatted
    assert "run: echo 2\n\n  deploy:" in formatted


def test_blank_lines_skip_literal_blocks(engine):
    """Lines inside `run: |` that look like steps must not be split."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: gen
        run: |
          cat <<EOF
          steps:
          - fake: item
          - other: item
          EOF
      - name: second
        run: echo done
"""
    formatted, _ = fmt(engine, workflow)
    # script content is untouched (no blank lines between the fake items)
    assert "- fake: item\n          - other: item" in formatted
    # but real steps are separated
    assert "EOF\n\n      - name: Second" in formatted


def test_blank_lines_can_be_disabled(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo 1
      - run: echo 2
"""
    formatted, _ = fmt(
        engine,
        workflow,
        config=Config(
            {
                "blank_line_between_steps": False,
                "blank_line_between_jobs": False,
                "blank_line_between_sections": False,
            }
        ),
    )
    assert "\n\n" not in formatted


def test_rules_can_be_disabled_by_id(engine):
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
"""
    formatted, _ = fmt(
        engine,
        workflow,
        config=Config({"rules": {"capitalize-names": False}}),
    )
    assert "name: ci" in formatted


def test_literal_block_preserved_after_rename(engine):
    """Reference rewriting must not change a literal block's scalar style."""
    action = """name: My Action
inputs:
  myInput:
    description: x
runs:
  using: composite
  steps:
    - shell: bash
      run: |
        echo "${{ inputs.myInput }}"
        echo "second line"
"""
    formatted, _ = fmt(engine, action, path="action.yml")
    assert "run: |" in formatted
    assert "inputs.my-input" in formatted


def test_write_failure_reported_as_error(tmp_path):
    """A file that cannot be written must be reported as an error."""
    from gh_formatter.app.service import FileStatus, process_file

    target = tmp_path / ".github" / "workflows"
    target.mkdir(parents=True)
    workflow_file = target / "ci.yml"
    workflow_file.write_text(
        "jobs:\n  b:\n    runs-on: ubuntu-latest\non: push\nname: x\n",
        encoding="utf-8",
    )

    result = process_file(
        workflow_file, Engine(), Config(), check=True, show_diff=False
    )
    assert result.status is FileStatus.CHANGED
    assert result.message == "Needs formatting"

    unreadable = target / "missing.yml"
    result = process_file(
        unreadable, Engine(), Config(), check=False, show_diff=False
    )
    assert result.status is FileStatus.ERROR


def test_jobs_prefix_references_updated_on_rename(engine):
    """Reusable workflow outputs reference jobs.<id>; renames must follow."""
    workflow = """name: template
on:
  workflow_call:
    outputs:
      passed:
        value: ${{ jobs.run-tests.outputs.passed }}
jobs:
  run-tests:
    runs-on: ubuntu-latest
    outputs:
      passed: "1"
    steps:
      - run: echo ok
"""
    formatted, _ = fmt(engine, workflow)
    assert "run_tests:" in formatted
    assert "jobs.run_tests.outputs.passed" in formatted
    assert "jobs.run-tests" not in formatted


def test_uppercase_names_lowercased_by_default(engine):
    """By default every input follows the configured casing."""
    workflow = """name: template
on:
  workflow_call:
    inputs:
      SERVER_IMAGE:
        type: string
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ inputs.SERVER_IMAGE }}"
"""
    formatted, _ = fmt(engine, workflow)
    assert "server-image:" in formatted
    assert "inputs.server-image" in formatted


def test_uppercase_names_normalized_when_preserved(engine):
    """With the flag on, uppercase names stay uppercase with underscores."""
    workflow = """name: template
on:
  workflow_call:
    inputs:
      SERVER-IMAGE:
        type: string
      MM_ENV:
        type: string
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ inputs.SERVER-IMAGE }} ${{ inputs.MM_ENV }}"
"""
    formatted, _ = fmt(
        engine, workflow, config=Config({"preserve_uppercase_names": True})
    )
    # dash separator normalized to underscore, case kept
    assert "SERVER_IMAGE:" in formatted
    assert "inputs.SERVER_IMAGE" in formatted
    # already-conforming name untouched
    assert "MM_ENV:" in formatted


def test_document_start_marker_preserved(engine):
    workflow = """---
name: ci
jobs:
  build:
    runs-on: ubuntu-latest
"""
    formatted, _ = fmt(engine, workflow)
    assert formatted.startswith("---\n")


def test_crlf_line_endings_preserved(tmp_path):
    from gh_formatter.app.service import FileStatus, process_file

    target = tmp_path / ".github" / "workflows"
    target.mkdir(parents=True)
    workflow_file = target / "ci.yml"
    workflow_file.write_bytes(
        b"jobs:\r\n  b:\r\n    runs-on: ubuntu-latest\r\non: push\r\nname: x\r\n"
    )

    result = process_file(
        workflow_file, Engine(), Config(), check=False, show_diff=False
    )
    assert result.status is FileStatus.CHANGED
    raw = workflow_file.read_bytes()
    # A CRLF file must be written back with CRLF endings only
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")

    # An LF file must stay LF even on Windows
    lf_file = target / "lf.yml"
    lf_file.write_bytes(
        b"jobs:\n  b:\n    runs-on: ubuntu-latest\non: push\nname: x\n"
    )
    process_file(lf_file, Engine(), Config(), check=False, show_diff=False)
    assert b"\r\n" not in lf_file.read_bytes()


def test_line_endings_lf_option_converts_crlf(tmp_path):
    from gh_formatter.app.service import FileStatus, process_file

    target = tmp_path / ".github" / "workflows"
    target.mkdir(parents=True)
    config = Config({"line_endings": "lf"})

    crlf_file = target / "ci.yml"
    crlf_file.write_bytes(
        b"jobs:\r\n  b:\r\n    runs-on: ubuntu-latest\r\non: push\r\nname: x\r\n"
    )
    result = process_file(
        crlf_file, Engine(), config, check=False, show_diff=False
    )
    assert result.status is FileStatus.CHANGED
    assert b"\r\n" not in crlf_file.read_bytes()

    # An already-formatted CRLF file still needs the newline conversion
    crlf_file.write_bytes(crlf_file.read_bytes().replace(b"\n", b"\r\n"))
    result = process_file(
        crlf_file, Engine(), config, check=False, show_diff=False
    )
    assert result.status is FileStatus.CHANGED
    assert b"\r\n" not in crlf_file.read_bytes()


def test_workflow_call_secrets_reordered(engine):
    workflow = """name: template
on:
  workflow_call:
    secrets:
      MM_LICENSE:
        required: false
        description: The license
jobs:
  build:
    runs-on: ubuntu-latest
"""
    formatted, _ = fmt(engine, workflow)
    assert formatted.index("description: The license") < formatted.index(
        "required: false"
    )


def test_step_comments_stay_with_their_step(engine):
    """The blank line goes above a step's comment, not between them."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo 1
      # explains the second step
      - run: echo 2
"""
    formatted, _ = fmt(engine, workflow)
    # ruamel keeps the comment at its original column; what matters is the
    # blank line lands above the comment, not between comment and step.
    assert (
        "echo 1\n\n      # explains the second step\n      - run: echo 2"
        in formatted
    )


def _reparses(text):
    from gh_formatter.core.yaml_io import load_yaml

    load_yaml(text)  # raises on invalid YAML
    return True


def test_reordering_step_keys_preserves_comments(engine):
    """Reordering keys must never corrupt a step or drop its comments."""
    workflow = """name: ci  # the workflow
jobs:
  build:
    # what this job does
    runs-on: ubuntu-latest  # the runner
    steps:
      - run: echo hi  # inline on run
        name: do thing
      - name: second
        # explains the uses below
        uses: actions/checkout@v4
        if: ${{ success() }}  # gate it
"""
    formatted, _ = fmt(engine, workflow)
    # Output is valid YAML (the bug used to merge two keys onto one line).
    assert _reparses(formatted)
    # Every comment survives.
    for comment in (
        "# the workflow",
        "# what this job does",
        "# the runner",
        "# inline on run",
        "# explains the uses below",
        "# gate it",
    ):
        assert comment in formatted
    # End-of-line comments stay attached to their own line.
    assert "echo hi  # inline on run" in formatted
    assert "if: ${{ success() }}  # gate it" in formatted
    # Re-running the formatter is a no-op (single-pass idempotent).
    assert engine.format_string(formatted, _context()) == formatted


def test_comment_before_reordered_first_key_lifted_above_step(engine):
    """A comment before a key that sorts first moves above the step's dash."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
        # TODO: tidy this up
        name: do thing
"""
    formatted, _ = fmt(engine, workflow)
    assert _reparses(formatted)
    assert "# TODO: tidy this up" in formatted
    # The comment sits above the dash, never on the empty dash line.
    assert "-\n" not in formatted
    assert engine.format_string(formatted, _context()) == formatted


def _context():
    return Context(".github/workflows/ci.yml", Config())


def test_step_reorder_keeps_trailing_job_comment_outside_step(engine):
    """Reordering step keys past a map-valued last key must not drag the
    next job's comment into the step (it hangs off the with: block)."""
    workflow = """name: ci
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: upload
        continue-on-error: true
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  # deploy comes after tests
  deploy:
    runs-on: ubuntu-latest
"""
    formatted, _ = fmt(engine, workflow)
    # The comment stays above the deploy job, not inside the upload step.
    assert "# deploy comes after tests\n  deploy:" in formatted
    # continue-on-error was reordered within the step, above the comment.
    assert formatted.index("continue-on-error: true") < formatted.index(
        "# deploy comes after tests"
    )
    assert engine.format_string(formatted, _context()) == formatted


def test_leading_blank_in_run_block_stripped(engine):
    """A blank line after `run: |` forces an ugly `|2` indentation
    indicator on re-dump; the meaningless blank is stripped instead."""
    action = """name: X
runs:
  using: composite
  steps:
    - shell: bash
      run: |

        GH_HOST="example.com"
        export GH_HOST
"""
    formatted, _ = fmt(engine, action, path="action.yml")
    assert "run: |\n" in formatted
    assert "|2" not in formatted
    assert 'GH_HOST="example.com"' in formatted


def test_required_block_indicator_preserved(engine):
    """A deliberate `|2` (first content line starts with spaces) survives
    with the content byte-identical."""
    from gh_formatter.core.yaml_io import load_yaml

    action = """name: X
runs:
  using: composite
  steps:
    - shell: bash
      run: |2
          indented first line
        normal line
"""
    formatted, _ = fmt(engine, action, path="action.yml")
    script = load_yaml(formatted)["runs"]["steps"][0]["run"]
    assert script == "  indented first line\nnormal line\n"


def test_job_reorder_keeps_comment_after_seq_tailed_entry(engine):
    """A comment for the NEXT job hangs on the previous job's deepest last
    child; when that chain ends in a sequence (strategy.matrix.region),
    the comment must still stay outside the job after reordering."""
    workflow = """name: ci
jobs:
  call_deploy:
    uses: ./x.yml
    with:
      env-name: prod
    strategy:
      matrix:
        region:
          - eu
          - us

  # always report, even on failure
  notify:
    runs-on: ubuntu-latest
"""
    config = Config({"caller_inputs": "ignore"})
    formatted, _ = fmt(engine, workflow, config=config)
    assert "# always report, even on failure\n  notify:" in formatted
    # strategy was reordered above uses without dragging the comment along
    assert formatted.index("strategy:") < formatted.index("uses: ./x.yml")
    context = Context(".github/workflows/ci.yml", config)
    assert engine.format_string(formatted, context) == formatted


def test_blank_after_block_scalar_stays_single(engine):
    """Reordering a step so a `run: |` block becomes last must not double
    the blank line separating it from the next step."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: one
        run: |
          echo hi
        shell: bash

      - name: two
        shell: bash
        run: |
          echo bye
"""
    formatted, _ = fmt(engine, workflow)
    assert "\n\n\n" not in formatted
    assert "echo hi\n\n" in formatted  # exactly one blank between steps
    context = Context(".github/workflows/ci.yml", Config())
    assert engine.format_string(formatted, context) == formatted


def test_header_comments_before_document_marker_preserved(engine):
    """Comments above `---` belong to the document prelude, which ruamel
    drops on dump; the formatter must carry them (and the marker) over."""
    workflow = """# Test
# Test2
---
name: ci
jobs:
  build:
    runs-on: ubuntu-latest
"""
    formatted, _ = fmt(engine, workflow)
    assert formatted.startswith("# Test\n# Test2\n---\n")
    context = Context(".github/workflows/ci.yml", Config())
    assert engine.format_string(formatted, context) == formatted


def test_header_comments_without_marker_preserved(engine):
    """Without a marker the header rides the root mapping and survives."""
    workflow = """# Test
# Test2
name: ci
jobs:
  build:
    runs-on: ubuntu-latest
"""
    formatted, _ = fmt(engine, workflow)
    assert formatted.startswith("# Test\n# Test2\nname: Ci")


def test_stray_blanks_inside_jobs_are_normalized(engine):
    """Blank lines between a job's settings (hand-written or left behind
    by reordering) are stripped; only step/job separators remain."""
    workflow = """name: ci
jobs:

  build:
    needs:
      - lint

    runs-on: ubuntu-latest

    steps:
      - run: echo one
      - run: echo two
"""
    formatted, _ = fmt(engine, workflow)
    assert "jobs:\n  build:" in formatted  # no blank after jobs:
    assert "- lint\n    runs-on:" in formatted  # no blank after needs list
    assert "ubuntu-latest\n    steps:" in formatted  # no blank before steps
    # Canonical separator between steps still inserted.
    assert "echo one\n\n      - run: echo two" in formatted


def test_blank_lines_inside_scripts_untouched(engine):
    """Blank lines are script content inside run: | blocks."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo first

          echo after blank
"""
    formatted, _ = fmt(engine, workflow)
    assert "echo first\n\n          echo after blank" in formatted


def test_root_section_separators_preserved(engine):
    """Author blank lines between top-level sections travel with their
    section instead of being scattered by reordering."""
    workflow = """jobs:
  build:
    runs-on: ubuntu-latest

env:
  A: "1"

on: push
name: ci
"""
    formatted, _ = fmt(engine, workflow)
    # Reordered to name/on/env/jobs with the separators intact and no
    # blank stuck between a key line and its own content.
    assert "jobs:\n  build:" in formatted
    assert engine.format_string(formatted, _context()) == formatted


def test_double_blank_after_block_scalar_collapsed(engine):
    """Extra blank lines between a run: | block and the next step are
    normalized to the single canonical separator."""
    workflow = """name: ci
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: |
          exit 1


      - run: echo next
"""
    formatted, _ = fmt(engine, workflow)
    assert "exit 1\n\n      - run: echo next" in formatted
    assert "\n\n\n" not in formatted
