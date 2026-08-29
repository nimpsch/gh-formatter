"""Entry point spawned by the extension's bundled (default) import strategy.

Puts the vendored gh-formatter + dependencies (populated into ../libs by
scripts/vendor_libs.sh) on sys.path, then runs the real server.
"""

import os
import sys

_BUNDLED_LIBS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "libs")
sys.path.insert(0, _BUNDLED_LIBS)

from gh_formatter.lsp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
