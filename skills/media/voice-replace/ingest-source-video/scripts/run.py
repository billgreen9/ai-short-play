from __future__ import annotations

from typing import Any

from app.skills.heuristics import parse_video_url, parse_voice_swap


def run(params: dict[str, Any]) -> dict[str, Any]:
    source_url = params.get("source_url") or parse_video_url(params["user_input"])
    characters = params.get("characters")
    if not characters:
        from_character, to_character = parse_voice_swap(params["user_input"])
        characters = [from_character, to_character]
    tracks = [{"character": name, "type": "dialogue"} for name in characters]
    return {
        "source_url": source_url,
        "tracks": tracks,
        "media_job": {"action": "ingest", "source_url": source_url},
        "markdown": f"登记源视频 `{source_url}`，音轨角色：{'、'.join(characters)}",
    }
