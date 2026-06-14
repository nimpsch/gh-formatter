"""Tests for inline disable directives (whole-file, region, single line)."""

import pytest

from gh_formatter.config import Config
from gh_formatter.context import Context
from gh_formatter.directives import scan_disabled
from gh_formatter.engine import Engine


@pytest.fixture
def engine():
    return Engine()


def fmt(engine, text, path=".github/workflows/ci.yml", config=None):
    return engine.format_string(text, Context(path, config or Config()))


def test_scan_disable_file():
    disable_file, lines = scan_disabled(
        "# gh-formatter:disable-file\nname: ci\n"
    )
    assert disable_file is True
    assert lines == set()


def test_scan_region_marks_inclusive_lines():
    content = (
        "a: 1\n"  # 1
        "# gh-formatter:disable\n"  # 2
        "b: 2\n"  # 3
        "c: 3\n"  # 4
        "# gh-formatter:enable\n"  # 5
        "d: 4\n"  # 6
    )
    disable_file, lines = scan_disabled(content)
    assert disable_file is False
    assert lines == {2, 3, 4}


def test_scan_disable_line_trailing_vs_standalone():
    content = (
        "a: 1  # gh-formatter:disable-line\n"  # 1 -> itself
        "# gh-formatter:disable-line\n"  # 2 -> next content line (3)
        "b: 2\n"  # 3
    )
    _, lines = scan_disabled(content)
    assert lines == {1, 3}


def test_disable_file_leaves_content_byte_for_byte(engine):
    workflow = """# gh-formatter:disable-file
name: ci
jobs:
  myJob:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
        name: build
"""
    assert fmt(engine, workflow) == workflow


def test_disable_line_freezes_only_that_job(engine):
    workflow = """name: ci
jobs:
  myJob:  # gh-formatter:disable-line
    runs-on: ubuntu-latest
  otherJob:
    runs-on: ubuntu-latest
"""
    formatted = fmt(engine, workflow)
    assert "myJob:" in formatted  # frozen, not renamed
    assert "other_job:" in formatted  # sibling still normalized


def test_disable_region_preserves_keys_and_order(engine):
    workflow = """name: ci
jobs:
  # gh-formatter:disable
  weirdJob:
    steps:
      - run: echo hi
        name: keep me lower
  # gh-formatter:enable
  normalJob:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
        name: lower
"""
    formatted = fmt(engine, workflow)
    # Inside the region: name not capitalized, step keys not reordered.
    assert "weirdJob:" in formatted
    assert "name: keep me lower" in formatted
    assert "run: echo hi\n        name: keep me lower" in formatted
    # Outside the region: normal rules apply.
    assert "normal_job:" in formatted
    assert "name: Lower" in formatted
    assert "name: Lower\n        run: echo hi" in formatted


def test_frozen_value_keeps_quotes_and_casing(engine):
    workflow = """name: ci
on:
  workflow_call:
    inputs:
      myInput:  # gh-formatter:disable-line
        default: 'keep single'
      otherInput:
        default: 'normalize me'
jobs:
  build:
    runs-on: ubuntu-latest
"""
    formatted = fmt(engine, workflow)
    assert "myInput:" in formatted
    assert "default: 'keep single'" in formatted  # quote style preserved
    assert "other-input:" in formatted
    assert 'default: "normalize me"' in formatted  # normalized to double


def test_directives_are_idempotent(engine):
    workflow = """name: ci
jobs:
  myJob:  # gh-formatter:disable-line
    runs-on: ubuntu-latest
  # gh-formatter:disable
  weirdJob:
    steps:
      - run: echo hi
        name: keep
  # gh-formatter:enable
  normalJob:
    runs-on: ubuntu-latest
"""
    once = fmt(engine, workflow)
    assert fmt(engine, once) == once
