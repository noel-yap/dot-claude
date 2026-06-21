# Skill evals

This directory holds one eval suite per skill, built on the
[**binom-eval**](https://github.com/noel-yap/binom-eval) package — the
skill-independent harness (Beta-binomial grading, the `claude -p` runner, the
stream-json parser, and a pytest plugin). Each skill adds a thin `evals/`
package that binds the harness to its own skill name, sample files, and
assertions.

`binom-eval` is a dependency, pinned in `requirements.txt`. Install it before
running anything:

```bash
make install   # uv pip install -r requirements.txt
```

This README explains how to stand up an eval suite for a **new skill**.

## What evals are (and aren't)

An eval runs the real `claude -p` CLI against a prompt, captures the
stream-json transcript, and checks the response with grep-style assertions.
The statistics behind the verdict — the Beta-binomial posterior, the target
rate, the adaptive trial loop — are binom-eval's job and are documented in
[its README](https://github.com/noel-yap/binom-eval); here we only cover what
a skill author has to write.

> Deterministic logic (your assertion helpers, regexes, parsing) belongs in
> ordinary unit tests, **not** in evals. Evals are only for "does the model,
> with this skill available, actually do the right thing often enough?"
>
> Evals are **expensive**: each trial is a real `claude -p` invocation that
> costs API tokens (and money) and takes seconds to minutes. They are isolated
> behind the `live_eval` marker (run only via `-m live_eval` / the `make eval`
> targets, never by the unit targets), so keep the eval set small and
> high-signal — anything checkable without the model belongs in the
> deterministic unit tests.

## How the `binom_eval` package fits together

`binom_eval` re-exports everything from its `__init__`, so you always
`from binom_eval import ...` regardless of which submodule a name lives in. The
full list of exported symbols is in binom-eval's
[Public API table](https://github.com/noel-yap/binom-eval#public-api); the
names a skill actually touches appear in the templates below.

The pytest hooks and the `live_eval_target_rate` fixture are registered
automatically by the installed `binom-eval` package (a pytest plugin via its
`pytest11` entry point), so the `--live-eval-max-trials` /
`--live-eval-target-rate` options and the `live_eval` marker are available
across the whole tree with no conftest wiring. **A new skill never touches the
`binom_eval` package** — it only adds files under its own `evals/`.

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
    ├── _helpers.py       # binds SKILL_NAME + paths, re-exports from binom_eval
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

from binom_eval import (
    EvalRun,
    assert_eval_passed,
    failing_assertions,
    parse_stream_json as _parse_stream_json,
    trial_outcomes,
    trigger_pass_counts,
)
from binom_eval import _is_skill_hit as _shared_is_skill_hit

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
Use `code_blocks`, `first_line`, and `missing_from` from `binom_eval` for
text wrangling.

```python
from __future__ import annotations

from ._helpers import EvalRun
from binom_eval import code_blocks, missing_from


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
Sibling modules are imported relatively (`from ._assertions import ...`);
paired with `consider_namespace_packages` in `skills/pytest.ini` this keeps
each skill's `_helpers` / `_assertions` namespaced, so several skills'
eval dirs can be collected in one pytest session without colliding.

```python
from __future__ import annotations

from ._assertions import ASSERTION_HANDLERS
from ._helpers import EVALS_PATH, REPO_ROOT, SKILL_NAME
from binom_eval import make_eval_runs_fixture

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
(provided by the `binom-eval` plugin).

```python
from __future__ import annotations

import json

import pytest

from ._assertions import ASSERTION_HANDLERS
from ._helpers import (
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
        from binom_eval import eval_passed

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
  `SKILL_NAME` (the shared functions are already tested in the binom-eval
  package's own suite, so don't re-test them).

## How grading works

The verdict is a Beta-binomial posterior over each assertion's true pass rate,
graded adaptively against a target rate (default **3/5**) over a trial budget
(default **21**). The model, the verdict band, and the reasoning behind every
default (`TARGET_RATE`, `MAX_TRIALS`, `BATCH_FLOOR`, the band, the prior, the
tiebreak) are documented in binom-eval's
[**Why these defaults**](https://github.com/noel-yap/binom-eval#why-these-defaults)
section. `TARGET_RATE` and `MAX_TRIALS` are overridable per run from the CLI /
Makefile (below); the rest are module constants in `binom_eval.grading`.

## Running

From `skills/` (a `Makefile` wraps the common cases):

```sh
make test                  # everything: unit tests then claude evals
make test-unit             # fast unit tests for all skills, no API calls
make eval                  # every skill's claude evals (target 3/5, <=21 runs)
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