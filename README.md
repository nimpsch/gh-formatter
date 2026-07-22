# gh-formatter

[![CI](https://github.com/nimpsch/gh-formatter/actions/workflows/build_and_test.yml/badge.svg)](https://github.com/nimpsch/gh-formatter/actions/workflows/build_and_test.yml)
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
  - Alphabetical sorting of env/inputs/outputs/secrets/with blocks
  - Name capitalization
  - Job naming conventions
  - Input naming conventions
  - `if:` expression normalization (wraps bare conditions in `${{ }}`)
  - Custom style rules
- **Multiple Modes**:
  - `format`: Format files in-place
  - `--check`: Dry-run mode to verify formatting without making changes
  - `--diff`: Show unified diff of what would be changed
  - `--version` / `--list-rules`: Show the version or all rule ids
- **Caller Input Checking**: Errors (or auto-fixes) when a `uses: ./...` caller passes an input the local target doesn't declare
- **Custom Configuration**: Support for custom configuration files to enforce your team's style guide
- **Inline Disable Directives**: Exempt a whole file, a region, or a single line with `# gh-formatter:disable[-file|-line]` / `:enable`
- **Recursive Discovery**: Automatically finds workflow and action files in your project — see [File discovery](#file-discovery) for exactly what counts

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

A pre-commit hook only ever sees staged/changed files, so if you rename an
input in a reusable workflow or local action in one commit and its callers
aren't touched in that same commit, they won't be fixed until they're next
staged themselves (gh-formatter still checks them correctly against the
current interface whenever that happens — see
[Cross-file input consistency](#cross-file-input-consistency) — it just
won't rewrite a file it wasn't asked to rewrite). Also run
`gh-formatter --check .` over the whole repository periodically or in CI
(this project does exactly that in its own
[pre-commit config](.pre-commit-config.yaml)) as the safety net that catches
any caller left stale by an incremental, hook-only run.

### Requirements

- Python 3.11 or higher
- `ruamel.yaml >= 0.19.1`

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

### File discovery

When given a **directory**, gh-formatter walks it and only touches:

- YAML files placed directly in a `.github/workflows/` directory — the same
  place GitHub itself reads workflows from. A sibling directory whose name
  merely starts with `workflows` (e.g. `.github/workflows-templates/`) does
  not count, and neither does a subdirectory nested *below*
  `.github/workflows/` — GitHub ignores both, so gh-formatter does too.
  This mirrors how actionlint locates workflow files.
- `action.yml` / `action.yaml`, anywhere in the project — a repository can
  publish an action from its root or from any subdirectory (`.github/actions/*/action.yml`
  is a common layout, but not the only valid one), so these are matched by
  filename rather than by location.

Common dependency/build directories (`.git`, `.venv`, `venv`,
`node_modules`, `__pycache__`, `.pytest_cache`, `build`, `dist`) are always
skipped during the walk.

A **file** passed directly as an argument is always processed, regardless
of its name or location — the same as pointing any formatter at an
explicit path. This is how this project's own CI formats its `examples/`
directory even though those files live outside `.github/workflows/`.

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
# or "preserve". Plain unquoted values are never force-quoted, and a value
# containing the configured quote char uses the opposite one instead of
# escaping ('say "hi"' rather than "say \"hi\"").
quote_style: double

# Caller with:-keys vs a LOCAL target's declared inputs (see "Caller input
# checking"): "error" (default) fails the run, "fix" renames, "ignore" skips.
caller_inputs: error
# Require callers to pass every declared input/secret of a LOCAL target,
# optional ones included ("secrets: inherit" counts). Needs caller_inputs.
require_explicit_inputs: true

# Let a yamllint config drive indentation (see "Using with yamllint").
# false (default), true (auto-discover .yamllint*), or an explicit path.
defer_to_yamllint: false

# Mapping blocks sorted alphabetically (case-insensitive); [] disables.
alphabetize: [env, inputs, outputs, secrets, with]

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

# Blank lines are normalized per scope: each flag keeps exactly one blank
# between that scope's siblings and removes stray blanks inside a sibling's
# body (see "Blank-line normalization"). A false flag leaves that scope as-is.
blank_line_between_steps: true      # between steps; none within a step
blank_line_between_jobs: true       # between jobs; none within a job body
blank_line_between_sections: true   # between top-level sections; none within

# Key ordering (unlisted keys keep their relative order at the end)
key_order_workflow: [name, run-name, on, concurrency, permissions, env, defaults, jobs]
key_order_action: [name, description, author, inputs, outputs, runs, branding]
key_order_job: [name, if, needs, runs-on, env, strategy, uses, with, secrets,
                permissions, environment, concurrency, container, services,
                outputs, defaults, timeout-minutes, continue-on-error, steps]
key_order_step: [name, id, if, env, uses, continue-on-error,
                 working-directory, shell, timeout-minutes, run, with]

# Disable individual rules by id (see `gh-formatter --list-rules`)
rules: {}
# rules:
#   capitalize-names: false
#   blank-lines: false
```

Invalid option names or values are rejected with a clear error message
(exit code 2).

### Blank-line normalization

Blank lines carry no meaning except as separators between siblings, so the
formatter normalizes them rather than only inserting them. There are three
scopes, each toggled by its own flag:

| Scope | Flag | Siblings |
|-------|------|----------|
| Steps | `blank_line_between_steps` | consecutive steps in a `steps:` list |
| Jobs | `blank_line_between_jobs` | job definitions under `jobs:` |
| Sections | `blank_line_between_sections` | top-level keys (`name`, `on`, `env`, `jobs`, ... / an action's `name`, `inputs`, `runs`, ...) |

Within an enabled scope the formatter keeps **exactly one** blank line
between siblings and removes **stray** blanks inside a sibling's body —
whether you wrote them by hand or they were left behind when keys were
reordered. "Inside a sibling's body" includes blanks nested arbitrarily
deep: for example, a blank line between two triggers under `on:`, or
between two entries of a `permissions:` block, is removed, because those
are section-body blanks, not separators between top-level sections. A blank
between two consecutive `run:` script lines is **not** touched — script
contents are always preserved verbatim.

Setting a scope's flag to `false` disables normalization for that scope
only: those blank lines are left exactly as written (neither inserted nor
removed), while the other scopes still normalize.

### Safety guarantees

- Renames that would collide with an existing input/job name are skipped
  and reported as a warning instead of silently overwriting a definition.
- `name` keys inside `with:`/`env:` blocks (e.g. artifact names) are never
  capitalized — only workflow, job, and step display names are.
- Filter-list normalization only applies inside the `on:` section, so a
  step input that happens to be called `branches` is left alone.
- Script contents (`run: |` blocks) are never touched by blank-line
  normalization — blank lines inside a script are preserved verbatim.
- Original line endings (LF/CRLF) and an explicit `---` document start
  marker are preserved.

### Cross-file input consistency

Renaming the inputs of a *reusable workflow* (`workflow_call`) or a local
action changes its public interface, so callers referencing it via
`uses: ./...` can fall out of sync. gh-formatter checks each caller's `with:`
keys against the local target's declared inputs and, by default, **errors**
on a mismatch so you fix both files (see
[Caller input checking](#caller-input-checking) for the `error` / `fix` /
`ignore` modes).

With `caller_inputs: fix`, gh-formatter instead renames the caller's keys to
match:

```yaml
jobs:
  call_template:
    uses: ./.github/workflows/template.yml
    with:
      commit-sha: abc123   # fixed to match the template's input
```

Either way, gh-formatter resolves a `uses: ./...` target by scanning every
workflow/action file in the caller's repository, not just the files passed
on the command line — so this works even when only the caller itself is
being formatted (e.g. a pre-commit hook that only sees staged files). Only
files it cannot place in any repository, and marketplace actions
(`actions/checkout@v4`), are left unchecked. Note that only the files you
actually pass get *written*: fixing a caller doesn't rewrite its target, and
vice versa — pass both (or run on the repo root) to update them together in
one pass.

To turn off input renaming of definitions entirely:

```yaml
rules:
  input-naming: false
```

### Caller input checking

When a caller passes a `with:` key that the local target does not declare —
typically a casing or rename that drifted between the two files — gh-formatter
acts according to the `caller_inputs` option. Only local references
(`uses: ./...`) are considered, resolved against every workflow/action file
in the caller's repository regardless of which files were passed on the
command line; marketplace actions (`actions/checkout@v4`) are never checked.

```yaml
# .gh-formatter.yml
caller_inputs: error   # error (default) | fix | ignore
```

| Mode | Behavior |
|------|----------|
| `error` (default) | Report the mismatch as an **error** and fail the run, like a linter. You fix it in both files. |
| `fix` | Rename the caller's key to the matching declared input (at your own risk). |
| `ignore` | Leave caller inputs alone. |

In `error` mode the message points at the offending key and the likely fix:

```text
[error] caller.yml - with: input 'commitSha' is not declared by local target
        './.github/workflows/template.yml' (did you mean 'commit-sha'?) - fix it in both files
```

Errors fail the run (non-zero exit) so CI catches the drift; run
`gh-formatter --check .` in CI. Use `fix` to let gh-formatter rename caller
keys for you, or `ignore` to turn the check off.

With `require_explicit_inputs: true` (the default) callers must also pass
**every** input and secret the local target declares — optional ones with
defaults included — so each call site documents the full interface.
`secrets:` blocks are checked the same way as `with:`, and
`secrets: inherit` counts as passing them all. Set the option to `false`
to allow relying on defaults.

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
- `codeql.yml`: CodeQL security scanning workflow
- `docker-publish.yml`: Docker build-and-publish workflow
- `composite_action/action.yml`: Composite action example
- `long_workflow.yml`: Worst-case stress test exercising every rule at once
  (anchors/aliases, matrices, services, containers, inline scripts, ...)

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
│       ├── cli.py               # Presentation: argparse, printing, exit codes
│       ├── config.py            # Options schema (enums), validation, loading
│       ├── yamllint_sync.py     # Derive indentation from a yamllint config
│       ├── core/                # Domain: pure tree/text transformations, no I/O
│       │   ├── pipeline.py      # Engine: rules -> dump -> post-processors
│       │   ├── comments.py      # Comment-preserving key reordering
│       │   ├── tree.py          # Typed tree accessors + traversal
│       │   ├── yaml_io.py       # ruamel parser/dumper configuration (StringIO)
│       │   ├── casing.py        # Casing conversion + safe rename planning
│       │   ├── references.py    # Expression reference rewriting
│       │   ├── directives.py    # Inline disable directives
│       │   ├── postprocess.py   # Text post-processors (blank lines)
│       │   ├── context.py       # Per-file context (config, diagnostics)
│       │   ├── diagnostics.py   # Diagnostic value objects
│       │   └── rules/           # One formatting rule per module
│       ├── app/                 # Application: frontend-agnostic orchestration
│       │   ├── service.py       # process_file: read -> format -> write/report
│       │   └── planning.py      # Cross-file caller/input planning
│       └── io/                  # Infrastructure: filesystem only
│           ├── files.py         # Read/write with line-ending policy
│           └── discovery.py     # Workflow/action file discovery
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
