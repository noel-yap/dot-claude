"""Shared helpers for per-skill eval suites.

Every skill under `skills/<name>/evals/` runs `claude -p` against its
`evals.json`, parses the stream-json output, and asserts refactor
quality. The skill-independent pieces live in this package, split by
concern:

  * `text_utils` -- pure text/regex helpers for per-skill `_assertions.py`
    (code-block extraction, the function-definition regexes, substring
    checks).
  * `stream_json` -- the `EvalRun` dataclass and `parse_stream_json`, which
    turn one `claude -p` run's stdout into an `EvalRun`.
  * `runner` -- the subprocess/env layer: `run_claude` and the concurrent
    `run_claude_batch`.
  * `grading` -- the adaptive trial driver (`next_batch_size`,
    `run_eval_adaptive`) plus the pass-rate rollups used to grade a batch.
  * `plugin` -- the pytest options, the `live_eval` marker, `resolve_min_pass`,
    and `make_eval_runs_fixture`.

This `__init__` re-exports the public surface so callers keep importing
`from eval_utils import ...` unchanged. Per-skill `_helpers.py` modules add
the parent directory to `sys.path` and re-export from here while supplying
their own `SKILL_NAME` and path constants; per-skill `_assertions.py`
modules import the shared regexes and text utilities; the parent
`skills/conftest.py` re-exports the pytest hooks and `live_eval_min_pass`.

Evals are inherently non-deterministic, so each is graded over repeated
live runs; there is deliberately no result caching (deterministic tests
belong in the per-skill unit suites, not here).

Stdlib + pytest only.
"""

from __future__ import annotations

from eval_utils.grading import (
    _check_failures,
    _eval_checks,
    _trigger_check,
    assert_pass_rate,
    assertions_below_threshold,
    load_evals,
    next_batch_size,
    run_eval_adaptive,
    trial_outcomes,
    trigger_pass_counts,
)
from eval_utils.plugin import (
    DEFAULT_MIN_PASS,
    DEFAULT_TRIALS,
    live_eval_min_pass,
    make_eval_runs_fixture,
    pytest_addoption,
    pytest_configure,
    resolve_min_pass,
)
from eval_utils.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    NESTED_SESSION_MARKERS,
    run_claude,
    run_claude_batch,
    stripped_env,
)
from eval_utils.stream_json import (
    EvalRun,
    _assistant_content_blocks,
    _content_blocks_from_event,
    _is_assistant_event,
    _is_skill_hit,
    _message_from_event,
    _text_from_block,
    _try_parse_json,
    parse_stream_json,
)
from eval_utils.text_utils import (
    ARROW_FN_RE,
    CODE_BLOCK_RE,
    NAMED_FN_RE,
    code_blocks,
    first_line,
    missing_from,
)

__all__ = [
    # text_utils
    "ARROW_FN_RE",
    "CODE_BLOCK_RE",
    "NAMED_FN_RE",
    "code_blocks",
    "first_line",
    "missing_from",
    # stream_json
    "EvalRun",
    "parse_stream_json",
    # runner
    "DEFAULT_TIMEOUT_SECONDS",
    "NESTED_SESSION_MARKERS",
    "run_claude",
    "run_claude_batch",
    "stripped_env",
    # grading
    "assert_pass_rate",
    "assertions_below_threshold",
    "load_evals",
    "next_batch_size",
    "run_eval_adaptive",
    "trial_outcomes",
    "trigger_pass_counts",
    # plugin
    "DEFAULT_MIN_PASS",
    "DEFAULT_TRIALS",
    "live_eval_min_pass",
    "make_eval_runs_fixture",
    "pytest_addoption",
    "pytest_configure",
    "resolve_min_pass",
]