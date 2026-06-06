"""Pytest config for dependency-injection skill Claude evals.

The `--run-claude` / `--claude-eval-cache` options and the
`claude_eval` marker are registered once at the parent
`skills/conftest.py`. This file only wires the session-scoped
`claude_runs` fixture for this skill.

Run the full eval set with:

    pytest skills/dependency-injection/evals --run-claude

Optionally cache outputs across runs to avoid repeated API calls:

    pytest ... --run-claude \
        --claude-eval-cache /tmp/di-evals-cache.json
"""

from __future__ import annotations

from _helpers import EVALS_PATH, REPO_ROOT, SKILL_NAME
from eval_utils import make_claude_runs_fixture

claude_runs = make_claude_runs_fixture(EVALS_PATH, REPO_ROOT, SKILL_NAME)