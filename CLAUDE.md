# gh-formatter

Python formatter for GitHub Actions workflows/actions. Source in
`src/gh_formatter/`, tests in `tests/`, sample workflows in `examples/`.
All tooling runs through the project venv: `.venv/bin/...`.

## Delegation policy (always orchestrate)

Default to delegating; the main session plans, decides, and reviews — the
roles below do the volume work. Refer to roles only by name; their model
and effort tiers live in `.claude/agents/` and may be retuned without
touching this policy.

- **Explore** — any code-location question ("where is X", "what references
  Y", file-pattern lookups). Never run broad searches in the main session.
- **recon** — before designing a fix or feature, have recon map the
  relevant subsystem and report constraints. Read at most 1–2 files
  directly; beyond that, delegate.
- **mechanic** — once a change is precisely specified: repetitive
  multi-file edits, fixture updates after an order/config change,
  black/ruff autofixes, reformatting the repo's own YAML.
- **gate** — after every code change, run the full quality gate through
  gate instead of invoking the six tools inline.

Keep in the main session: design decisions, edits to
`src/gh_formatter/comments.py` (the regression-prone comment surgery),
API/interface changes, anything the user must decide, and final review of
delegated work.

When a delegated result looks wrong or incomplete, escalate to the main
session rather than re-delegating in a loop.

## Verification

The full gate (what `gate` runs): pytest, ruff, black --check, mypy,
yamllint --strict, `gh-formatter --check . examples/*.yml`. A change is
done only when all six pass and the repo's own YAML stays idempotent.

`config.py`'s DEFAULT_CONFIG is the source of truth for options; keep
`.gh-formatter.yml` and the README config block in sync with it.
