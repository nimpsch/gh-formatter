from gh_formatter.config import Config
from gh_formatter.core.pipeline import Engine
from gh_formatter.lsp.core import diagnostic_to_lsp_range, run_pipeline


def test_run_pipeline_formats_valid_yaml():
    workflow = """
jobs:
  build:
    runs-on: ubuntu-latest
on: push
name: ci
"""
    outcome = run_pipeline(
        Engine(), workflow, ".github/workflows/ci.yml", Config()
    )
    assert outcome.parse_error is None
    assert outcome.formatted_text is not None
    assert outcome.formatted_text.index("name:") < outcome.formatted_text.index(
        "on:"
    )


def test_run_pipeline_reports_parse_error_location():
    # An unclosed flow sequence: the parser reports the problem at the
    # start of "jobs:" (line 5, column 5), 1-based.
    invalid = """name: ci
on:
  push:
    branches: [main
jobs:
  build:
    runs-on: ubuntu-latest
"""
    outcome = run_pipeline(Engine(), invalid, "ci.yml", Config())
    assert outcome.formatted_text is None
    assert outcome.parse_error is not None
    assert (outcome.parse_error.line, outcome.parse_error.column) == (5, 5)
    assert "expected" in outcome.parse_error.message


def test_run_pipeline_collects_lint_diagnostics():
    # A rename collision is reported as a warning (core/casing.py), located
    # at the colliding key -- "  my_input:" is line 5, column 3.
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
    config = Config({"input_casing": "dash-case"})
    outcome = run_pipeline(Engine(), action, "action.yml", config)
    assert outcome.parse_error is None
    diag = next(d for d in outcome.diagnostics if "my_input" in d.message)
    assert (diag.line, diag.column) == (5, 3)


def test_diagnostic_to_lsp_range_extends_to_end_of_line():
    lines = ["name: ci", "  my_input: x", "type: string"]
    start, end = diagnostic_to_lsp_range(2, 3, lines)
    assert start == (1, 2)
    assert end == (1, len(lines[1]))


def test_diagnostic_to_lsp_range_falls_back_without_location():
    assert diagnostic_to_lsp_range(None, None, ["anything"]) == ((0, 0), (0, 1))


def test_diagnostic_to_lsp_range_falls_back_out_of_bounds():
    assert diagnostic_to_lsp_range(99, 1, ["only one line"]) == ((0, 0), (0, 1))
