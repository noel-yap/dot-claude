"""End-to-end Claude evals for the dependency-injection skill.

For each entry in ``evals.json`` this module:

  1. Runs ``claude -p <prompt>`` up to ``--live-eval-trials`` times
     (default 8) in adaptive concurrent batches via the ``eval_runs``
     fixture in ``conftest.py``.
  2. Detects whether the DI skill was invoked by scanning the
     ``stream-json`` events for a ``Skill`` tool_use targeting our skill.
  3. Captures the full assistant text (the proposed refactor) and applies
     grep-style assertions for refactor quality.

Because the model is non-deterministic, each assertion is graded over all
trials and must pass in at least ``--live-eval-min-pass`` of them
(default 7 of 8) rather than on a single draw.

Three of the four evals reference samples that exhibit the DI smell —
hardcoded module imports, hidden globals (Date.now / Math.random /
process.env), or a singleton couple. The fourth references
``samples/pure_calculator.ts``, a pure function with no I/O at all. That
one should NOT trigger the skill (it is the canonical "When NOT to use"
case from the SKILL.md), and the test asserts both that the skill stayed
quiet and that Claude added tests without inventing DI ceremony.

These tests carry the ``live_eval`` marker because each model call costs
time and money; select them with ``-m live_eval`` (see conftest.py) or via
``make eval-dependency-injection``. The unit targets exclude them with
``-m "not live_eval"``.
"""

from __future__ import annotations

import json

import pytest
from _assertions import ASSERTION_HANDLERS
from _helpers import (
    EVALS_PATH,
    EvalRun,
    assert_pass_rate,
    assertions_below_threshold,
    trial_outcomes,
    trigger_pass_counts,
)


class TestClaudeEvals:
    @staticmethod
    def _evals() -> list[dict]:
        """Load all eval entries from evals.json."""
        return json.loads(EVALS_PATH.read_text(encoding="utf-8"))["evals"]

    @staticmethod
    def _assertion_params(evals: list[dict]) -> list[pytest.param]:
        """Build a pytest.param per (eval_id, assertion_id) in evals.json."""
        return [
            pytest.param(ev["id"], ass["id"], id=f"{ev['id']}::{ass['id']}")
            for ev in evals
            for ass in ev["assertions"]
        ]

    @pytest.mark.live_eval
    @pytest.mark.parametrize(
        "eval_id,assertion_id", _assertion_params(_evals())
    )
    def test_eval_assertion(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_min_pass: int,
        eval_id: str,
        assertion_id: str,
    ) -> None:
        handler = ASSERTION_HANDLERS.get(assertion_id)
        assert handler is not None, (
            f"no handler registered for assertion {assertion_id!r}; "
            f"add it to ASSERTION_HANDLERS in _assertions.py"
        )
        outcomes = trial_outcomes(eval_runs[eval_id], handler)
        assert_pass_rate(
            outcomes, live_eval_min_pass, f"{eval_id}::{assertion_id}"
        )

    @pytest.mark.live_eval
    @pytest.mark.parametrize("eval_id", [ev["id"] for ev in _evals()])
    def test_eval_expectation(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_min_pass: int,
        eval_id: str,
    ) -> None:
        """Per-eval rollup: when any of this eval's assertions passed in fewer
        than the threshold trials, fail once with the eval's `expected_output`
        as the human-level intent, alongside which assertions fell short.

        The per-assertion `test_eval_assertion` nodes still report exactly
        which assertion regressed and why; this node adds the expected-outcome
        context once per eval instead of repeating it on every assertion.
        """
        ev = next(e for e in self._evals() if e["id"] == eval_id)
        runs = eval_runs[eval_id]
        below = assertions_below_threshold(
            runs, ev["assertions"], ASSERTION_HANDLERS, live_eval_min_pass
        )
        assert not below, (
            f"{eval_id}: {len(below)} assertion(s) below threshold "
            f"(need >= {live_eval_min_pass}/{len(runs)}):\n"
            + "\n".join(
                f"  - {aid}: {n}/{len(runs)} passed" for aid, n in below
            )
            + f"\n\nExpected outcome:\n  {ev['expected_output']}"
        )

    @pytest.mark.live_eval
    def test_should_trigger_evals_invoked_skill(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_min_pass: int,
    ) -> None:
        counts = trigger_pass_counts(eval_runs, self._evals())
        failures = list(filter(lambda c: c[1] < live_eval_min_pass, counts))
        assert not failures, (
            f"DI skill invoked below threshold "
            f"(need >= {live_eval_min_pass} trials): "
            + ", ".join(f"{eid}: {n}/{total}" for eid, n, total in failures)
        )
