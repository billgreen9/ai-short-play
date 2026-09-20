from __future__ import annotations

import json
from typing import Any

import httpx

from langsmith import traceable

from app.config import get_settings


def llm_enabled() -> bool:
    return bool(get_settings().openai_api_key)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().openai_api_key}",
        "Content-Type": "application/json",
    }


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=20.0) as client:
        response = client.post(url, headers=_headers(), json=payload)
        response.raise_for_status()
        return response.json()


@traceable(name="llm.complete", run_type="llm")
def complete(prompt: str, *, system: str | None = None, temperature: float = 0.4) -> str | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        data = _post_chat(
            {
                "model": settings.openai_model,
                "temperature": temperature,
                "messages": messages,
            }
        )
    except httpx.HTTPError:
        return None
    return data["choices"][0]["message"]["content"]


def complete_json(prompt: str, *, system: str | None = None) -> dict[str, Any] | None:
    text = complete(prompt, system=system, temperature=0.2)
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


@traceable(name="llm.complete_tool_args", run_type="llm")
def complete_tool_args(
    prompt: str,
    *,
    tool: dict[str, Any],
    system: str | None = None,
) -> dict[str, Any] | None:
    """让模型按 tool_schema 填参，返回 function.arguments。"""
    if not llm_enabled():
        return None
    settings = get_settings()
    name = tool["function"]["name"]
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        data = _post_chat(
            {
                "model": settings.openai_model,
                "temperature": 0.3,
                "messages": messages,
                "tools": [tool],
                "tool_choice": {"type": "function", "function": {"name": name}},
            }
        )
    except httpx.HTTPError:
        return None
    tool_calls = data["choices"][0]["message"].get("tool_calls") or []
    if not tool_calls:
        return None
    raw_args = tool_calls[0]["function"].get("arguments") or "{}"
    parsed = json.loads(raw_args)
    return parsed if isinstance(parsed, dict) else None
