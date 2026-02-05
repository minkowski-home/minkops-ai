"""Thin entrypoint for the AI Suite orchestrator CLI.

We keep a small top-level script so developers can run:
`python services/ai-suite/main.py <cmd>`

The real implementation lives in `ai_suite/` so it is testable and importable.
"""

from __future__ import annotations

import sys

from ai_suite.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

