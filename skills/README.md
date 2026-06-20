# Skill evals

This directory holds the **eval harness** shared by every skill plus one
eval suite per skill. The `eval_utils` package is the skill-independent
core; each skill adds a thin `evals/` package that binds the harness to its
own skill name, sample files, and assertions.

This README explains how to stand up an eval suite for a **new skill**.

## What evals are (and aren't)

An eval runs the real `claude -p` CLI against a prompt, captures the
stream-json transcript, and checks the response with grep-style assertions.
Because the model is non-deterministic, every assertion is graded over
**repeated live runs** and must pass in at least `min_pass` of them. There
is **no caching** — repeated trials exist precisely to measure run-to-run
variance.

> Deterministic logic (your assertion helpers, regexes, parsing) belongs in
> ordinary unit tests, **not** in evals. Evals are only for "does the model,
> with this skill available, actually do the right thing often enough?"
>
> Evals are **expensive**: each trial is a real `claude -p` invocation that
> costs API tokens (and money) and takes seconds to minutes, and every eval
> runs up to `--live-eval-trials` times (default 8). A full suite is
> `evals × trials` live model calls. That is why they are isolated behind the
> `live_eval` marker (run only via `-m live_eval` / the `make eval`
> targets, never by the unit targets), why the harness runs trials adaptively
> (stopping as soon as the verdict is fixed) and concurrently, and why you
> should keep the eval set small and high-signal — lower
> `--live-eval-trials` while iterating, and push anything checkable without
> the model into the deterministic unit tests.

## How the `eval_utils` package fits together

`eval_utils` is a package whose `__init__` re-exports everything below, so
you always `from eval_utils import ...` regardless of which submodule a name
lives in. It provides, as plain functions (no per-skill state):

| Area | Submodule | What you use |
| --- | --- | --- |
| Run + parse | `runner`, `stream_json` | `run_claude`, `run_claude_batch`, `parse_stream_json`, `EvalRun` |
| Adaptive grading loop | `grading`, `plugin` | `run_eval_adaptive`, `next_batch_size`, `resolve_min_pass` |
| Per-assertion scoring | `grading` | `trial_outcomes`, `assert_pass_rate`, `trigger_pass_counts` |
| Assertion text helpers | `text_utils` | `code_blocks`, `first_line`, `missing_from` |
| pytest wiring | `plugin` | `pytest_addoption`, `pytest_configure`, `live_eval_min_pass`, `make_eval_runs_fixture` |

The pytest hooks and the `live_eval_min_pass` fixture are re-exported once
from the parent `skills/conftest.py`, so the `--live-eval-trials` /
`--live-eval-min-pass` options and the `live_eval` marker are registered
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
  (next step). `expected_output` is documentation only.
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
    assert_pass_rate,
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
    "_is_skill_hit", "assert_pass_rate", "parse_stream_json",
    "trial_outcomes", "trigger_pass_counts",
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
as soon as the verdict is fixed, yielding `{eval_id: [EvalRun, ...]}`.

### 5. `test_evals.py` — the live evals

Two tests, both marked `live_eval` (so the unit targets exclude them via
`-m "not live_eval"` and the eval targets select them via `-m live_eval`).
The grading threshold comes from the `live_eval_min_pass` fixture
(re-exported by the parent conftest).

```python
from __future__ import annotations

import json

import pytest

from _assertions import ASSERTION_HANDLERS
from _helpers import (
    EVALS_PATH, EvalRun, assert_pass_rate, trial_outcomes, trigger_pass_counts,
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
        live_eval_min_pass: int,
        eval_id: str,
        assertion_id: str,
    ) -> None:
        handler = ASSERTION_HANDLERS.get(assertion_id)
        assert handler is not None, f"no handler for {assertion_id!r} in _assertions.py"
        outcomes = trial_outcomes(eval_runs[eval_id], handler)
        assert_pass_rate(outcomes, live_eval_min_pass, f"{eval_id}::{assertion_id}")

    @pytest.mark.live_eval
    def test_should_trigger_evals_invoked_skill(
        self,
        eval_runs: dict[str, list[EvalRun]],
        live_eval_min_pass: int,
    ) -> None:
        counts = trigger_pass_counts(eval_runs, self._evals())
        failures = [c for c in counts if c[1] < live_eval_min_pass]
        assert not failures, (
            f"skill invoked below threshold (need >= {live_eval_min_pass}): "
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

- `--live-eval-trials N` (default **8**): max live runs per eval.
- `--live-eval-min-pass M` (default **`min(7, trials)`**): each assertion
  must pass in at least `M` trials. Leaving it unset and lowering `trials`
  keeps the threshold reachable (`resolve_min_pass`).
- Trials run **adaptively** (`next_batch_size` → `run_eval_adaptive`): the
  first batch is the `min_pass` passes a clean eval needs, run concurrently;
  after each batch the verdict is re-checked and the loop stops once every
  assertion has reached `min_pass` or one can no longer reach it. Cost is
  capped at `trials` and is often less.

## Running

From `skills/` (a `Makefile` wraps the common cases):

```sh
make test                  # everything: unit tests then claude evals
make test-unit             # fast unit tests for all skills, no API calls
make test-shared           # just the shared eval_utils unit tests
make eval                  # every skill's claude evals (8 trials, >=7 pass)
make eval-<skill-name>     # one skill's claude evals
make eval TRIALS=5 MIN_PASS=4
```

Or call pytest directly (always **one** eval dir at a time). The
`live_eval` marker is the unit/eval split:

```sh
# fast unit tests for a skill (excludes the live_eval tests)
python3 -m pytest skills/<skill-name>/evals -m "not live_eval"

# live evals (requires the `claude` CLI on PATH; makes real model calls)
python3 -m pytest skills/<skill-name>/evals -m live_eval

# fewer trials while iterating
python3 -m pytest skills/<skill-name>/evals -m live_eval \
    --live-eval-trials 3
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