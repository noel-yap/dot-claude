"""Unit tests for `eval_utils.grading` (verdict logic + pass-rate rollups).

Covers the adaptive trial driver (`next_batch_size`, `run_eval_adaptive`
and the checks feeding them) and the rollups per-skill suites grade with
(`trial_outcomes`, `assert_pass_rate`, `assertions_below_threshold`,
`trigger_pass_counts`). `eval_utils` is skill-independent, so this logic is
tested once here rather than duplicated per skill.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import eval_utils
from eval_utils import (
    EvalRun,
    _check_failures,
    _eval_checks,
    _trigger_check,
    assert_pass_rate,
    assertions_below_threshold,
    next_batch_size,
    trial_outcomes,
    trigger_pass_counts,
)


def _runs(*passed: bool) -> list[EvalRun]:
    """Trials whose `skill_invoked` flag stands in for pass/fail."""
    return [
        EvalRun(eval_id="t", prompt="", skill_invoked=p, assistant_text="")
        for p in passed
    ]


class TestTriggerCheck:
    def test_passes_when_skill_invoked(self) -> None:
        _trigger_check(_runs(True)[0])  # should not raise

    def test_raises_when_skill_not_invoked(self) -> None:
        with pytest.raises(AssertionError, match="skill was not invoked"):
            _trigger_check(_runs(False)[0])


class TestTrialOutcomes:
    def test_records_pass_and_fail_per_trial(self) -> None:
        def check(run: EvalRun) -> None:
            assert run.skill_invoked, "miss"

        outcomes = trial_outcomes(_runs(True, False), check)
        assert outcomes[0] == (0, None)
        assert outcomes[1][0] == 1
        assert outcomes[1][1] is not None


class TestAssertPassRate:
    def test_passes_at_threshold(self) -> None:
        assert_pass_rate(
            [(0, None), (1, None), (2, "bad")], min_pass=2, label="x"
        )

    def test_fails_below_threshold(self) -> None:
        with pytest.raises(AssertionError, match=r"1/3 trials passed"):
            assert_pass_rate(
                [(0, None), (1, "bad"), (2, "bad")], min_pass=2, label="x"
            )


class TestAssertionsBelowThreshold:
    """Per-eval rollup of which assertions passed in fewer than `min_pass`."""

    @staticmethod
    def _skill(run: EvalRun) -> None:
        assert run.skill_invoked, "skill"

    @staticmethod
    def _text(run: EvalRun) -> None:
        assert run.assistant_text, "text"

    def _handlers(self) -> dict:
        return {"a": self._skill, "b": self._text}

    def test_empty_when_all_clear_threshold(self) -> None:
        # 3 runs that pass the "skill" check; threshold 2.
        runs = _runs(True, True, True)
        assertions = [{"id": "a"}]
        assert (
            assertions_below_threshold(runs, assertions, self._handlers(), 2)
            == []
        )

    def test_reports_id_and_pass_count_below_threshold(self) -> None:
        # 1 of 3 runs invoked the skill; need 2.
        runs = _runs(True, False, False)
        assertions = [{"id": "a"}]
        assert assertions_below_threshold(
            runs, assertions, self._handlers(), 2
        ) == [("a", 1)]

    def test_skips_assertions_without_a_handler(self) -> None:
        runs = _runs(False, False)
        # "missing" has no handler even though it would be below threshold.
        assertions = [{"id": "missing"}, {"id": "a"}]
        assert assertions_below_threshold(
            runs, assertions, self._handlers(), 2
        ) == [("a", 0)]

    def test_collects_every_failing_assertion(self) -> None:
        # All runs miss skill (a) and have empty text (b): both below 2.
        runs = _runs(False, False)
        assertions = [{"id": "a"}, {"id": "b"}]
        assert assertions_below_threshold(
            runs, assertions, self._handlers(), 2
        ) == [("a", 0), ("b", 0)]


class TestEvalChecks:
    def test_collects_assertion_handlers(self) -> None:
        handlers = {"a": lambda _r: None, "b": lambda _r: None}
        item = {"assertions": [{"id": "a"}, {"id": "b"}]}
        assert _eval_checks(item, handlers) == [handlers["a"], handlers["b"]]

    def test_appends_trigger_check_when_should_trigger(self) -> None:
        item = {"assertions": [], "should_trigger": True}
        assert len(_eval_checks(item, {})) == 1

    def test_skips_unregistered_assertion_ids(self) -> None:
        item = {"assertions": [{"id": "missing"}]}
        assert _eval_checks(item, {}) == []


class TestCheckFailures:
    @staticmethod
    def _check(run: EvalRun) -> None:
        assert run.skill_invoked, "miss"

    def test_counts_failing_runs(self) -> None:
        assert _check_failures(_runs(True, False, False), self._check) == 2

    def test_counts_zero_when_all_pass(self) -> None:
        assert _check_failures(_runs(True, True), self._check) == 0


class TestNextBatchSize:
    """The adaptive batch sizing that drives `run_eval_adaptive`.

    A run "passes" a check when `skill_invoked` is True; `_check` fails on a
    miss, so a check's failure count equals its number of misses. The result
    is 0 once the verdict is fixed (every check at `min_pass`, or one out of
    reach), else the number of trials to run next.
    """

    @staticmethod
    def _check(run: EvalRun) -> None:
        assert run.skill_invoked, "miss"

    def test_first_batch_targets_min_pass(self) -> None:
        # 7-of-8, nothing run yet: optimistically run the 7 passes owed.
        assert next_batch_size([], [self._check], trials=8, min_pass=7) == 7

    def test_zero_once_min_pass_reached(self) -> None:
        runs = _runs(*([True] * 7))  # already 7 passes
        assert next_batch_size(runs, [self._check], trials=8, min_pass=7) == 0

    def test_runs_one_more_on_single_failure(self) -> None:
        runs = _runs(
            True, True, True, True, True, True, False
        )  # 6 pass, 1 fail
        assert next_batch_size(runs, [self._check], trials=8, min_pass=7) == 1

    def test_zero_once_out_of_reach(self) -> None:
        runs = _runs(
            True, True, True, True, True, False, False
        )  # cannot reach 7
        assert next_batch_size(runs, [self._check], trials=8, min_pass=7) == 0

    def test_zero_when_trials_exhausted(self) -> None:
        runs = _runs(*([True] * 4 + [False] * 4))  # 8 runs, 4 passes, undecided
        assert next_batch_size(runs, [self._check], trials=8, min_pass=7) == 0

    def test_no_checks_runs_nothing(self) -> None:
        assert (
            next_batch_size(_runs(*([False] * 3)), [], trials=8, min_pass=7)
            == 0
        )

    def test_batch_stays_optimistic_near_a_fail_decision(self) -> None:
        # 4-of-8: 3 failures already, but the batch stays at the 4 passes
        # owed (capped by the 5 remaining), favouring concurrency over
        # minimising runs on a check that may yet fail.
        runs = _runs(False, False, False)  # 0 pass, 3 fail
        assert next_batch_size(runs, [self._check], trials=8, min_pass=4) == 4

    def test_batch_takes_largest_shortfall_across_checks(self) -> None:
        def check_a(run: EvalRun) -> None:
            assert run.skill_invoked, "a"

        def check_b(run: EvalRun) -> None:
            assert run.assistant_text, "b"

        # check_a: 2/2 pass (shortfall 3); check_b: 1/2 pass (shortfall 4).
        # The larger shortfall drives the batch; the fail budget is loose.
        runs = [
            EvalRun(
                eval_id="t", prompt="", skill_invoked=True, assistant_text="ok"
            ),
            EvalRun(
                eval_id="t", prompt="", skill_invoked=True, assistant_text=""
            ),
        ]
        assert (
            next_batch_size(runs, [check_a, check_b], trials=10, min_pass=5)
            == 4
        )

    def test_shrinks_over_successive_rounds(self) -> None:
        # 3-of-7, a mixed run sequence: the batch shrinks 3 -> 2 -> 1 as
        # passes accumulate, confirming more than two rounds are supported.
        assert next_batch_size([], [self._check], trials=7, min_pass=3) == 3
        after_r1 = _runs(True, False, False)  # 1 pass, 2 fail
        assert (
            next_batch_size(after_r1, [self._check], trials=7, min_pass=3) == 2
        )
        after_r2 = _runs(True, False, False, True, False)  # 2 pass, 3 fail
        assert (
            next_batch_size(after_r2, [self._check], trials=7, min_pass=3) == 1
        )


class TestRunEvalAdaptive:
    """The batch loop accumulates runs until `next_batch_size` returns 0."""

    @staticmethod
    def _check(run: EvalRun) -> None:
        assert run.skill_invoked, "miss"

    def test_loops_across_rounds_until_verdict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Scripted per-trial outcomes consumed `count` at a time. With 3-of-7
        # this drives three rounds (3, then 2, then 1) reaching 3 passes at
        # the sixth run; the seventh scripted outcome is never needed.
        scripted = [False, False, True, True, False, True, True]
        state = {"i": 0}

        def fake_batch(
            item: dict, repo_root: Path, skill_name: str, count: int
        ) -> list[EvalRun]:
            chunk = scripted[state["i"] : state["i"] + count]
            state["i"] += count
            return _runs(*chunk)

        monkeypatch.setattr(eval_utils.grading, "run_claude_batch", fake_batch)
        runs = eval_utils.run_eval_adaptive(
            {"id": "t", "prompt": "p"},
            Path("."),
            "demo",
            trials=7,
            min_pass=3,
            checks=[self._check],
        )
        assert len(runs) == 6
        assert sum(run.skill_invoked for run in runs) == 3


class TestTriggerPassCounts:
    def test_counts_invoked_trials(self) -> None:
        runs = {"a": _runs(True, False, True)}
        evals = [{"id": "a", "should_trigger": True}]
        assert trigger_pass_counts(runs, evals) == [("a", 2, 3)]

    def test_ignores_non_should_trigger_evals(self) -> None:
        runs = {"a": _runs(False)}
        evals = [{"id": "a", "should_trigger": False}]
        assert trigger_pass_counts(runs, evals) == []

    def test_returns_empty_when_no_evals(self) -> None:
        assert trigger_pass_counts({}, []) == []


class TestChecksSurviveOptimizedMode:
    """Guard the graded checks against regressing to bare `assert`.

    `trial_outcomes` grades each trial by catching `AssertionError`, so
    `_trigger_check` and `assert_pass_rate` must keep raising even under
    `python -O`, where `assert` statements are stripped from the bytecode.
    A bare `assert` would silently stop raising under `-O` and make every
    trial look like a pass. Each case runs in an `-O` subprocess (cwd set to
    the dir holding the `eval_utils` package so `-c` can import it) and
    asserts the check still raised.
    """

    def _raises_under_o(self, body: str) -> subprocess.CompletedProcess[str]:
        """Run `body` under `python -O`; it exits 0 iff the check raised."""
        return subprocess.run(
            [sys.executable, "-O", "-c", body],
            cwd=str(Path(eval_utils.__file__).parent.parent),
            capture_output=True,
            text=True,
        )

    def test_trigger_check_raises_under_o(self) -> None:
        proc = self._raises_under_o(
            "import eval_utils as e\n"
            "from eval_utils import EvalRun\n"
            "try:\n"
            "    e._trigger_check(EvalRun('t', '', False, ''))\n"
            "except AssertionError:\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit('did not raise under -O')\n"
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_assert_pass_rate_raises_under_o(self) -> None:
        proc = self._raises_under_o(
            "import eval_utils as e\n"
            "try:\n"
            "    e.assert_pass_rate([(0, 'bad')], min_pass=1, label='x')\n"
            "except AssertionError:\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit('did not raise under -O')\n"
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr