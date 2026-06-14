# gh-formatter

[![CI](https://github.com/nimpsch/gh-formatter/actions/workflows/ci.yml/badge.svg)](https://github.com/nimpsch/gh-formatter/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/gh-formatter.svg)](https://pypi.org/project/gh-formatter/)
[![Python versions](https://img.shields.io/pypi/pyversions/gh-formatter.svg)](https://pypi.org/project/gh-formatter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A powerful and customizable formatting tool for GitHub Actions and Workflows. Automatically format and lint your workflow YAML files with consistent style, naming conventions, and structure.

## Features

- **Automatic Formatting**: Format GitHub Actions (`action.yml`/`action.yaml`) and Workflow files (`.github/workflows/*.yml/yaml`)
- **Customizable Rules**: Apply custom formatting rules including:
  - Key ordering
  - List style standardization
  - List indentation
  - Quote style normalization (single/double)
  - Name capitalization
  - Job naming conventions
  - Input naming conventions
  - Custom style rules
- **Multiple Modes**:
  - `format`: Format files in-place
  - `--check`: Dry-run mode to verify formatting without making changes
  - `--diff`: Show unified diff of what would be changed
- **Custom Configuration**: Support for custom configuration files to enforce your team's style guide
- **Inline Disable Directives**: Exempt a whole file, a region, or a single line with `# gh-formatter:disable[-file|-line]` / `:enable`
- **Recursive Discovery**: Automatically finds all workflow and action files in your project

## Installation

### From PyPI

```bash
pip install gh-formatter
```

### From Source

```bash
git clone https://github.com/nimpsch/gh-formatter.git
cd gh-formatter
pip install -e .
```

### Use as a pre-commit hook

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
- repo: https://github.com/nimpsch/gh-formatter
  rev: v0.1.0  # use the latest release tag
  hooks:
  - id: gh-formatter
```

### Requirements

- Python 3.11 or higher
- `ruamel.yaml >= 0.17.21`

## Usage

### Basic Formatting

Format a single file:

```bash
gh-formatter .github/workflows/main.yml
```

Format all workflows in a directory:

```bash
gh-formatter .github/workflows/
```

Format the entire project (will find all actions and workflows):

```bash
gh-formatter .
```

### Check Mode (Dry Run)

Check if files need formatting without modifying them:

```bash
gh-formatter --check .github/workflows/
```

Exit code will be 1 if any files need formatting, 0 if all are already formatted.

### Show Differences

See what changes would be made:

```bash
gh-formatter --diff .github/workflows/
```

Displays a unified diff for each file that would be changed.

### Custom Configuration

Use a custom configuration file:

```bash
gh-formatter --config my-config.yml .github/workflows/
```

### Listing Rules

See every available rule and post-processor (and its id, used for toggling):

```bash
gh-formatter --list-rules
```

## Disabling formatting with inline directives

Sometimes a file (or a few lines) is formatted intentionally and you want
gh-formatter to leave it alone. Add a YAML comment directive (yamllint-style):

| Directive | Effect |
|-----------|--------|
| `# gh-formatter:disable-file` | Skip the entire file. |
| `# gh-formatter:disable` … `# gh-formatter:enable` | Skip every line in the region between the two directives. |
| `# gh-formatter:disable-line` | Skip the line the directive trails, or — when it sits on its own line — the next line. |

```yaml
# gh-formatter:disable-file   # nothing in this file is touched

name: ci
on: push
jobs:
  # gh-formatter:disable
  keepThisExactly:        # name, order and quotes are all preserved
    runs-on: ubuntu-latest
  # gh-formatter:enable

  normal_job:             # formatted normally
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo hi
        legacyInput: x    # gh-formatter:disable-line  (left untouched)
```

A disabled key/step/region is exempt from every rule: renaming, key
ordering, name capitalization, list style, quote normalization, and
whitespace cleanup. Renames are also suppressed across files, so a frozen
reusable-workflow input is not rewritten in its callers.

Because gh-formatter parses and re-emits the document, the **base
indentation still applies** even inside a disabled region — directives turn
off the content rules, not the YAML serializer.

## Configuration

Configuration is read from `.gh-formatter.yml`, `.gh-formatter.yaml`, or the
`[tool.gh-formatter]` table in `pyproject.toml` (searched in that order), or
from an explicit `--config` path. All options are optional; defaults shown:

```yaml
# Indentation
indent: 2            # general mapping indentation
sequence_indent: 4   # indentation of list item content
sequence_offset: 2   # indentation of the list dash (must be < sequence_indent)
                     # default indents list items one level under their key:
                     #   steps:
                     #     - name: ...

# Naming conventions ("dash-case" or "snake_case")
input_casing: dash-case
job_casing: snake_case
# true keeps env-var style names uppercase (SERVER-IMAGE -> SERVER_IMAGE);
# false (default) renames them like any other name
preserve_uppercase_names: false

# Line endings: "preserve" (default) or "lf"
line_endings: preserve

# Quote style for already-quoted scalars: "double" (default), "single",
# or "preserve". Plain unquoted values are never force-quoted.
quote_style: double

# Let a yamllint config drive indentation (see "Using with yamllint").
# false (default), true (auto-discover .yamllint*), or an explicit path.
defer_to_yamllint: false

# Trigger filter lists under `on:` (branches, tags, paths, ...)
list_style: block    # "block" (- a) or "flow" ([a, b])
list_keys:           # which keys under `on:` are treated as filter lists
  - branches
  - branches-ignore
  - tags
  - tags-ignore
  - paths
  - paths-ignore
  - types
  - workflows

# Blank lines
blank_line_between_steps: true
blank_line_between_jobs: true

# Key ordering (unlisted keys keep their relative order at the end)
key_order_workflow: [name, run-name, on, concurrency, permissions, env, defaults, jobs]
key_order_action: [name, description, author, inputs, outputs, runs, branding]
key_order_job: [name, if, needs, runs-on, uses, with, secrets, permissions,
                environment, concurrency, strategy, container, services,
                outputs, env, defaults, timeout-minutes, continue-on-error,
                steps]
key_order_step: [name, id, uses, run, with, env, timeout-minutes,
                 continue-on-error, if, shell, working-directory]

# Disable individual rules by id (see `gh-formatter --list-rules`)
rules: {}
# rules:
#   capitalize-names: false
#   blank-lines: false
```

Invalid option names or values are rejected with a clear error message
(exit code 2).

### Safety guarantees

- Renames that would collide with an existing input/job name are skipped
  and reported as a warning instead of silently overwriting a definition.
- `name` keys inside `with:`/`env:` blocks (e.g. artifact names) are never
  capitalized — only workflow, job, and step display names are.
- Filter-list normalization only applies inside the `on:` section, so a
  step input that happens to be called `branches` is left alone.
- Script contents (`run: |` blocks) are never touched by blank-line
  insertion.
- Original line endings (LF/CRLF) and an explicit `---` document start
  marker are preserved.

### Cross-file rename propagation

Renaming the inputs of a *reusable workflow* (`workflow_call`) or a local
action changes its public interface. When both the definition and its
callers are part of the same run, gh-formatter updates the callers'
`with:` keys automatically for local references (`uses: ./...`):

```yaml
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123   # renamed together with the template's input
```

Two rules apply:

- Only `uses: ./...` references (same repository) are followed —
  marketplace actions (`actions/checkout@v4`) are never touched.
- A caller is only updated when its target file is part of the same run.
  Run gh-formatter on the repository root (`gh-formatter .`) so
  definitions and callers are always formatted together; formatting a
  lone template file renames its inputs without updating callers.

To opt out of input renaming entirely:

```yaml
rules:
  input-naming: false
```

## Using with yamllint

gh-formatter is a *formatter* (it rewrites files); [yamllint](https://yamllint.readthedocs.io)
is a *linter* (it reports style problems). They complement each other, but
yamllint's defaults flag a few things gh-formatter intentionally produces, so
out of the box the two would fight. This repo ships a [`.yamllint.yml`](.yamllint.yml)
that resolves the conflicts — drop the same file into your project and both
tools agree.

What the bundled config changes and why:

| yamllint rule | Setting | Reason |
|---------------|---------|--------|
| `line-length` | `disable` | gh-formatter never wraps `run:` scripts or `${{ }}` expressions, so a width cap would flag its output. |
| `document-start` | `disable` | gh-formatter preserves an existing `---` but never inserts one. |
| `truthy` | `check-keys: false` | The Actions `on:` key is read as a YAML 1.1 boolean; this stops it being flagged while still checking values. |
| `indentation` | `indent-sequences: consistent` | Matches gh-formatter's indented sequences while tolerating hand-written files that keep dashes flush. |

Run order matters: lint **after** formatting so yamllint sees the final
output.

```bash
gh-formatter .          # format first
yamllint --strict .     # then lint
```

The same ordering is wired into [CI](.github/workflows/build_and_test.yml) and
the [pre-commit hooks](.pre-commit-config.yaml).

> Tip: in your own config files (like `.gh-formatter.yml`) quote a literal
> `"on"` in a list so YAML 1.1 linters don't read it as `true`.

### Keeping the two configs in sync

The bundled `.yamllint.yml` is deliberately lenient about indentation
(`indent-sequences: consistent`), so it accepts gh-formatter's output whatever
the indent width. But if you tighten yamllint to a *specific* width — say
`indentation: {spaces: 4, indent-sequences: true}` — while gh-formatter is
still on its 2-space default, the two diverge: gh-formatter reindents to 2,
yamllint demands 4, and the project never goes green.

To make that impossible, point gh-formatter at the yamllint config and let
**yamllint win**:

```yaml
# .gh-formatter.yml
defer_to_yamllint: true          # discover .yamllint(.yml/.yaml) in the cwd
# defer_to_yamllint: path/to/.yamllint.yml   # or an explicit path
```

When enabled, gh-formatter reads the yamllint `indentation` rule and derives
its own `indent` / `sequence_indent` / `sequence_offset` from it (mapping the
`spaces` width and `indent-sequences` flag, always leaving exactly one space
after a `-` so the `hyphens` rule is happy too). yamllint becomes the single
source of truth, so the formatter can't produce output its own linter rejects.
If yamllint leaves the width as `consistent`, there is nothing concrete to
copy and gh-formatter keeps its configured indentation.

## Examples

See the `examples/` directory for sample workflow and action files:

- `workflow_example.yml`: Basic workflow example
- `reusable_workflow_example.yml`: Reusable workflow example
- `caller_workflow_example.yml`: Workflow that calls reusable workflows

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/nimpsch/gh-formatter.git
cd gh-formatter

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package in editable mode with development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Code Quality

The project uses several tools for code quality:

- **black**: Code formatting
- **ruff**: Fast Python linting
- **mypy**: Static type checking

Run all quality checks:

```bash
black src/ tests/
ruff check src/ tests/
mypy src/
pytest
```

## Project Structure

```
gh-formatter/
├── src/
│   └── gh_formatter/
│       ├── cli.py           # Command-line interface
│       ├── casing.py        # Casing conversion + safe rename planning
│       ├── config.py        # Configuration loading and validation
│       ├── context.py       # Processing context (file type, warnings)
│       ├── discovery.py     # Workflow/action file discovery
│       ├── engine.py        # Pipeline: rules -> dump -> post-processors
│       ├── postprocess.py   # Text post-processors (blank lines)
│       ├── project.py       # Cross-file rename planning
│       ├── references.py    # Expression reference rewriting
│       ├── utils.py         # ruamel.yaml round-trip helpers
│       └── rules/           # Tree formatting rules
│           ├── base.py      # Base rule class
│           ├── inputs.py    # Input naming rule
│           ├── callers.py   # Cross-file caller input renaming rule
│           ├── jobs.py      # Job naming rule
│           ├── keys.py      # Key ordering rule
│           ├── lists.py     # Trigger filter list style rule
│           ├── names.py     # Display name capitalization rule
│           └── style.py     # Whitespace/boolean style rule
├── tests/                   # Test suite
├── examples/                # Example workflow files
└── README.md               # This file
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for
development setup, the project layout, how to add a new rule, and the pull
request process. By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

To report a bug or request a feature, open an issue using the provided
templates. For security issues, see [SECURITY.md](SECURITY.md).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Sebastian Nimpsch
