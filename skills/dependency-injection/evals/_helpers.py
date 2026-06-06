"""Skill-specific bindings over the shared eval helpers.

Owns the path constants (`EVAL_DIR`, `REPO_ROOT`, `EVALS_PATH`) and the
skill identifier (`SKILL_NAME`) for the dependency-injection eval
suite. Everything else is re-exported from `skills/eval_utils` so
the underlying behaviour stays in one place.

`parse_stream_json` is wrapped so callers can keep calling it with just
the stdout string; the wrapper supplies `SKILL_NAME`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval_utils import (
    ClaudeRun,
    DEFAULT_TIMEOUT_SECONDS,
    cache_path,
    load_cache,
    needs_skip,
    parse_stream_json as _parse_stream_json,
    run_from_cache,
    serialise_runs,
    stripped_env,
    write_cache,
)
from eval_utils import (
    _assistant_content_blocks,
    _content_blocks_from_event,
    _is_assistant_event,
    _is_skill_hit as _shared_is_skill_hit,
    _message_from_event,
    _text_from_block,
    _try_parse_json,
)

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[3]
EVALS_PATH = EVAL_DIR / "evals.json"
SKILL_NAME = "dependency-injection"


def parse_stream_json(stdout: str) -> tuple[bool, str, list[dict[str, Any]]]:
    return _parse_stream_json(stdout, SKILL_NAME)


def _is_skill_hit(block: dict[str, Any]) -> bool:
    return _shared_is_skill_hit(block, SKILL_NAME)


__all__ = [
    "ClaudeRun",
    "DEFAULT_TIMEOUT_SECONDS",
    "EVAL_DIR",
    "EVALS_PATH",
    "REPO_ROOT",
    "SKILL_NAME",
    "_assistant_content_blocks",
    "_content_blocks_from_event",
    "_is_assistant_event",
    "_is_skill_hit",
    "_message_from_event",
    "_text_from_block",
    "_try_parse_json",
    "cache_path",
    "load_cache",
    "needs_skip",
    "parse_stream_json",
    "run_from_cache",
    "serialise_runs",
    "stripped_env",
    "write_cache",
]