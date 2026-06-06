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

    def test_returns_empty_dict_when_message_is_none(self) -> None:
        assert _message_from_event({"message": None}) == {}


class TestIsAssistantEvent:
    def test_true_when_type_matches(self) -> None:
        assert _is_assistant_event({"type": "assistant"}) is True

    def test_false_when_type_differs(self) -> None:
        assert _is_assistant_event({"type": "tool_result"}) is False

    def test_false_when_type_missing(self) -> None:
        assert _is_assistant_event({}) is False


class TestContentBlocksFromEvent:
    def test_returns_content_when_present(self) -> None:
        blocks = [{"type": "text"}]
        ev = {"message": {"content": blocks}}
        assert _content_blocks_from_event(ev) == blocks

    def test_returns_empty_when_content_none(self) -> None:
        assert _content_blocks_from_event({"message": {"content": None}}) == []

    def test_returns_empty_when_message_missing(self) -> None:
        assert _content_blocks_from_event({}) == []


class TestIsSkillHit:
    def test_both_conditions_met(self) -> None:
        block = {"name": "Skill", "input": {"skill": "functional-core-imperative-shell"}}
        assert _is_skill_hit(block) is True

    def test_wrong_name_false(self) -> None:
        block = {"name": "Read", "input": {"skill": "functional-core-imperative-shell"}}
        assert _is_skill_hit(block) is False

    def test_skill_name_absent_from_input_false(self) -> None:
        block = {"name": "Skill", "input": {"skill": "other-skill"}}
        assert _is_skill_hit(block) is False


class TestTextFromBlock:
    def test_returns_text_when_type_text(self) -> None:
        assert _text_from_block({"type": "text", "text": "hello"}) == "hello"

    def test_returns_none_when_not_text_type(self) -> None:
        assert _text_from_block({"type": "tool_use", "text": "hello"}) is None

    def test_returns_empty_string_when_text_key_absent(self) -> None:
        assert _text_from_block({"type": "text"}) == ""


class TestAssistantContentBlocks:
    def test_returns_only_assistant_blocks(self) -> None:
        events = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
            {"type": "tool_result", "message": {"content": [{"type": "text", "text": "x"}]}},
        ]
        assert _assistant_content_blocks(events) == [{"type": "text", "text": "hi"}]

    def test_empty_events_returns_empty(self) -> None:
        assert _assistant_content_blocks([]) == []


class TestParseStreamJson:
    def test_detects_skill_invocation(self) -> None:
        line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": "functional-core-imperative-shell"},
                }]
            },
        })
        skill_invoked, _, tool_uses = parse_stream_json(line)
        assert skill_invoked is True
        assert len(tool_uses) == 1

    def test_collects_text(self) -> None:
        line = json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hello world"}]},
        })
        _, text, _ = parse_stream_json(line)
        assert "hello world" in text

    def test_no_skill_returns_false(self) -> None:
        line = json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "plain reply"}]},
        })
        skill_invoked, _, _ = parse_stream_json(line)
        assert skill_invoked is False

    def test_skips_invalid_lines(self) -> None:
        stdout = "not json\n" + json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "ok"}]},
        })
        _, text, _ = parse_stream_json(stdout)
        assert "ok" in text


class TestStrippedEnv:
    def test_removes_claudecode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("HOME", "/home/test")
        env = stripped_env()
        assert "CLAUDECODE" not in env
        assert "HOME" in env

    def test_passes_through_non_claudecode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.setenv("MY_VAR", "val")
        assert "MY_VAR" in stripped_env()


class TestCachePath:
    def test_returns_path_when_str_given(self) -> None:
        assert cache_path("/tmp/cache.json") == Path("/tmp/cache.json")

    def test_returns_none_when_none_given(self) -> None:
        assert cache_path(None) is None


class TestLoadCache:
    def test_returns_empty_when_no_path(self) -> None:
        assert load_cache(None) == {}

    def test_returns_empty_when_file_absent(self, tmp_path: Path) -> None:
        assert load_cache(str(tmp_path / "missing.json")) == {}

    def test_returns_parsed_json_when_file_exists(self, tmp_path: Path) -> None:
        p = tmp_path / "cache.json"
        p.write_text('{"a": {"skill_invoked": true, "assistant_text": "x", "tool_uses": []}}')
        assert load_cache(str(p)) == {
            "a": {"skill_invoked": True, "assistant_text": "x", "tool_uses": []}
        }


class TestRunFromCache:
    def test_builds_clauderun(self) -> None:
        item = {"id": "ev1", "prompt": "do thing"}
        entry = {"skill_invoked": True, "assistant_text": "result", "tool_uses": []}
        run = run_from_cache("ev1", item, entry)
        assert run.eval_id == "ev1"
        assert run.prompt == "do thing"
        assert run.skill_invoked is True
        assert run.assistant_text == "result"
        assert run.tool_uses == []

    def test_uses_entry_tool_uses_when_present(self) -> None:
        item = {"id": "ev2", "prompt": "p"}
        entry = {"skill_invoked": False, "assistant_text": "", "tool_uses": [{"name": "Read"}]}
        run = run_from_cache("ev2", item, entry)
        assert run.tool_uses == [{"name": "Read"}]


class TestSerialiseAndWriteCache:
    def test_serialise_runs_produces_valid_json(self) -> None:
        runs = {
            "e1": ClaudeRun(
                eval_id="e1", prompt="p", skill_invoked=False,
                assistant_text="t", tool_uses=[],
            )
        }
        data = json.loads(serialise_runs(runs))
        assert data["e1"]["skill_invoked"] is False
        assert data["e1"]["assistant_text"] == "t"

    def test_write_cache_noop_when_no_path(self) -> None:
        runs = {"e1": ClaudeRun(eval_id="e1", prompt="", skill_invoked=False, assistant_text="")}
        write_cache(None, runs)

    def test_write_cache_writes_file(self, tmp_path: Path) -> None:
        p = tmp_path / "out.json"
        runs = {"e1": ClaudeRun(eval_id="e1", prompt="p", skill_invoked=True, assistant_text="a")}
        write_cache(str(p), runs)
        data = json.loads(p.read_text())
        assert data["e1"]["skill_invoked"] is True


class TestNeedsSkip:
    def test_true_when_not_run_claude_and_keyword_present(self) -> None:
        assert needs_skip(False, {"claude_eval"}) is True

    def test_false_when_run_claude_true(self) -> None:
        assert needs_skip(True, {"claude_eval"}) is False

    def test_false_when_keyword_absent(self) -> None:
        assert needs_skip(False, set()) is False

    def test_false_when_both_conditions_false(self) -> None:
        assert needs_skip(True, set()) is False