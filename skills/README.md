# Skill evals

This directory holds the **eval harness** shared by every skill plus one
eval suite per skill. The `eval_utils` package is the skill-independent
core; each skill adds a thin `evals/` package that binds the harness to its
own skill name, sample files, and assertions.

This README explains how to stand up an eval suite for a **new skill**.

## What evals are (and aren't)

An eval runs the real `claude -p` CLI against a prompt, captures the
stream-json transcript, and checks the response with grep-style assertions.
Because the model is non-deterministic, each assertion has an unknown true
pass rate `theta`; we estimate it Bayesianly from **repeated live runs** and
the assertion passes when the posterior puts most of its mass at or above a
target rate (default **2/3**). There is **no caching** — repeated trials are
the samples the posterior is built from.

> Deterministic logic (your assertion helpers, regexes, parsing) belongs in
> ordinary unit tests, **not** in evals. Evals are only for "does the model,
> with this skill available, actually do the right thing often enough?"
>
> Evals are **expensive**: each trial is a real `claude -p` invocation that
> costs API tokens (and money) and takes seconds to minutes, and every eval
> runs up to `--live-eval-max-trials` times (default 21). That is why they
> are isolated behind the `live_eval` marker (run only via `-m live_eval` /
> the `make eval` targets, never by the unit targets), why the harness runs
> trials adaptively (stopping as soon as the posterior locks PASS or FAIL)
> and concurrently, and why you should keep the eval set small and
> high-signal — a clearly-good or clearly-broken skill settles in a handful
> of trials, and anything checkable without the model belongs in the
> deterministic unit tests.

## How the `eval_utils` package fits together

`eval_utils` is a package whose `__init__` re-exports everything below, so
you always `from eval_utils import ...` regardless of which submodule a name
lives in. It provides, as plain functions (no per-skill state):

| Area | Submodule | What you use |
| --- | --- | --- |
| Run + parse | `runner`, `stream_json` | `run_claude`, `run_claude_batch`, `parse_stream_json`, `EvalRun` |
| Bayesian verdict | `grading` | `posterior_pass_prob`, `eval_passed` |
| Adaptive grading loop | `grading` | `run_eval_adaptive`, `next_batch_size` |
| Per-assertion scoring | `grading` | `trial_outcomes`, `assert_eval_passed`, `failing_assertions`, `trigger_pass_counts` |
| Assertion text helpers | `text_utils` | `code_blocks`, `first_line`, `missing_from` |
| pytest wiring | `plugin` | `pytest_addoption`, `pytest_configure`, `live_eval_target_rate`, `make_eval_runs_fixture` |

The pytest hooks and the `live_eval_target_rate` fixture are re-exported once
from the parent `skills/conftest.py`, so the `--live-eval-max-trials` /
`--live-eval-target-rate` options and the `live_eval` marker are registered
for the whole tree. **A new skill never
touches the `eval_utils` package or `skills/conftest.py`** — it only adds
files under its own `evals/`.

The one entry point a skill calls directly is **`make_eval_runs_fixture`**,
which builds the session-scoped `eval_runs` fixture that runs claude for
every eval and returns `{eval_id: [EvalRun, ...]}`.

## Directory layout for a new skill

```
skills/<skill-name>/
└── evals/
    ├── evals.json        # the eval cases + per-eval assertion ids
    ├── samples/          # input files the prompts point at
    │   └── *.ts
    ├── _helpers.py       # binds SKILL_NAME + paths, re-exports from eval_utils
    ├── _assertions.py    # assertion functions + ASSERTION_HANDLERS registry
    ├── conftest.py       # wires the `eval_runs` fixture
    ├── test_evals.py     # the live evals (marked `live_eval`; run via -m live_eval)
    ├── test_assertions.py# unit tests for _assertions.py (fast, deterministic)
    └── test_helpers.py   # unit tests for the SKILL_NAME-bound wrappers
```

> **Important:** every skill's `evals/` reuses the module names `_helpers`
> and `_assertions`. pytest cannot collect two skills' eval dirs in one
> session without a `sys.modules` collision — always run **one skill's eval
> dir at a time** (the `Makefile` targets do this for you).

## Step by step

### 1. `evals.json` — the cases

The skill identity is derived from the directory name (see `_helpers.py`
below), so `evals.json` holds only the cases:

```json
{
  "evals": [
    {
      "id": "descriptive-case-id",
      "should_trigger": true,
      "file": "skills/<skill-name>/evals/samples/example.ts",
      "prompt": "A realistic user request that points at the sample file ...",
      "expected_output": "Prose describing what a good response looks like (human reference; not asserted directly).",
      "assertions": [
        { "id": "some-assertion-id", "description": "What this assertion checks." }
      ]
    }
  ]
}
```

- `should_trigger: true` adds an automatic check that the skill's `Skill`
  tool actually fired. Use `should_trigger: false` for a "When NOT to use"
  case and add a `skill-not-invoked` assertion.
- Each `assertions[].id` must have a handler registered in `_assertions.py`
  (next step) — `load_evals` enforces this when the `eval_runs` fixture is
  built, raising a `KeyError` that names every gap before any trials run.
  `expected_output` is documentation only.
- Put the input files the prompt references under `samples/`.

### 2. `_helpers.py` — bind the skill identity

Copy this verbatim — nothing to edit. Both `REPO_ROOT` and the skill identity
(`SKILL_NAME`) are derived from this file's location (`evals/` is 3 levels
below the repo root, and its parent dir is the skill).

```python
"""Skill-specific bindings over the shared eval helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from eval_utils import (
    EvalRun,
    assert_eval_passed,
    failing_assertions,
    parse_stream_json as _parse_stream_json,
    trial_outcomes,
    trigger_pass_counts,
)
from eval_utils import _is_skill_hit as _shared_is_skill_hit

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[3]
EVALS_PATH = EVAL_DIR / "evals.json"
SKILL_NAME = EVAL_DIR.parent.name      # the skill dir is the source of truth


def parse_stream_json(stdout: str) -> tuple[bool, str, list[dict[str, Any]]]:
    return _parse_stream_json(stdout, SKILL_NAME)


def _is_skill_hit(block: dict[str, Any]) -> bool:
    return _shared_is_skill_hit(block, SKILL_NAME)


__all__ = [
    "EvalRun", "EVAL_DIR", "EVALS_PATH", "REPO_ROOT", "SKILL_NAME",
    "_is_skill_hit", "assert_eval_passed", "failing_assertions",
    "parse_stream_json", "trial_outcomes", "trigger_pass_counts",
]
```

### 3. `_assertions.py` — the checks

Each handler takes a `EvalRun` and **raises `AssertionError`** on failure
(its message becomes the per-trial failure detail). Register every handler in
an `ASSERTION_HANDLERS` dict keyed by the `assertion.id` from `evals.json`.
Use `code_blocks`, `first_line`, and `missing_from` from `eval_utils` for
text wrangling.

```python
from __future__ import annotations

from _helpers import EvalRun
from eval_utils import code_blocks, missing_from


def assert_does_the_thing(run: EvalRun) -> None:
    """Fail if the response is missing the required tokens."""
    missing = missing_from(("expectedToken",), run.assistant_text)
    assert not missing, f"response missing: {missing}"


def assert_skill_not_invoked(run: EvalRun) -> None:
    """For a should_trigger:false eval."""
    assert not run.skill_invoked, "skill fired on a When-NOT-to-use case"


ASSERTION_HANDLERS = {
    "some-assertion-id": assert_does_the_thing,
    "skill-not-invoked": assert_skill_not_invoked,
}
```

### 4. `conftest.py` — wire the fixture

Identical for every skill except the imports resolve to this skill's modules.

```python
from __future__ import annotations

import sys
from pathlib import Path

# Put this eval dir on sys.path so `_helpers` / `_assertions` import under
# pytest's importlib mode.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _assertions import ASSERTION_HANDLERS          # noqa: E402
from _helpers import EVALS_PATH, REPO_ROOT, SKILL_NAME  # noqa: E402
from eval_utils import make_eval_runs_fixture      # noqa: E402

eval_runs = make_eval_runs_fixture(
    EVALS_PATH, REPO_ROOT, SKILL_NAME, ASSERTION_HANDLERS
)
```

`make_eval_runs_fixture` returns a session-scoped fixture. For each eval it
runs `run_eval_adaptive`, which fires trials in concurrent batches and stops
as soon as the posterior locks PASS or FAIL, yielding
`{eval_id: [EvalRun, ...]}`.

### 5. `test_evals.py` — the live evals

Two tests, both marked `live_eval` (so the unit targets exclude them via
`-m "not live_eval"` and the eval targets select them via `-m live_eval`).
The target pass rate comes from the `live_eval_target_rate` fixture
(re-exported by the parent conftest).

```python
from __future__ import annotations

import json

import pytest

from _assertions import ASSERTION_HANDLERS
from _helpers import (
    EVALS_PATH, EvalRun, assert_eval_passed, failing_assertions,
    trial_outcomes, trigger_pass_counts,
)


class TestClaudeEvals:
    @staticmethod
    def _evals() -> list[dict]:
        return json.loads(EVALS_PATH.read_text(encoding="utf-8"))["evals"]

    @staticmethod
    def _assertion_params(evals: list[dict]) -> list[pytest.param]:
        return [
            pytest.param(ev["id"], a["id"], id=f"{ev['id']}::{a['id']}")
            for ev in evals
            for a in ev["assertions"]
        ]

    @pytest.mark.live_eval
    @pytest.mark.parametrize("eval_id,assertion_id", _assertion_params(_evals()))
    def test_eval_assertion(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_target_rate: float,
        eval_id: str,
        assertion_id: str,
    ) -> None:
        # eval_runs is built before this body runs, and that build validates
        # handler coverage -- so assertion_id always has a registered handler.
        handler = ASSERTION_HANDLERS[assertion_id]
        outcomes = trial_outcomes(eval_runs[eval_id], handler)
        assert_eval_passed(outcomes, live_eval_target_rate, f"{eval_id}::{assertion_id}")

    @pytest.mark.live_eval
    def test_should_trigger_evals_invoked_skill(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_target_rate: float,
    ) -> None:
        from eval_utils import eval_passed

        counts = trigger_pass_counts(eval_runs, self._evals())
        failures = [
            c for c in counts if not eval_passed(c[1], c[2], live_eval_target_rate)
        ]
        assert not failures, (
            "skill invoked below the bar "
            f"(P(rate >= {live_eval_target_rate:.3f}) must be >= 0.5): "
            + ", ".join(f"{eid}: {n}/{total}" for eid, n, total in failures)
        )
```

### 6. Unit tests (fast, no API)

- **`test_assertions.py`** — exercise each assertion handler against
  hand-written `EvalRun(assistant_text=...)` fixtures covering pass and
  fail cases. This is where the *deterministic* coverage lives.
- **`test_helpers.py`** — verify your `_helpers.py` wrappers bind the right
  `SKILL_NAME` (the shared functions are already tested in
  `skills/eval_utils/tests/`, so don't re-test them).

## How grading works

The model is a Beta-binomial: each assertion has an unknown true pass rate
`theta`; with a `Beta(1, 1)` prior and `k` passes of `n` trials the posterior
is `Beta(1 + k, 1 + (n - k))` (conjugate, so no sampling). `p_good` is the
posterior mass at or above the target rate, `P(theta >= target)`.

- `--live-eval-target-rate T` (default **2/3**): the true pass rate a good
  skill should clear. An assertion's final grade (`eval_passed`) is PASS when
  `p_good >= 0.5`.
- `--live-eval-max-trials N` (default **21**): the budget ceiling. The verdict
  usually locks long before this; it only bites for a skill sitting right at
  the target rate, which is genuinely undecidable.
- Trials run **adaptively** (`next_batch_size` → `run_eval_adaptive`). After
  each concurrent batch the posterior is re-checked against a symmetric band:
  PASS once `p_good > 1 - e^-2` (~0.865), FAIL once `p_good < e^-2` (~0.135),
  keep sampling in between. Batches are sized to the fewest trials that could
  settle the worst still-open check, floored at `BATCH_FLOOR` (3) so early
  rounds fan out and an unlucky streak can't lock a verdict. A clearly-good or
  clearly-broken skill settles in a handful of trials.

### Why these defaults

The defaults are tuned for the expected workload: **most eval runs are of
working skills in CI** (a broken skill gets fixed fast, so it's rarely the
thing under test). That makes the dominant failure mode a *false red* — a
working skill that the build rejects by chance — so the parameters are chosen
to keep that rare while still catching real regressions. The numbers below
are from Monte-Carlo simulation of the adaptive loop (budget 21, prior
`Beta(1, 1)`); "false-FAIL" is a good skill wrongly failed, "caught" is a
broken skill correctly failed.

- **`TARGET_RATE = 2/3`.** The bar must sit *below* where good skills actually
  live (~0.9+), because asking the posterior to distinguish 0.90 from a bar
  near it is both expensive and flaky. At 2/3 a true-0.90 skill false-fails
  ~3% of the time (true-0.95: <1%) while a true-0.50 skill is caught ~94% and
  true-0.40 ~99%. Pushing the bar to 0.7 roughly quadruples false reds on
  0.9 skills; dropping it to 0.5 leaks mildly-broken skills (0.4–0.5) through.
  2/3 is the knee of that trade — and "passes at least two of every three
  attempts" is an easy bar to explain.
- **Band `(e^-2, 1 - e^-2)` ≈ (0.135, 0.865).** Symmetric about ½, so an early
  unlucky streak is as hard to lock a FAIL on as a lucky one is to lock a PASS.
  `e^-2` is a natural "two-units-of-evidence" tail and pairs cleanly with the
  2/3 target. Raising the low edge (e.g. to 0.5, a FAIL-eager asymmetric band)
  was measured to ~10× the false-FAIL rate on good skills — rejected.
- **`BATCH_FLOOR = 3`.** Not just a concurrency knob — it's a *stability* knob.
  Flooring the opening salvo at 3 forces a representative sample before the
  posterior may commit, which cut false-FAIL ~3× versus a floor of 1 (e.g.
  12% → 4% at target 0.7, true 0.9) for ~2 extra trials. A floor of 2 was
  strictly worse (same cost, less benefit, and it could *raise* round counts);
  5 bought marginal speed at near-max trial cost. 3 is the sweet spot.
- **`MAX_TRIALS = 21`.** A ceiling, not a target: good skills lock in ~2–3
  rounds (~6–9 trials) and never approach it. It only bites for a skill
  sitting *exactly* at the bar, which is genuinely undecidable — one more
  trial can't rescue it. 21 = 3 × 7 divides evenly by `BATCH_FLOOR`, so the
  worst case is a clean seven rounds of three with no ragged final batch. The
  budget is the least sensitive parameter here (20 vs 21 was within noise).
- **Prior `Beta(1, 1)` (uniform).** No prior opinion on a skill's pass rate —
  the verdict is driven by the trials, not by a thumb on the scale. Raise
  `PRIOR_ALPHA` for an optimistic prior ("skills usually work, demand less
  evidence") or `PRIOR_BETA` for a skeptical one.
- **Budget tiebreak at `p_good >= 0.5`.** If a run exhausts the budget still
  inside the band, it's graded toward whichever side holds the majority of the
  posterior. This only matters for at-the-bar skills (everything else locks via
  the band first); 0.5 is the principled midpoint.

All of these are per-run overridable from the CLI / Makefile (`TARGET_RATE`,
`MAX_TRIALS`); the band, floor, prior, and tiebreak are module constants in
`eval_utils.grading` — change them there if the workload assumptions shift.

## Running

From `skills/` (a `Makefile` wraps the common cases):

```sh
make test                  # everything: unit tests then claude evals
make test-unit             # fast unit tests for all skills, no API calls
make test-shared           # just the shared eval_utils unit tests
make eval                  # every skill's claude evals (target 2/3, <=21 runs)
make eval-<skill-name>     # one skill's claude evals
make eval TARGET_RATE=0.8 MAX_TRIALS=12
```

Or call pytest directly (always **one** eval dir at a time). The
`live_eval` marker is the unit/eval split:

```sh
# fast unit tests for a skill (excludes the live_eval tests)
python3 -m pytest skills/<skill-name>/evals -m "not live_eval"

# live evals (requires the `claude` CLI on PATH; makes real model calls)
python3 -m pytest skills/<skill-name>/evals -m live_eval

# cheaper budget while iterating
python3 -m pytest skills/<skill-name>/evals -m live_eval \
    --live-eval-max-trials 6
```

With `-m "not live_eval"` the live evals are excluded, so the unit tests
(`test_assertions.py`, `test_helpers.py`) run fast and offline.

## Checklist for a new skill

1. `evals/evals.json` with cases + assertion ids (and `samples/`).
2. `_helpers.py` with `SKILL_NAME` set.
3. `_assertions.py` with one handler per assertion id + `ASSERTION_HANDLERS`.
4. `conftest.py` calling `make_eval_runs_fixture`.
5. `test_evals.py` (the two live tests above).
6. `test_assertions.py` + `test_helpers.py` (deterministic unit coverage).
7. `make eval-<skill-name>` passes; `make` (unit) stays green.