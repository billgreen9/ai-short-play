from __future__ import annotations

import json
from typing import Any

from langsmith import traceable

from app.llm import complete_with_tools
from app.models import SkillRecord, StepResult
from app.skills.runtime import SkillRuntime, set_runtime
from app.tools import openai_tools_and_handlers
from app.tools.registry import resolve_tools


def _build_prompt(skill: SkillRecord, user_input: str, artifacts: dict[str, Any]) -> str:
    artifact_text = json.dumps(artifacts, ensure_ascii=False, default=str) if artifacts else "{}"
    return (
        f"当前技能：{skill.skill_name}\n"
        f"技能说明：{skill.description}\n"
        f"用户输入：{user_input}\n"
        f"上游产物：{artifact_text}\n"
        "请完成当前技能。若已注册 function tools，需要结构化结果时调用 save_result。"
    )


@traceable(name="execute_skill", run_type="chain")
def execute_skill(
    skill: SkillRecord,
    *,
    user_input: str,
    run_id: str,
    step_index: int,
    artifacts: dict[str, Any],
) -> StepResult:
    tool_names = skill.tool_names()
    runtime = SkillRuntime(
        user_input=user_input,
        run_id=run_id,
        skill_name=skill.skill_name,
        artifacts=artifacts,
    )
    previous = set_runtime(runtime)
    try:
        tools = None
        handlers = None
        if tool_names:
            resolve_tools(skill.function_tools)
            tools, handlers = openai_tools_and_handlers(skill.function_tools)
        result = complete_with_tools(
            _build_prompt(skill, user_input, artifacts),
            system=skill.skill_prompt or None,
            tools=tools,
            handlers=handlers,
        )
        if result.get("error") and not result.get("content") and runtime.saved_result is None:
            return StepResult(
                skill_name=skill.skill_name,
                step_index=step_index,
                status="error",
                error=str(result["error"]),
                tools=tool_names,
            )
        output = runtime.saved_result or {"text": result.get("content") or ""}
        if result.get("tool_trace"):
            output = {**output, "tool_trace": result["tool_trace"]}
        return StepResult(
            skill_name=skill.skill_name,
            step_index=step_index,
            status="ok",
            output=output,
            tools=tool_names,
        )
    except Exception as exc:  # noqa: BLE001
        return StepResult(
            skill_name=skill.skill_name,
            step_index=step_index,
            status="error",
            error=str(exc),
            tools=tool_names,
        )
    finally:
        set_runtime(previous)
