"""Unit tests for _helpers.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _helpers import (
    ClaudeRun,
    _assistant_content_blocks,
    _content_blocks_from_event,
    _is_assistant_event,
    _is_skill_hit,
    _message_from_event,
    _text_from_block,
    _try_parse_json,
    cache_path,
    load_cache,
    needs_skip,
    parse_stream_json,
    run_from_cache,
    serialise_runs,
    stripped_env,
    write_cache,
)


class TestTryParseJson:
    def test_valid_returns_dict(self) -> None:
        assert _try_parse_json('{"type": "assistant"}') == {"type": "assistant"}

    def test_invalid_returns_none(self) -> None:
        assert _try_parse_json("not json") is None

    def test_empty_line_returns_none(self) -> None:
        assert _try_parse_json("") is None

    def test_whitespace_stripped(self) -> None:
        assert _try_parse_json('  {"x": 1}  ') == {"x": 1}


class TestMessageFromEvent:
    def test_returns_msg_when_present(self) -> None:
        assert _message_from_event({"message": {"content": []}}) == {"content": []}

    def test_returns_empty_dict_when_key_absent(self) -> None:
        assert _message_from_event({}) == {}

    def test_returns_empty_dict_when_msg_none(self) -> None:
        assert _message_from_event({"message": None}) == {}


class TestIsAssistantEvent:
    def test_true_when_type_assistant(self) -> None:
        assert _is_assistant_event({"type": "assistant"})

    def test_false_when_type_other(self) -> None:
        assert not _is_assistant_event({"type": "user"})

    def test_false_when_type_missing(self) -> None:
        assert not _is_assistant_event({})


class TestContentBlocksFromEvent:
    def test_returns_content_list(self) -> None:
        ev = {"message": {"content": [{"type": "text", "text": "hi"}]}}
        assert _content_blocks_from_event(ev) == [{"type": "text", "text": "hi"}]

    def test_returns_empty_list_when_content_missing(self) -> None:
        assert _content_blocks_from_event({"message": {}}) == []

    def test_returns_empty_list_when_content_none(self) -> None:
        assert _content_blocks_from_event({"message": {"content": None}}) == []


class TestAssistantContentBlocks:
    def test_filters_to_assistant_only(self) -> None:
        events = [
            {"type": "user", "message": {"content": [{"type": "text", "text": "u"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "a"}]}},
        ]
        assert _assistant_content_blocks(events) == [{"type": "text", "text": "a"}]


class TestIsSkillHit:
    def test_matches_skill_name_in_input(self) -> None:
        block = {
            "name": "Skill",
            "input": {"skill": "dependency-injection"},
        }
        assert _is_skill_hit(block)

    def test_rejects_non_skill_tool(self) -> None:
        block = {"name": "Read", "input": {"skill": "dependency-injection"}}
        assert not _is_skill_hit(block)

    def test_rejects_wrong_skill_name(self) -> None:
        block = {"name": "Skill", "input": {"skill": "other-skill"}}
        assert not _is_skill_hit(block)


class TestTextFromBlock:
    def test_returns_text_when_type_text(self) -> None:
        assert _text_from_block({"type": "text", "text": "hello"}) == "hello"

    def test_returns_none_when_type_not_text(self) -> None:
        assert _text_from_block({"type": "tool_use"}) is None


class TestParseStreamJson:
    def test_no_skill_no_text(self) -> None:
        out = parse_stream_json("")
        assert out == (False, "", [])

    def test_detects_skill_invocation_and_text(self) -> None:
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": "dependency-injection"},
                        },
                        {"type": "text", "text": "did the thing"},
                    ]
                },
            }
        ]
        stdout = "\n".join(map(json.dumps, events))
        invoked, text, tools = parse_stream_json(stdout)
        assert invoked
        assert text == "did the thing"
        assert tools[0]["name"] == "Skill"

    def test_ignores_unparseable_lines(self) -> None:
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "ok"}]},
            }
        ]
        stdout = "garbage line\n" + "\n".join(map(json.dumps, events))
        invoked, text, _ = parse_stream_json(stdout)
        assert (invoked, text) == (False, "ok")


class TestStrippedEnv:
    def test_strips_claudecode_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("OTHER", "v")
        env = stripped_env()
        assert "CLAUDECODE" not in env
        assert env.get("OTHER") == "v"


class TestCachePath:
    def test_returns_path_when_set(self) -> None:
        assert cache_path("/tmp/x.json") == Path("/tmp/x.json")

    def test_returns_none_when_unset(self) -> None:
        assert cache_path(None) is None


class TestLoadCache:
    def test_empty_when_no_path(self) -> None:
        assert load_cache(None) == {}

    def test_empty_when_missing_file(self, tmp_path: Path) -> None:
        assert load_cache(str(tmp_path / "missing.json")) == {}

    def test_loads_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "c.json"
        f.write_text('{"a": {"skill_invoked": true, "assistant_text": "x"}}')
        assert load_cache(str(f)) == {
            "a": {"skill_invoked": True, "assistant_text": "x"}
        }


class TestRunFromCache:
    def test_constructs_with_cached_fields(self) -> None:
        run = run_from_cache(
            "id1",
            {"prompt": "p"},
            {
                "skill_invoked": True,
                "assistant_text": "out",
                "tool_uses": [{"name": "Read"}],
            },
        )
        assert (run.eval_id, run.prompt, run.skill_invoked) == ("id1", "p", True)
        assert run.assistant_text == "out"
        assert run.tool_uses == [{"name": "Read"}]


class TestSerialiseRuns:
    def test_serialises_and_omits_eval_id_and_prompt(self) -> None:
        runs = {
            "a": ClaudeRun(
                eval_id="a",
                prompt="hidden",
                skill_invoked=True,
                assistant_text="t",
            )
        }
        parsed = json.loads(serialise_runs(runs))
        assert parsed == {
            "a": {"skill_invoked": True, "assistant_text": "t", "tool_uses": []}
        }


class TestWriteCache:
    def test_noop_when_no_path(self) -> None:
        # Should not raise when path is None.
        write_cache(None, {})

    def test_writes_when_path_given(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        runs = {
            "a": ClaudeRun(
                eval_id="a", prompt="p", skill_invoked=False, assistant_text="t"
            )
        }
        write_cache(str(path), runs)
        assert json.loads(path.read_text()) == {
            "a": {"skill_invoked": False, "assistant_text": "t", "tool_uses": []}
        }


class TestNeedsSkip:
    def test_skips_when_marked_and_not_running(self) -> None:
        assert needs_skip(False, {"claude_eval": True})

    def test_does_not_skip_when_running(self) -> None:
        assert not needs_skip(True, {"claude_eval": True})

    def test_does_not_skip_when_unmarked(self) -> None:
        assert not needs_skip(False, {"other_marker": True})