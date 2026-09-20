from __future__ import annotations

import json
from typing import Any, Callable

import httpx
from langsmith import traceable

from app.config import get_settings

ToolHandler = Callable[[dict[str, Any]], Any]


def llm_enabled() -> bool:
    return bool(get_settings().openai_api_key)


def embedding_enabled() -> bool:
    settings = get_settings()
    return bool(settings.openai_api_key and settings.openai_embedding_model)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().openai_api_key}",
        "Content-Type": "application/json",
    }


def _timeout() -> float:
    return get_settings().llm_timeout_seconds


def _post(path: str, payload: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
    settings = get_settings()
    url = settings.openai_base_url.rstrip("/") + path
    with httpx.Client(timeout=timeout or _timeout()) as client:
        response = client.post(url, headers=_headers(), json=payload)
        response.raise_for_status()
        return response.json()


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/chat/completions", payload)


def message_text(message: dict[str, Any] | None) -> str | None:
    """豆包等模型经常 content=null，正文在 reasoning_content 或 content 数组里。"""
    if not message:
        return None
    text = _content_to_text(message.get("content"))
    if text:
        return text
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()
    return None


def _content_to_text(content: object) -> str | None:
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item)
            elif isinstance(item, dict):
                piece = item.get("text") or item.get("content")
                if isinstance(piece, str) and piece.strip():
                    parts.append(piece)
        if parts:
            return "\n".join(parts)
    return None


def _parse_embedding(data: dict[str, Any]) -> list[float] | None:
    items = data.get("data")
    if isinstance(items, dict):
        vector = items.get("embedding")
    elif isinstance(items, list) and items:
        vector = items[0].get("embedding")
    else:
        vector = None
    if not isinstance(vector, list):
        return None
    return [float(v) for v in vector]


def _embedding_requests(text: str, model: str) -> list[tuple[str, dict[str, Any]]]:
    openai_payload = {
        "model": model,
        "input": [text],
        "encoding_format": "float",
    }
    multimodal_payload = {
        "model": model,
        "input": [{"type": "text", "text": text}],
    }
    if "vision" in model.lower() or "multimodal" in model.lower():
        return [("/embeddings/multimodal", multimodal_payload), ("/embeddings", openai_payload)]
    return [("/embeddings", openai_payload), ("/embeddings/multimodal", multimodal_payload)]


@traceable(name="llm.embed", run_type="embedding")
def embed_text(text: str) -> list[float] | None:
    settings = get_settings()
    if not embedding_enabled() or not text.strip():
        return None
    for path, payload in _embedding_requests(text, settings.openai_embedding_model):
        try:
            data = _post(path, payload)
        except httpx.HTTPError:
            continue
        values = _parse_embedding(data)
        if values and len(values) == settings.embedding_dim:
            return values
    return None


@traceable(name="llm.complete", run_type="llm")
def complete(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.4,
    timeout: float | None = None,
) -> str | None:
    if not llm_enabled():
        return None
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        data = _post(
            "/chat/completions",
            {
                "model": get_settings().openai_model,
                "temperature": temperature,
                "messages": messages,
            },
            timeout=timeout,
        )
    except httpx.HTTPError:
        return None
    return message_text(data["choices"][0]["message"])


def complete_json(
    prompt: str,
    *,
    system: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any] | None:
    text = complete(prompt, system=system, temperature=0.1, timeout=timeout)
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
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


@traceable(name="llm.complete_with_tools", run_type="llm")
def complete_with_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    handlers: dict[str, ToolHandler] | None = None,
    temperature: float = 0.4,
) -> dict[str, Any]:
    """用结构化 messages 调用大模型；若注册了 function tools，则执行工具循环。"""
    if not llm_enabled():
        return {"content": None, "tool_trace": []}
    if not messages:
        return {"content": None, "tool_trace": [], "error": "messages 不能为空"}
    history: list[dict[str, Any]] = [dict(item) for item in messages]
    settings = get_settings()
    tool_trace: list[dict[str, Any]] = []
    payload_tools = tools or None
    for _ in range(settings.max_tool_rounds):
        payload: dict[str, Any] = {
            "model": settings.openai_model,
            "temperature": temperature,
            "messages": history,
        }
        if payload_tools:
            payload["tools"] = payload_tools
        try:
            data = _post_chat(payload)
        except httpx.HTTPError as exc:
            return {"content": None, "tool_trace": tool_trace, "error": str(exc)}
        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = message_text(message)
            if not content:
                return {
                    "content": None,
                    "tool_trace": tool_trace,
                    "error": "大模型未返回文本或 tool_calls（content 为 null）",
                }
            return {"content": content, "tool_trace": tool_trace}
        history.append(message)
        for call in tool_calls:
            function = call.get("function") or {}
            name = str(function.get("name") or "")
            raw_args = function.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}
            handler = (handlers or {}).get(name)
            if handler is None:
                result: Any = {"error": f"未注册的 function tool: {name}"}
            else:
                try:
                    result = handler(args if isinstance(args, dict) else {})
                except Exception as exc:  # noqa: BLE001
                    result = {"error": str(exc)}
            tool_trace.append({"name": name, "arguments": args, "result": result})
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    return {"content": None, "tool_trace": tool_trace, "error": "工具调用轮次超限"}
