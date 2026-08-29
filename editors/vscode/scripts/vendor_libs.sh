#!/usr/bin/env bash
# Vendors gh-formatter and its (all pure-Python) dependencies into
# bundled/libs, so the packaged extension works without the user running
# `pip install` themselves -- same approach as Microsoft's Python tool
# extensions (black-formatter, pylint, etc.). Regenerate before packaging
# or publishing; bundled/libs is gitignored, not committed, and gets
# picked up automatically by `npm run vendor` in vscode:prepublish.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO_ROOT="$(cd ../.. && pwd)"

# Prefer this project's own venv (guaranteed to have pip); fall back to a
# bare `python3` on PATH, which on some systems (e.g. Debian/Ubuntu without
# python3-pip installed) has no pip at all. Override with PYTHON=... if
# neither is right for your machine.
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
  else
    PYTHON="python3"
  fi
fi

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
  echo "error: '$PYTHON' has no pip available." >&2
  echo "Install pip for it, or set PYTHON=/path/to/a/python/with/pip." >&2
  exit 1
fi

rm -rf bundled/libs
"$PYTHON" -m pip install \
  --no-compile \
  --disable-pip-version-check \
  --target bundled/libs \
  "$REPO_ROOT"

# pip leaves __pycache__/metadata behind that isn't needed at runtime.
find bundled/libs -name "__pycache__" -type d -prune -exec rm -rf {} +
