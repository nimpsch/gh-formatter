# Repository rulesets

These JSON files are importable [repository rulesets](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository).
They are kept in the repo for version control; GitHub does **not** apply them
automatically — you must import them once (and re-import after edits).

## How to import

1. Go to **Settings → Rules → Rulesets** in the repository.
2. Click **New ruleset → Import a ruleset**.
3. Select the JSON file and click **Create**.
4. Repeat for each file.

## Files

| File | What it does |
| ---- | ------------ |
| `main-branch-protection.json` | Protects the default branch: requires a PR with 1 Code Owner approval, passing CI, linear history, blocks force-push and deletion. |
| `branch-naming.json` | Enforces a naming convention on all non-default branches pushed to this repo. |

## Who can approve & merge

- **Approve:** Only accounts in [`.github/CODEOWNERS`](../CODEOWNERS) that also have
  Write+ access satisfy the required review. Today that is only `@nimpsch`.
  External contributors fork the repo and have read-only access, so their reviews
  are non-binding.
- **Merge:** Only accounts with Write+ access can click merge. On a public repo,
  forkers never have write, so they can never merge. Keep yourself the sole
  admin/collaborator and you remain the only person who can merge.

The default-branch ruleset lists **Repository admin (`actor_id: 5`)** as a bypass
actor so you can merge your own PRs (a PR author cannot approve their own PR).
Remove the `bypass_actors` entry if you want the review requirement to apply to
you as well.

## Branch naming convention

Non-default branches must match:

```
^(feature|fix|hotfix|chore|docs|refactor|test|ci|build|perf|release|dependabot)/[a-z0-9._/-]+$
```

Examples that pass: `feature/yaml-anchors`, `fix/issue-42`, `docs/readme-badges`,
`dependabot/pip/black-25.1.0`.

> **Note:** Branch-name rules apply only to branches created in *this* repo.
> A fork is a separate repository, so this rule cannot constrain the head-branch
> name of a PR opened from someone else's fork — it governs your own branches and
> any direct collaborators.
