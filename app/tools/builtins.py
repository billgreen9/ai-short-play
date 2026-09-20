from __future__ import annotations

from typing import Any

from app.skills.runtime import get_runtime
from app.tools.registry import FunctionTool, register_tool


def _get_artifact(args: dict[str, Any]) -> Any:
    name = str(args.get("skill_name") or "")
    runtime = get_runtime()
    if not name:
        return {"available": sorted(runtime.artifacts)}
    if name not in runtime.artifacts:
        return {"error": f"没有名为 {name} 的上游产物", "available": sorted(runtime.artifacts)}
    return runtime.artifacts[name]


def _list_artifacts(_args: dict[str, Any]) -> Any:
    runtime = get_runtime()
    return {"skill_names": sorted(runtime.artifacts)}


def _save_result(args: dict[str, Any]) -> Any:
    runtime = get_runtime()
    payload = args.get("result")
    if not isinstance(payload, dict):
        raise ValueError("save_result.result 必须是对象")
    runtime.saved_result = payload
    return {"ok": True, "keys": sorted(payload)}


register_tool(
    FunctionTool(
        name="get_artifact",
        description="读取上游已执行 skill 的产物。不传 skill_name 时返回可用名称列表。",
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "上游 skill_name，例如 generate_concept",
                }
            },
        },
        handler=_get_artifact,
    )
)
register_tool(
    FunctionTool(
        name="list_artifacts",
        description="列出当前任务里已经产出的上游 skill 名称。",
        parameters={"type": "object", "properties": {}},
        handler=_list_artifacts,
    )
)
register_tool(
    FunctionTool(
        name="save_result",
        description="把当前 skill 的结构化结果保存下来，供下游 skill 使用。",
        parameters={
            "type": "object",
            "required": ["result"],
            "properties": {
                "result": {
                    "type": "object",
                    "description": "当前技能的结构化输出",
                }
            },
        },
        handler=_save_result,
    )
)
