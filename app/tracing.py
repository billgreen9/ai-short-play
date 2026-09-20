from __future__ import annotations

import os

from app.config import get_settings


def configure_tracing() -> None:
    """把 Settings 写入进程环境，LangGraph / langsmith 才能采到 trace。"""
    settings = get_settings()
    enabled = settings.langsmith_enabled
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if enabled else "false"
    if not enabled:
        return
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    if settings.langsmith_workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = settings.langsmith_workspace_id


def tracing_status_line() -> str:
    settings = get_settings()
    if not settings.langsmith_enabled:
        return "LangSmith tracing 未开启（需要 LANGSMITH_API_KEY 且 LANGSMITH_TRACING=true）"
    return (
        f"LangSmith tracing 已开启  project={settings.langsmith_project}  "
        "https://smith.langchain.com"
    )
