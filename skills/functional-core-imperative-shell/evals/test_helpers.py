"""Unit tests for the SKILL_NAME-bound wrappers in `_helpers.py`.

The skill-independent helpers these delegate to live in `binom_eval` and
are tested once in the `binom-eval` package. Here we only verify that
this suite's wrappers bind the correct `SKILL_NAME`.
"""

from __future__ import annotations

import json

from ._helpers import SKILL_NAME, _is_skill_hit, parse_stream_json


class TestParseStreamJsonWrapper:
    def test_detects_this_skill(self) -> None:
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": SKILL_NAME},
                        },
                        {"type": "text", "text": "ok"},
                    ]
                },
            }
        )
        invoked, text, tools = parse_stream_json(line)
        assert invoked is True
        assert text == "ok"
        assert tools[0]["name"] == "Skill"

    def test_ignores_other_skill(self) -> None:
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": "other-skill"},
                        }
                    ]
                },
            }
        )
        invoked, _, _ = parse_stream_json(line)
        assert invoked is False


class TestIsSkillHitWrapper:
    def test_true_for_this_skill(self) -> None:
        block = {"name": "Skill", "input": {"skill": SKILL_NAME}}
        assert _is_skill_hit(block) is True

    def test_false_for_other_skill(self) -> None:
        block = {"name": "Skill", "input": {"skill": "other-skill"}}
        assert _is_skill_hit(block) is False
