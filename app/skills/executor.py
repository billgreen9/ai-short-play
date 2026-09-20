from __future__ import annotations

import json
from typing import Any

from langsmith import traceable

from app.llm import complete_with_tools
from app.models import SkillRecord, StepResult
from app.skills.runtime import SkillRuntime, set_runtime
from app.tools import openai_tools_and_handlers
from app.tools.registry import resolve_tools


def build_skill_messages(
    skill: SkillRecord,
    *,
    user_input: str,
    artifacts: dict[str, Any],
    has_tools: bool,
) -> list[dict[str, Any]]:
    """结构化 chat messages：用户原话单独作为 user，技能说明与上游产物放在 system。"""
    system_parts: list[str] = []
    if skill.skill_prompt.strip():
        system_parts.append(skill.skill_prompt.strip())
    system_parts.append(f"当前技能：{skill.skill_name}")
    if skill.description.strip():
        system_parts.append(f"技能说明：{skill.description.strip()}")
    if has_tools:
        system_parts.append(
            "已注册 function tools。需要结构化结果时调用 save_result；读取上游产物时调用 get_artifact。"
        )
    else:
        system_parts.append("请完成当前技能并直接给出结果。")
    if artifacts:
        system_parts.append(
            "上游产物（JSON）：\n" + json.dumps(artifacts, ensure_ascii=False, default=str)
        )
    return [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": user_input},
    ]


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
        messages = build_skill_messages(
            skill,
            user_input=user_input,
            artifacts=artifacts,
            has_tools=bool(tool_names),
        )
        result = complete_with_tools(
            messages,
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
        content = result.get("content")
        if runtime.saved_result is None and not (isinstance(content, str) and content.strip()):
            return StepResult(
                skill_name=skill.skill_name,
                step_index=step_index,
                status="error",
                error=str(result.get("error") or "大模型未返回内容"),
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
