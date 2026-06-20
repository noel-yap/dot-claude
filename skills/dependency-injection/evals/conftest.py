"""Pytest config for dependency-injection skill Claude evals.

The `--live-eval-max-trials` / `--live-eval-target-rate` options and the
`live_eval` marker are registered once at the parent `skills/conftest.py`.
This file only wires the session-scoped `eval_runs` fixture for this skill.

Run the full eval set with:

    pytest skills/dependency-injection/evals -m live_eval

Each assertion is graded by a Beta-binomial posterior over its true pass
rate: it passes once the posterior puts most of its mass at or above
`--live-eval-target-rate` (default 2/3). To save cost the runs are adaptive:
trials run in concurrent batches and re-grade after each, stopping as soon
as the posterior locks PASS or FAIL — capping cost at `--live-eval-max-trials`
runs (default 21) while usually spending far fewer. To demand a higher true
rate over a smaller budget:

    pytest skills/dependency-injection/evals -m live_eval \
        --live-eval-target-rate 0.8 --live-eval-max-trials 12

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
