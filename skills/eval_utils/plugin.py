"""pytest integration: options, the `live_eval` marker, and the run fixture.

The only module that touches pytest at import time. It registers the
`--live-eval-trials` / `--live-eval-min-pass` options and the `live_eval`
marker (both re-exported through `skills/conftest.py` so they apply once
across the whole skills tree), resolves the effective per-assertion pass
threshold, and builds the session-scoped fixture that runs `claude -p`
across adaptive trial batches per eval.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from eval_utils.grading import _eval_checks, load_evals, run_eval_adaptive
from eval_utils.stream_json import EvalRun

DEFAULT_TRIALS = 8
DEFAULT_MIN_PASS = 7


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the `--live-eval-trials` and `--live-eval-min-pass` options.

    Re-exported through `skills/conftest.py` so the trial count and
    per-assertion pass threshold can be tuned from the pytest command line.
    """
    parser.addoption(
        "--live-eval-trials",
        action="store",
        type=int,
        default=DEFAULT_TRIALS,
        help=(
            "How many times to run each eval. Each assertion must pass "
            "in at least --live-eval-min-pass of these trials. "
            f"Default {DEFAULT_TRIALS}."
        ),
    )
    parser.addoption(
        "--live-eval-min-pass",
        action="store",
        type=int,
        default=None,
        help=(
            "Minimum number of trials in which each assertion must pass for "
            "the assertion to be considered passing. "
            f"Defaults to min({DEFAULT_MIN_PASS}, "
            "--live-eval-trials), so fewer trials than the default still "
            "yield a reachable threshold."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the `live_eval` marker for selecting/skipping live tests."""
    config.addinivalue_line(
        "markers",
        "live_eval: end-to-end test that invokes `claude -p` (real model "
        "call). Select with `-m live_eval`; exclude with `-m 'not live_eval'`.",
    )


def resolve_min_pass(min_pass_opt: int | None, trials: int) -> int:
    """The effective per-assertion pass threshold.

    When `--live-eval-min-pass` is left unset (`None`) it defaults to
    `min(DEFAULT_MIN_PASS, trials)`, so running fewer trials than the default
    still yields a reachable threshold (at the low end every trial must pass)
    rather than an impossible "7 of 3". An explicit value is used as given.

    Both the batch-sizing fixture and the grading fixture resolve through
    here so the threshold that decides how many trials to run is the same one
    the assertions are graded against.
    """
    return (
        min(DEFAULT_MIN_PASS, trials) if min_pass_opt is None else min_pass_opt
    )


def make_eval_runs_fixture(
    evals_path: Path,
    repo_root: Path,
    skill_name: str,
    assertion_handlers: dict[str, Callable[[EvalRun], None]],
) -> Callable[..., dict[str, list[EvalRun]]]:
    """Build a session-scoped pytest fixture that runs claude -p up to
    `--live-eval-trials` times per eval in `evals_path` and returns the
    parsed runs keyed by eval id.

    Per-skill conftest.py binds the returned fixture to the name
    `eval_runs` so per-skill `test_evals.py` can request it directly. The
    value is a list of `EvalRun` per eval (one per trial run): trials run
    in adaptive concurrent batches that stop as soon as the verdict is fixed,
    decided from `assertion_handlers` (plus the skill-trigger check). Every
    run is a fresh live call; results are never cached.
    """

    @pytest.fixture(scope="session")
    def eval_runs(pytestconfig: pytest.Config) -> dict[str, list[EvalRun]]:
        pytest.skip("claude CLI not found on PATH") if shutil.which(
            "claude"
        ) is None else None
        trials = pytestconfig.getoption("--live-eval-trials")
        min_pass = resolve_min_pass(
            pytestconfig.getoption("--live-eval-min-pass"), trials
        )

        def build(item: dict[str, Any]) -> list[EvalRun]:
            checks = _eval_checks(item, assertion_handlers)
            return run_eval_adaptive(
                item, repo_root, skill_name, trials, min_pass, checks
            )

        return {item["id"]: build(item) for item in load_evals(evals_path)}

    return eval_runs


@pytest.fixture(scope="session")
def live_eval_min_pass(pytestconfig: pytest.Config) -> int:
    """The per-assertion pass threshold, resolved like the batch sizing."""
    return resolve_min_pass(
        pytestconfig.getoption("--live-eval-min-pass"),
        pytestconfig.getoption("--live-eval-trials"),
    )