import pytest

from app.models import SkillRecord
from app.skills.executor import execute_skill
from app.tools import list_tool_names, resolve_tools


def test_builtin_tools_are_registered():
    names = set(list_tool_names())
    assert {"get_artifact", "list_artifacts", "save_result"} <= names


def test_resolve_unknown_tool_raises():
    with pytest.raises(ValueError, match="未注册"):
        resolve_tools("not_a_tool")


def test_execute_registers_function_tools(monkeypatch):
    captured: dict = {}

    def fake_complete_with_tools(prompt, *, system, tools, handlers, temperature=0.4):
        captured["tools"] = [item["function"]["name"] for item in (tools or [])]
        captured["system"] = system
        assert handlers is not None
        handlers["save_result"]({"result": {"title": "职场复仇"}})
        return {"content": "ok", "tool_trace": [{"name": "save_result"}]}

    monkeypatch.setattr("app.skills.executor.complete_with_tools", fake_complete_with_tools)
    skill = SkillRecord(
        id=1,
        skill_name="generate_concept",
        description="生成概念",
        skill_prompt="你是创意编辑",
        function_tools="save_result",
    )
    step = execute_skill(skill, user_input="写短剧", run_id="r1", step_index=0, artifacts={})
    assert captured["tools"] == ["save_result"]
    assert captured["system"] == "你是创意编辑"
    assert step.status == "ok"
    assert step.output["title"] == "职场复仇"


def test_execute_skips_tools_when_empty(monkeypatch):
    captured: dict = {}

    def fake_complete_with_tools(prompt, *, system, tools, handlers, temperature=0.4):
        captured["tools"] = tools
        return {"content": "纯文本结果", "tool_trace": []}

    monkeypatch.setattr("app.skills.executor.complete_with_tools", fake_complete_with_tools)
    skill = SkillRecord(id=2, skill_name="plain", skill_prompt="直接回答", function_tools="")
    step = execute_skill(skill, user_input="你好", run_id="r1", step_index=0, artifacts={})
    assert captured["tools"] is None
    assert step.output["text"] == "纯文本结果"
