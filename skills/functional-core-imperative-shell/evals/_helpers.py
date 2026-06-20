"""Skill-specific bindings over the shared eval helpers.

Owns the path constants (`EVAL_DIR`, `REPO_ROOT`, `EVALS_PATH`) and derives
the skill identity (`SKILL_NAME`) from the skill directory, and re-exports
the handful of shared helpers this suite's tests use from `skills/eval_utils`
so the behaviour stays in one place.

`parse_stream_json` and `_is_skill_hit` are wrapped so callers can call
them with just the stream payload; the wrappers supply `SKILL_NAME`. The
skill-independent helpers are unit-tested once in `skills/eval_utils/tests/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval_utils import (
    EvalRun,
    assert_pass_rate,
    assertions_below_threshold,
    trial_outcomes,
    trigger_pass_counts,
)
from eval_utils import _is_skill_hit as _shared_is_skill_hit
from eval_utils import (
    parse_stream_json as _parse_stream_json,
)

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[3]
EVALS_PATH = EVAL_DIR / "evals.json"
# The skill directory (`evals/`'s parent) is the single source of truth for
# the skill identity: its name is what Claude loads and what `_is_skill_hit`
# matches against, so derive it rather than restating it here or in JSON.
SKILL_NAME = EVAL_DIR.parent.name


def parse_stream_json(stdout: str) -> tuple[bool, str, list[dict[str, Any]]]:
    return _parse_stream_json(stdout, SKILL_NAME)


def _is_skill_hit(block: dict[str, Any]) -> bool:
    return _shared_is_skill_hit(block, SKILL_NAME)


__all__ = [
    "EvalRun",
    "EVAL_DIR",
    "EVALS_PATH",
    "REPO_ROOT",
    "SKILL_NAME",
    "_is_skill_hit",
    "assert_pass_rate",
    "assertions_below_threshold",
    "parse_stream_json",
    "trial_outcomes",
    "trigger_pass_counts",
]
