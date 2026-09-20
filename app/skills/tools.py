from __future__ import annotations

from typing import Any

from app.models import SkillMeta


def normalize_tool(tool_schema: dict[str, Any], *, fallback_name: str, fallback_description: str) -> dict[str, Any]:
    if tool_schema.get("type") == "function" and isinstance(tool_schema.get("function"), dict):
        function = dict(tool_schema["function"])
    elif "name" in tool_schema and "parameters" in tool_schema:
        function = dict(tool_schema)
    else:
        raise ValueError(f"skill {fallback_name} 的 tool_schema.json 不是 OpenAI function 格式")
    function.setdefault("name", fallback_name.replace("-", "_"))
    function.setdefault("description", fallback_description)
    if not isinstance(function.get("parameters"), dict):
        raise ValueError(f"skill {fallback_name} 缺少 function.parameters")
    return {"type": "function", "function": function}


def assemble_openai_tools(skills: list[SkillMeta]) -> list[dict[str, Any]]:
    """调度层用：把各 skill 的 tool_schema.json 组装成 Chat Completions tools。"""
    tools: list[dict[str, Any]] = []
    for skill in skills:
        if skill.disable_model_invocation or not skill.tool_schema:
            continue
        tools.append(
            normalize_tool(
                skill.tool_schema,
                fallback_name=skill.name,
                fallback_description=skill.description,
            )
        )
    return tools


def tool_name_for(skill: SkillMeta) -> str:
    tool = normalize_tool(
        skill.tool_schema,
        fallback_name=skill.name,
        fallback_description=skill.description,
    )
    return str(tool["function"]["name"])
