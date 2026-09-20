from __future__ import annotations

from typing import Any

from app.skills.heuristics import parse_voice_swap


def run(params: dict[str, Any]) -> dict[str, Any]:
    ingest = (params.get("artifacts") or {}).get("ingest-source-video") or {}
    from_character = params.get("from_character")
    to_character = params.get("to_character")
    if not from_character or not to_character:
        from_character, to_character = parse_voice_swap(params["user_input"])
    source_url = ingest.get("source_url")
    return {
        "from_character": from_character,
        "to_character": to_character,
        "source_url": source_url,
        "media_job": {
            "action": "swap_voice",
            "source_url": source_url,
            "from_character": from_character,
            "to_character": to_character,
        },
        "markdown": f"作业：将「{from_character}」全部对白替换为「{to_character}」声线",
    }
