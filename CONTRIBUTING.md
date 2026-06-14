# Contributing to gh-formatter

Thanks for your interest in improving gh-formatter! This document explains
how to set up the project, the conventions we follow, and how to get your
changes merged.

## Table of contents

- [Code of conduct](#code-of-conduct)
- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Running the checks](#running-the-checks)
- [Project layout](#project-layout)
- [Adding a new rule](#adding-a-new-rule)
- [Coding conventions](#coding-conventions)
- [Commit messages](#commit-messages)
- [Opening a pull request](#opening-a-pull-request)
- [Reporting bugs and requesting features](#reporting-bugs-and-requesting-features)

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you are expected to uphold it. Please report unacceptable
behavior to the maintainers.

## Ways to contribute

- **Report a bug** — open an issue using the *Bug report* template.
- **Suggest a feature** — open an issue using the *Feature request* template.
- **Improve docs** — typo fixes and clarifications are very welcome.
- **Submit code** — fix a bug, add a rule, or add a configuration option.

If you are planning a larger change, please open an issue first so we can
agree on the approach before you invest a lot of time.

## Development setup

You need **Python 3.11 or newer**.

```bash
# Fork and clone, then:
cd gh_formatter

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install the package in editable mode with the dev dependencies
pip install -e ".[dev]"
```

## Running the checks

All four checks below run in CI and must pass before a PR can be merged.
Run them locally before pushing:

```bash
black --check src/ tests/     # formatting (drop --check to auto-format)
ruff check src/ tests/        # linting
mypy src/                     # static type checking (strict)
pytest                        # tests
```

A change is not complete until it has tests. Bug fixes should include a
regression test that fails before the fix; new features need tests for the
new behavior and its edge cases.

## Project layout

```
src/gh_formatter/
  cli.py          # argument parsing + orchestration
  config.py       # configuration loading and validation
  context.py      # per-file context (file type, warnings, project plan)
  discovery.py    # workflow/action file discovery
  engine.py       # pipeline: tree rules -> dump -> post-processors
  postprocess.py  # text post-processors (blank lines)
  project.py      # cross-file rename planning
  references.py   # expression reference rewriting
  casing.py       # casing conversion + safe rename planning
  utils.py        # ruamel.yaml round-trip helpers (the ONLY place that
                  #   touches ruamel internals)
  rules/          # one BaseRule subclass per formatting concern
```

The engine runs in two stages: **tree rules** (`BaseRule`) transform the
parsed YAML, then **post-processors** (`BasePostProcessor`) adjust the
serialized text. Anything that can be expressed on the parse tree should be
a rule; only purely presentational concerns (like blank lines) belong in a
post-processor.

## Adding a new rule

1. Create a module in `src/gh_formatter/rules/` with a class that subclasses
   `BaseRule`. Implement `id`, `description`, `should_run`, and `apply`.
2. Register it in `default_rules()` in `engine.py` (order matters — rules
   run top to bottom).
3. If the rule has options, add them to `DEFAULT_CONFIG` in `config.py`
   **with validation** in `Config.__init__`, and document them in
   `.gh-formatter.yml` and the README.
4. Keep all ruamel.yaml-specific logic in `utils.py` — rules should use the
   helpers there rather than touching `.ca`, `.lc`, or scalar style classes
   directly.
5. Add tests covering the rule and at least one edge case.

Every rule can be disabled by its `id` via the `rules:` config block, so
pick a clear, kebab-case id. Run `gh-formatter --list-rules` to see the
registered ids.

## Coding conventions

- Formatting and linting are enforced by **black** and **ruff** (config in
  `pyproject.toml`); the line length is 80.
- Public functions, classes, and methods should have docstrings (Google
  style). Comments explain *why*, not *what*.
- Full type annotations are required — `mypy --strict` must pass.
- Be careful with comment and quote-style preservation: gh-formatter's value
  is that it does **not** mangle files. When in doubt, add a round-trip test.

## Commit messages

Use clear, imperative commit subjects ("Add ...", "Fix ...", not "Added" or
"Fixes"). A short body explaining the motivation is appreciated for anything
non-trivial. We squash-merge most PRs, so the PR title becomes the final
commit subject — keep it descriptive.

## Opening a pull request

1. Create a topic branch off `main` (`git checkout -b fix-comment-loss`).
2. Make your change with tests and run all four checks locally.
3. Update the README / `.gh-formatter.yml` if you changed behavior or options.
4. Push and open a PR using the template. Fill in *what* changed, *why*, and
   *how you tested it*. Link any related issue (`Fixes #123`).
5. Keep PRs focused — one logical change per PR is much easier to review.

CI runs the test matrix (Python 3.11–3.14), the lint/type checks, and a
package build. All must be green.

## Reporting bugs and requesting features

Open an issue using the appropriate template. For bugs, the most useful
report includes a **minimal YAML snippet**, the command you ran, what you
expected, and what gh-formatter produced instead. Reproductions make fixes
dramatically faster.
