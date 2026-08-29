# gh-formatter for VSCode

Format and lint GitHub Actions workflow and action YAML files, backed by
[gh-formatter](https://github.com/nimpsch/gh-formatter)'s own formatting
engine over a real Language Server Protocol connection.

## Features

- **Format on save** for `.github/workflows/*.yml` and `action.yml`/`action.yaml`.
- **Inline diagnostics** — parse errors and lint findings (undeclared
  caller inputs, casing collisions, etc.) shown at their exact line and
  column, refreshed when a file is opened or saved.

## Requirements

Just a Python 3 interpreter on your `PATH` (`python3` or `python`) — that's
it. This extension bundles its own copy of gh-formatter and everything it
needs, the same approach Microsoft's own Python tool extensions
(black-formatter, pylint, ...) use, so there's nothing to `pip install`.

If you'd rather the editor use the exact gh-formatter version pinned by
your project's `pre-commit`/CI setup instead of the bundled copy, set:

```json
{ "gh-formatter.importStrategy": "fromEnvironment" }
```

which looks for `gh-formatter-lsp` in `.venv/bin/` (workspace root) or on
`PATH`, falling back to the bundled copy with a warning if neither is
found (same as `black-formatter`/`ruff`'s `importStrategy`). `gh-formatter.serverPath`
overrides either strategy with an exact path. If nothing resolves at all,
you'll get a notification explaining how to fix it.

## Enabling format-on-save

On first activation you'll get a one-time prompt offering to set this up
automatically for both `yaml` and `github-actions-workflow`. To set it up
by hand instead:

```json
{
  "[yaml]": {
    "editor.defaultFormatter": "nimpsch.gh-formatter-vscode",
    "editor.formatOnSave": true
  },
  "[github-actions-workflow]": {
    "editor.defaultFormatter": "nimpsch.gh-formatter-vscode",
    "editor.formatOnSave": true
  }
}
```

Both are set because of an editor quirk: GitHub's own
[GitHub Actions extension](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-github-actions),
if installed, reassigns workflow files to `github-actions-workflow`
instead of `yaml` — without it, workflow files stay plain `yaml`. Setting
both covers either case.

**Trade-off**: this extension only *offers* to format the narrower set
(`.github/workflows/**`, `action.yml`/`action.yaml`) — but
`editor.defaultFormatter` for `"[yaml]"` applies to *all* YAML files. If
you already use a different formatter for non-Actions YAML, skip that
block (only add `"[github-actions-workflow]"`), or decline the prompt and
configure it yourself. "Format Document" still works on demand regardless
of `editor.defaultFormatter`, as long as the file matches this extension's
scope.

## Extension Settings

| Setting                     | Default       | Description                                                   |
|------------------------------|---------------|------------------------------------------------------------------|
| `gh-formatter.enable`        | `true`        | Enable the gh-formatter language server.                        |
| `gh-formatter.importStrategy`| `useBundled`  | `useBundled` runs the copy shipped with this extension; `fromEnvironment` uses the one installed in your project. |
| `gh-formatter.serverPath`    | `""`          | Explicit path to a `gh-formatter-lsp` executable. Overrides `importStrategy`. |

## Known Limitations

- Diagnostics refresh on open/save only, not live as you type.
- Single-root workspaces only — in a multi-root workspace, only the first
  folder's `.gh-formatter.yml` is used.
- The bundled strategy still needs *some* Python 3 interpreter on `PATH` —
  it removes the `pip install` step, not the need for Python to exist.

## Learn More

See the [gh-formatter README](https://github.com/nimpsch/gh-formatter#readme)
for configuration options, inline directives, and CLI usage.
