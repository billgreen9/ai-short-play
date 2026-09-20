from __future__ import annotations

from typing import Any, Callable

from app.models import parse_csv

ToolHandler = Callable[[dict[str, Any]], Any]


class FunctionTool:
    def __init__(self, name: str, description: str, parameters: dict[str, Any], handler: ToolHandler):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, FunctionTool] = {}


def register_tool(tool: FunctionTool) -> FunctionTool:
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> FunctionTool | None:
    return _REGISTRY.get(name)


def list_tool_names() -> list[str]:
    return sorted(_REGISTRY)


def resolve_tools(raw: str | None) -> list[FunctionTool]:
    names = parse_csv(raw)
    missing = [name for name in names if name not in _REGISTRY]
    if missing:
        available = ", ".join(list_tool_names()) or "(无)"
        raise ValueError(f"未注册的 function tools: {', '.join(missing)}；当前可用: {available}")
    return [_REGISTRY[name] for name in names]


def openai_tools_and_handlers(raw: str | None) -> tuple[list[dict[str, Any]], dict[str, ToolHandler]]:
    tools = resolve_tools(raw)
    schemas = [tool.openai_schema() for tool in tools]
    handlers = {tool.name: tool.handler for tool in tools}
    return schemas, handlers
