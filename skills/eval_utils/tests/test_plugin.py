"""Unit tests for `eval_utils.plugin` (pytest wiring).

Covers `resolve_min_pass`, the pure threshold logic behind both the
batch-sizing and grading fixtures. The fixtures and pytest hooks themselves
are exercised by the per-skill eval suites that consume them.
"""

from __future__ import annotations

from eval_utils import resolve_min_pass


class TestResolveMinPass:
    def test_unset_defaults_to_seven_at_full_trials(self) -> None:
        assert resolve_min_pass(None, trials=8) == 7

    def test_unset_caps_at_trials_when_below_default(self) -> None:
        assert resolve_min_pass(None, trials=3) == 3
        assert resolve_min_pass(None, trials=1) == 1

    def test_explicit_value_is_used_as_given(self) -> None:
        assert resolve_min_pass(4, trials=5) == 4
        assert resolve_min_pass(7, trials=3) == 7  # explicit, even if > trials