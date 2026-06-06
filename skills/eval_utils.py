"""Shared helpers for per-skill eval suites.

Every skill under `skills/<name>/evals/` runs `claude -p` against its
`evals.json`, parses the stream-json output, and asserts refactor
quality. The pieces that don't depend on the specific skill — the
`ClaudeRun` dataclass, stream-json parsing, the cache, the pytest hooks
that register `--run-claude` / `--claude-eval-cache`, and the
session-scoped fixture that runs claude once per eval — live here.

Per-skill `_helpers.py` modules add this directory to `sys.path` and
re-export from `eval_utils` while supplying their own `SKILL_NAME` and
path constants. Per-skill `_assertions.py` modules import the shared
regexes and small text utilities from here too. The parent
`skills/conftest.py` re-exports the pytest hooks from this module.

Stdlib + pytest only.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

DEFAULT_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Data class for a single claude -p run
# ---------------------------------------------------------------------------


@dataclass
class ClaudeRun:
    eval_id: str
    prompt: str
    skill_invoked: bool
    assistant_text: str
    tool_uses: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# stream-json parsing
# ---------------------------------------------------------------------------


def _try_parse_json(line: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    with contextlib.suppress(json.JSONDecodeError, ValueError, AttributeError):
        result = json.loads(line.strip())
    return result


def _is_assistant_event(ev: dict[str, Any]) -> bool:
    return ev.get("type") == "assistant"


def _message_from_event(ev: dict[str, Any]) -> dict[str, Any]:
    msg = ev.get("message")
    return msg if msg is not None else {}


def _content_blocks_from_event(ev: dict[str, Any]) -> list[dict[str, Any]]:
    content = _message_from_event(ev).get("content")
    return content if content else []


def _assistant_content_blocks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assistant_events = filter(_is_assistant_event, events)
    return [b for ev in assistant_events for b in _content_blocks_from_event(ev)]


def _is_skill_hit(block: dict[str, Any], skill_name: str) -> bool:
    return all([
        block.get("name") == "Skill",
        skill_name in str(block.get("input", {})),
    ])


def _text_from_block(block: dict[str, Any]) -> str | None:
    return block.get("text", "") if block.get("type") == "text" else None


def parse_stream_json(
    stdout: str, skill_name: str
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Parse `claude -p --output-format stream-json` stdout into
    (skill_invoked, assistant_text, tool_uses)."""
    events = list(filter(None, map(_try_parse_json, stdout.splitlines())))
    blocks = _assistant_content_blocks(events)
    skill_invoked = any(_is_skill_hit(b, skill_name) for b in blocks)
    text = "\n".join(filter(None, map(_text_from_block, blocks)))
    tool_uses = list(filter(lambda b: b.get("type") == "tool_use", blocks))
    return skill_invoked, text, tool_uses


# ---------------------------------------------------------------------------
# Environment + cache helpers
# ---------------------------------------------------------------------------


def stripped_env() -> dict[str, str]:
    return dict(filter(lambda kv: kv[0] != "CLAUDECODE", os.environ.items()))


def cache_path(cache_path_str: str | None) -> Path | None:
    return Path(cache_path_str) if cache_path_str else None


def load_cache(cache_path_str: str | None) -> dict[str, Any]:
    path = cache_path(cache_path_str)
    exists = path.is_file() if path else False
    raw = path.read_text(encoding="utf-8") if exists else None
    return json.loads(raw) if raw else {}


def run_from_cache(eid: str, item: dict[str, Any], entry: dict[str, Any]) -> ClaudeRun:
    return ClaudeRun(
        eval_id=eid,
        prompt=item["prompt"],
        skill_invoked=entry["skill_invoked"],
        assistant_text=entry["assistant_text"],
        tool_uses=entry.get("tool_uses", []),
    )


def serialise_runs(runs: dict[str, ClaudeRun]) -> str:
    return json.dumps(
        {
            eid: {
                "skill_invoked": r.skill_invoked,
                "assistant_text": r.assistant_text,
                "tool_uses": r.tool_uses,
            }
            for eid, r in runs.items()
        },
        indent=2,
    )


def write_cache(cache_path_str: str | None, runs: dict[str, ClaudeRun]) -> None:
    path = cache_path(cache_path_str)
    writer = path.write_text if path else (lambda *a, **kw: None)
    writer(serialise_runs(runs), encoding="utf-8")


def needs_skip(run_claude: bool, item_keywords: Any) -> bool:
    return all([not run_claude, "claude_eval" in item_keywords])


# ---------------------------------------------------------------------------
# Shared text/regex utilities for per-skill `_assertions.py`
# ---------------------------------------------------------------------------

CODE_BLOCK_RE = re.compile(r"```(?:ts|typescript)?\n(.*?)```", re.DOTALL)
NAMED_FN_RE = re.compile(r"\bfunction\s+(\w+)\s*\(")
ARROW_FN_RE = re.compile(
    r"\bconst\s+(\w+)\s*(?::[^=]+)?=\s*(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"
)


def code_blocks(text: str) -> list[str]:
    """Extract bodies of fenced ```ts / ```typescript / ``` code blocks."""
    return CODE_BLOCK_RE.findall(text)


def first_line(block: str) -> str:
    """First non-empty line of `block`, capped at 80 chars for assertion messages."""
    return next(iter(block.strip().splitlines()), "")[:80]


def missing_from(needles: tuple[str, ...], haystack: str) -> list[str]:
    """Return the needles absent from haystack, in original order."""
    return list(filter(lambda n: n not in haystack, needles))


# ---------------------------------------------------------------------------
# claude -p runner
# ---------------------------------------------------------------------------


def run_claude(
    prompt: str,
    repo_root: Path,
    skill_name: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ClaudeRun:
    """Invoke `claude -p` once and parse its stream-json output."""
    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--dangerously-skip-permissions",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env=stripped_env(),
        timeout=timeout,
    )
    skill_invoked, assistant_text, tool_uses = parse_stream_json(proc.stdout, skill_name)
    return ClaudeRun(
        eval_id="",
        prompt=prompt,
        skill_invoked=skill_invoked,
        assistant_text=assistant_text,
        tool_uses=tool_uses,
    )


def run_or_load(
    item: dict[str, Any],
    cache: dict[str, Any],
    repo_root: Path,
    skill_name: str,
) -> ClaudeRun:
    eid = item["id"]
    cached = cache.get(eid)
    run = (
        run_from_cache(eid, item, cached)
        if cached
        else run_claude(item["prompt"], repo_root, skill_name)
    )
    run.eval_id = eid
    return run


def load_evals(evals_path: Path) -> list[dict[str, Any]]:
    return json.loads(evals_path.read_text(encoding="utf-8"))["evals"]


# ---------------------------------------------------------------------------
# pytest hooks (re-exported by `skills/conftest.py`)
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-claude",
        action="store_true",
        default=False,
        help=(
            "Run end-to-end claude -p evals against the skills. Requires the "
            "`claude` CLI on PATH; each eval makes a real model call."
        ),
    )
    parser.addoption(
        "--claude-eval-cache",
        action="store",
        default=None,
        help=(
            "Optional path. If set and exists, claude outputs are loaded from "
            "it instead of re-running. After the run, fresh outputs are "
            "written back."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "claude_eval: end-to-end test that invokes `claude -p`; needs --run-claude.",
    )


def _apply_skip(item: pytest.Item, marker: pytest.MarkDecorator) -> None:
    item.add_marker(marker)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_claude = config.getoption("--run-claude")
    skip = pytest.mark.skip(reason="needs --run-claude")
    to_skip = filter(lambda item: needs_skip(run_claude, item.keywords), items)
    list(map(lambda item: _apply_skip(item, skip), to_skip))


# ---------------------------------------------------------------------------
# Fixture factory
# ---------------------------------------------------------------------------


def make_claude_runs_fixture(
    evals_path: Path, repo_root: Path, skill_name: str
) -> Callable[..., dict[str, ClaudeRun]]:
    """Build a session-scoped pytest fixture that runs claude -p once per
    eval in `evals_path` and caches the parsed output for the session.

    Per-skill conftest.py binds the returned fixture to the name
    `claude_runs` so per-skill `test_evals.py` can request it directly.
    """

    @pytest.fixture(scope="session")
    def claude_runs(pytestconfig: pytest.Config) -> dict[str, ClaudeRun]:
        pytest.skip("claude CLI not found on PATH") if shutil.which("claude") is None else None
        cache_path_str = pytestconfig.getoption("--claude-eval-cache")
        cache = load_cache(cache_path_str)
        runs = {
            item["id"]: run_or_load(item, cache, repo_root, skill_name)
            for item in load_evals(evals_path)
        }
        write_cache(cache_path_str, runs)
        return runs

    return claude_runs