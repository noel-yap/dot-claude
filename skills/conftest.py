"""Parent conftest for all skills under `skills/`.

Two responsibilities:
  1. Add this directory to `sys.path` so descendant test modules
     (per-skill `_helpers.py`, `_assertions.py`, `conftest.py`,
     `test_*.py`) can `from eval_utils import ...` and `from test_utils
     import ...` without each one fiddling with `sys.path` itself.
  2. Re-export the pytest hooks (`pytest_addoption`,
     `pytest_configure`) and the session-scoped `live_eval_target_rate`
     fixture from `eval_utils` so the `--live-eval-max-trials` /
     `--live-eval-target-rate` options and the `live_eval` marker are
     registered exactly once for the whole skills tree, regardless of which
     subset of skills pytest is pointed at.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_utils import (  # noqa: E402, F401
    live_eval_target_rate,
    pytest_addoption,
    pytest_configure,
)
