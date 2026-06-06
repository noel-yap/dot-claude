"""End-to-end Claude evals for the dependency-injection skill.

For each entry in ``evals.json`` this module:

  1. Runs ``claude -p <prompt>`` once (cached for the test session via the
     ``claude_runs`` fixture in ``conftest.py``).
  2. Detects whether the DI skill was invoked by scanning the
     ``stream-json`` events for a ``Skill`` tool_use targeting our skill.
  3. Captures the full assistant text (the proposed refactor) and applies
     grep-style assertions for refactor quality.

Three of the four evals reference samples that exhibit the DI smell —
hardcoded module imports, hidden globals (Date.now / Math.random /
process.env), or a singleton couple. The fourth references
``samples/pure_calculator.ts``, a pure function with no I/O at all. That
one should NOT trigger the skill (it is the canonical "When NOT to use"
case from the SKILL.md), and the test asserts both that the skill stayed
quiet and that Claude added tests without inventing DI ceremony.

Tests are skipped by default because each model call costs time and money.
Opt in with ``--run-claude`` (see conftest.py).
"""

from __future__ import annotations

import json

import pytest

from _assertions import ASSERTION_HANDLERS
from _helpers import EVALS_PATH, ClaudeRun


def _untriggered_should_trigger_ids(
        runs: dict[str, ClaudeRun], evals: list[dict]
) -> list[str]:
    """Return eval IDs where should_trigger is True but the DI skill was not invoked."""
    should_trigger = list(filter(lambda ev: ev.get("should_trigger"), evals))
    untriggered = filter(lambda ev: not runs[ev["id"]].skill_invoked, should_trigger)
    return list(map(lambda ev: ev["id"], untriggered))


class TestUntriggeredShouldTriggerIds:
    @staticmethod
    def _make_run(skill_invoked: bool) -> ClaudeRun:
        """Construct a minimal ClaudeRun for unit tests."""
        return ClaudeRun(eval_id="t", prompt="", skill_invoked=skill_invoked, assistant_text="")

    def test_returns_empty_when_all_triggered(self) -> None:
        runs = {"a": self._make_run(True)}
        evals = [{"id": "a", "should_trigger": True}]
        assert _untriggered_should_trigger_ids(runs, evals) == []

    def test_returns_id_when_skill_not_invoked(self) -> None:
        runs = {"a": self._make_run(False)}
        evals = [{"id": "a", "should_trigger": True}]
        assert _untriggered_should_trigger_ids(runs, evals) == ["a"]

    def test_ignores_non_should_trigger_evals(self) -> None:
        runs = {"a": self._make_run(False)}
        evals = [{"id": "a", "should_trigger": False}]
        assert _untriggered_should_trigger_ids(runs, evals) == []


class TestClaudeEvals:
    @staticmethod
    def _evals() -> list[dict]:
        """Load all eval entries from evals.json."""
        return json.loads(EVALS_PATH.read_text(encoding="utf-8"))["evals"]

    @staticmethod
    def _assertion_params(evals: list[dict]) -> list[pytest.param]:
        """Build pytest.param entries for every (eval_id, assertion_id) combination in evals.json."""
        return [
            pytest.param(ev["id"], ass["id"], id=f"{ev['id']}::{ass['id']}")
            for ev in evals
            for ass in ev["assertions"]
        ]

    @pytest.mark.claude_eval
    @pytest.mark.parametrize("eval_id,assertion_id", _assertion_params(_evals()))
    def test_eval_assertion(
            self, claude_runs: dict[str, ClaudeRun], eval_id: str, assertion_id: str
    ) -> None:
        handler = ASSERTION_HANDLERS.get(assertion_id)
        assert handler is not None, (
            f"no handler registered for assertion {assertion_id!r}; "
            f"add it to ASSERTION_HANDLERS in _assertions.py"
        )
        handler(claude_runs[eval_id])

    @pytest.mark.claude_eval
    def test_should_trigger_evals_invoked_skill(
            self,
            claude_runs: dict[str, ClaudeRun],
    ) -> None:
        failures = _untriggered_should_trigger_ids(claude_runs, self._evals())
        assert not failures, (
            f"DI skill did not invoke on should_trigger evals: {failures}"
        )