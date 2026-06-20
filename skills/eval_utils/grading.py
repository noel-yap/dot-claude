"""Deciding eval verdicts from repeated trials.

Two concerns live here. First, the adaptive driver: `_eval_checks` derives
the pass/fail checks for an eval, `next_batch_size` decides how many more
trials are worth running given the results so far, and `run_eval_adaptive`
loops the two until the verdict is fixed -- capping cost at `trials` runs
while spending as few as `min_pass` when every trial passes. Second, the
pass-rate rollups (`trial_outcomes`, `assert_pass_rate`,
`assertions_below_threshold`, `trigger_pass_counts`) that per-skill tests
use to grade and report on a completed batch of runs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eval_utils.runner import run_claude_batch
from eval_utils.stream_json import EvalRun


def _trigger_check(run: EvalRun) -> None:
    """Assertion-style check that the skill fired (for should_trigger evals)."""
    if not run.skill_invoked:
        raise AssertionError("skill was not invoked")


def _eval_checks(
    item: dict[str, Any],
    assertion_handlers: dict[str, Callable[[EvalRun], None]],
) -> list[Callable[[EvalRun], None]]:
    """The pass/fail checks that decide an eval: its registered assertion
    handlers plus, for should_trigger evals, the skill-invocation check.

    These are exactly the checks whose per-trial outcomes determine whether
    further trials could still change the verdict.
    """
    checks = [
        assertion_handlers[a["id"]]
        for a in item.get("assertions", [])
        if a["id"] in assertion_handlers
    ]
    if item.get("should_trigger"):
        checks.append(_trigger_check)
    return checks


def _check_failures(
    runs: list[EvalRun], check: Callable[[EvalRun], None]
) -> int:
    """Number of `runs` for which `check` fails (raises AssertionError)."""
    return sum(1 for _, err in trial_outcomes(runs, check) if err is not None)


def next_batch_size(
    runs: list[EvalRun],
    checks: list[Callable[[EvalRun], None]],
    trials: int,
    min_pass: int,
) -> int:
    """How many trials to run next, or 0 once the verdict is fixed.

    Each check must pass in `min_pass` of at most `trials` runs. Given the
    runs so far, the eval is already decided when either every check has
    `min_pass` passes (PASS) or some check has more than `trials - min_pass`
    failures, putting `min_pass` out of reach (FAIL); both return 0.

    Otherwise the next batch is optimistic -- it runs the passes still owed,
    assuming they all land:
      * the largest per-check pass shortfall, since the eval passes only once
        the *worst* check clears `min_pass` (so all-passing trials of that
        size would finish every check at once);
      * capped by `remaining` so it never exceeds the `trials` budget.
    Batching to the shortfall keeps concurrency high (the first batch is the
    `min_pass` passes a clean eval needs); the loop in `run_eval_adaptive`
    re-grades after each batch, shrinking the next one as passes accumulate.
    """
    runs_done = len(runs)
    remaining = trials - runs_done
    if remaining <= 0:
        return 0
    fails = [_check_failures(runs, c) for c in checks]
    unsatisfied = [f for f in fails if runs_done - f < min_pass]
    if not unsatisfied:
        return 0
    if any(f > trials - min_pass for f in unsatisfied):
        return 0
    need_pass = max(min_pass - (runs_done - f) for f in unsatisfied)
    return min(need_pass, remaining)


def run_eval_adaptive(
    item: dict[str, Any],
    repo_root: Path,
    skill_name: str,
    trials: int,
    min_pass: int,
    checks: list[Callable[[EvalRun], None]],
) -> list[EvalRun]:
    """Run trials in optimistic concurrent batches, stopping once the verdict
    is fixed.

    Each round runs `next_batch_size` trials concurrently (the first batch is
    the `min_pass` passes a clean eval needs) and re-grades, looping until
    every check has cleared `min_pass` or one has fallen out of reach. This
    caps cost at `trials` runs and spends as few as `min_pass` when every
    trial passes, over however many rounds the outcomes require.
    """
    runs: list[EvalRun] = []
    batch = next_batch_size(runs, checks, trials, min_pass)
    while batch > 0:
        runs.extend(run_claude_batch(item, repo_root, skill_name, batch))
        batch = next_batch_size(runs, checks, trials, min_pass)
    return runs


def load_evals(evals_path: Path) -> list[dict[str, Any]]:
    """Read an `evals.json` file and return its list of eval items.

    Args:
        evals_path: Path to a skill's `evals.json`, an object with an
            `"evals"` key.

    Returns:
        The value of the file's top-level `"evals"` array.
    """
    return json.loads(evals_path.read_text(encoding="utf-8"))["evals"]


def trial_outcomes(
    runs: list[EvalRun], check: Callable[[EvalRun], None]
) -> list[tuple[int, str | None]]:
    """Run `check` against each trial run, capturing its assertion result.

    `check` is an assertion handler that raises ``AssertionError`` on
    failure. Returns one ``(trial_index, error_or_None)`` per run, where
    a ``None`` error means that trial passed.
    """
    outcomes: list[tuple[int, str | None]] = []
    for idx, run in enumerate(runs):
        try:
            check(run)
            outcomes.append((idx, None))
        except AssertionError as exc:
            outcomes.append((idx, str(exc)))
    return outcomes


def assert_pass_rate(
    outcomes: list[tuple[int, str | None]], min_pass: int, label: str
) -> None:
    """Assert that at least `min_pass` of the trial outcomes passed."""
    passes = list(filter(lambda o: o[1] is None, outcomes))
    fails = list(filter(lambda o: o[1] is not None, outcomes))
    detail = "\n".join(f"  trial {idx}: {err}" for idx, err in fails)
    if len(passes) < min_pass:
        raise AssertionError(
            f"{label}: {len(passes)}/{len(outcomes)} trials passed "
            f"(need >= {min_pass}).\nFailing trials:\n{detail}"
        )


def assertions_below_threshold(
    runs: list[EvalRun],
    assertions: list[dict[str, Any]],
    handlers: dict[str, Callable[[EvalRun], None]],
    min_pass: int,
) -> list[tuple[str, int]]:
    """For one eval's runs, the `(assertion_id, pass_count)` of every
    registered assertion that passed in fewer than `min_pass` trials.

    This mirrors the per-assertion grading in `assert_pass_rate` but rolls it
    up across all of an eval's assertions, so a single per-eval report can
    name every assertion that fell short (and pair them with the eval's
    `expected_output`). Assertions with no registered handler are skipped —
    the per-assertion test flags those separately. An empty result means the
    whole eval cleared the threshold.
    """
    below: list[tuple[str, int]] = []
    for assertion in assertions:
        handler = handlers.get(assertion["id"])
        if handler is None:
            continue
        passes = sum(
            1 for _, err in trial_outcomes(runs, handler) if err is None
        )
        if passes < min_pass:
            below.append((assertion["id"], passes))
    return below


def trigger_pass_counts(
    runs: dict[str, list[EvalRun]], evals: list[dict[str, Any]]
) -> list[tuple[str, int, int]]:
    """Per should_trigger eval: (id, trials_invoking_skill, trials_total)."""
    return [
        (
            ev["id"],
            sum(r.skill_invoked for r in runs[ev["id"]]),
            len(runs[ev["id"]]),
        )
        for ev in evals
        if ev.get("should_trigger")
    ]