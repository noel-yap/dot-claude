"""Pytest config for dependency-injection skill Claude evals.

The `--live-eval-trials` / `--live-eval-min-pass` options and the
`live_eval` marker are registered once at the parent `skills/conftest.py`.
This file only wires the session-scoped `eval_runs` fixture for this skill.

Run the full eval set with:

    pytest skills/dependency-injection/evals -m live_eval

Each eval is graded over up to `--live-eval-trials` runs (default 8) and
each assertion must pass in at least `--live-eval-min-pass` of them
(defaults to `min(7, trials)`, so fewer trials still gives a reachable
threshold). To save cost the runs are adaptive: trials run in concurrent
batches (the first sized to the `min_pass` passes a clean eval needs) and
re-grade after each batch, stopping as soon as every assertion has reached
`min_pass` passes or one can no longer reach it — capping cost at `trials`
runs while often spending fewer. To run, say, 5 trials needing 4 passes each:

    pytest skills/dependency-injection/evals -m live_eval \
        --live-eval-trials 5 --live-eval-min-pass 4

Evals are non-deterministic by design and are never cached: every trial is
a fresh live `claude -p` call so the suite measures run-to-run variance.
Deterministic checks belong in the per-skill unit suites, not here.

Run ONE skill's eval dir at a time: every skill's evals reuse the module
names `_helpers` / `_assertions`, so pointing pytest at two eval dirs in
a single session collides in `sys.modules`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Put this eval dir on sys.path so `_helpers` / `_assertions` import under
# pytest's importlib mode (which, unlike prepend mode, does not add the
# conftest's own directory).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _assertions import ASSERTION_HANDLERS  # noqa: E402
from _helpers import EVALS_PATH, REPO_ROOT, SKILL_NAME  # noqa: E402

from eval_utils import make_eval_runs_fixture  # noqa: E402

eval_runs = make_eval_runs_fixture(
    EVALS_PATH, REPO_ROOT, SKILL_NAME, ASSERTION_HANDLERS
)
