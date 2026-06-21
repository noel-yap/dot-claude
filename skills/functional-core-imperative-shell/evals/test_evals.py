"""End-to-end Claude evals for the functional-core-imperative-shell skill.

For each entry in ``evals.json`` this module:

  1. Runs ``claude -p <prompt>`` up to ``--live-eval-max-trials`` times
     (default 21) in adaptive concurrent batches via the ``eval_runs``
     fixture in ``conftest.py``.
  2. Detects whether the FCIS skill was invoked by scanning the
     ``stream-json`` events for a ``Skill`` tool_use targeting our skill.
  3. Captures the full assistant text (the proposed refactor) and applies
     grep-style assertions for refactor quality.

Because the model is non-deterministic, each assertion is graded by a
Beta-binomial posterior over its true pass rate: the assertion passes when
the posterior puts most of its mass at or above ``--live-eval-target-rate``
(default 3/5) rather than on a single draw.

Three of the four evals reference ``samples/order_processor.ts`` — a clear
FCIS candidate where business decisions are entangled with database and
email I/O. The fourth references ``samples/pipeline_coordinator.ts``, a
saga where the I/O sequence *is* the logic. That one should NOT trigger
the skill (it is the canonical "When NOT to use" case from the SKILL.md),
and the test asserts both that the skill stayed quiet and that Claude
delivered the requested retry/backoff change without inventing a fake
pure core.

These tests carry the ``live_eval`` marker because each model call costs
time and money; select them with ``-m live_eval`` (see conftest.py) or via
``make eval-functional-core-imperative-shell``. The unit targets exclude them
with ``-m "not live_eval"``.
"""

from __future__ import annotations

import json

import pytest
from ._assertions import ASSERTION_HANDLERS
from ._helpers import (
    EVALS_PATH,
    EvalRun,
    assert_eval_passed,
    failing_assertions,
    trial_outcomes,
    trigger_pass_counts,
)
from binom_eval import eval_passed


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
        live_eval_target_rate: float,
        eval_id: str,
        assertion_id: str,
    ) -> None:
        # Requesting eval_runs builds the fixture first, and that build runs
        # load-time handler-coverage validation -- so every assertion_id here
        # is guaranteed to have a registered handler.
        handler = ASSERTION_HANDLERS[assertion_id]
        outcomes = trial_outcomes(eval_runs[eval_id], handler)
        assert_eval_passed(
            outcomes, live_eval_target_rate, f"{eval_id}::{assertion_id}"
        )

    @pytest.mark.live_eval
    @pytest.mark.parametrize("eval_id", [ev["id"] for ev in _evals()])
    def test_eval_expectation(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_target_rate: float,
        eval_id: str,
    ) -> None:
        """Per-eval rollup: when any of this eval's assertions failed the
        posterior bar, fail once with the eval's `expected_output` as the
        human-level intent, alongside which assertions fell short.

        The per-assertion `test_eval_assertion` nodes still report exactly
        which assertion regressed and why; this node adds the expected-outcome
        context once per eval instead of repeating it on every assertion.
        """
        ev = next(e for e in self._evals() if e["id"] == eval_id)
        runs = eval_runs[eval_id]
        failing = failing_assertions(
            runs, ev["assertions"], ASSERTION_HANDLERS, live_eval_target_rate
        )
        assert not failing, (
            f"{eval_id}: {len(failing)} assertion(s) below the bar "
            f"(P(rate >= {live_eval_target_rate:.3f}) must be >= 0.5):\n"
            + "\n".join(
                f"  - {aid}: {n}/{total} passed, p_good={p:.3f}"
                for aid, n, total, p in failing
            )
            + f"\n\nExpected outcome:\n  {ev['expected_output']}"
        )

    @pytest.mark.live_eval
    def test_should_trigger_evals_invoked_skill(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_target_rate: float,
    ) -> None:
        counts = trigger_pass_counts(eval_runs, self._evals())
        failures = [
            (eid, n, total)
            for eid, n, total in counts
            if not eval_passed(n, total, live_eval_target_rate)
        ]
        assert not failures, (
            f"FCIS skill invoked below the bar "
            f"(P(rate >= {live_eval_target_rate:.3f}) must be >= 0.5): "
            + ", ".join(f"{eid}: {n}/{total}" for eid, n, total in failures)
        )