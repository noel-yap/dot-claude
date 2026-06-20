"""Pytest config for FCIS skill end-to-end Claude evals.

The `--live-eval-max-trials` / `--live-eval-target-rate` options and the
`live_eval` marker are registered once at the parent `skills/conftest.py`.
This file only wires the session-scoped `eval_runs` fixture for this skill.

Run the full eval set with:

    pytest skills/functional-core-imperative-shell/evals -m live_eval

Each assertion is graded by a Beta-binomial posterior over its true pass
rate: it passes once the posterior puts most of its mass at or above
`--live-eval-target-rate` (default 2/3). To save cost the runs are adaptive:
trials run in concurrent batches and re-grade after each, stopping as soon
as the posterior locks PASS or FAIL — capping cost at `--live-eval-max-trials`
runs (default 21) while usually spending far fewer. To demand a higher true
rate over a smaller budget:

    pytest skills/functional-core-imperative-shell/evals -m live_eval \
        --live-eval-target-rate 0.8 --live-eval-max-trials 12

Evals are non-deterministic by design and are never cached: every trial is
a fresh live `claude -p` call so the suite measures run-to-run variance.
Deterministic checks belong in the per-skill unit suites, not here.

Multiple skills' eval dirs can be collected in one pytest session: each
`evals` dir is a namespace package (no `__init__.py`) and its sibling
modules are imported relatively (`from ._helpers import ...`), so
`_helpers` / `_assertions` are namespaced per skill rather than colliding
in `sys.modules`. See `skills/pytest.ini` (`consider_namespace_packages`).
"""

from __future__ import annotations

from ._assertions import ASSERTION_HANDLERS
from ._helpers import EVALS_PATH, REPO_ROOT, SKILL_NAME

from eval_utils import make_eval_runs_fixture

eval_runs = make_eval_runs_fixture(
    EVALS_PATH, REPO_ROOT, SKILL_NAME, ASSERTION_HANDLERS
)
