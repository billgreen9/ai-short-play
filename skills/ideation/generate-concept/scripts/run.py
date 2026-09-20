from __future__ import annotations

from typing import Any

from app.skills.heuristics import infer_genre, infer_logline, infer_title


def run(params: dict[str, Any]) -> dict[str, Any]:
    user_input = params["user_input"]
    title = params.get("title") or infer_title(user_input)
    genre = params.get("genre") or infer_genre(user_input)
    logline = params.get("logline") or infer_logline(user_input)
    hook = params.get("hook") or f"开场 3 秒内抛出冲突：{user_input.strip()}"
    episode_count = int(params.get("episode_count") or 8)
    core_conflict = params.get("core_conflict") or "身份被否定后的反击与反转"
    source = "llm" if params.get("title") else "template"
    markdown = (
        f"# {title}\n\n"
        f"- 类型：{genre}\n"
        f"- 集数：{episode_count}\n"
        f"- Logline：{logline}\n"
        f"- 开场钩子：{hook}\n"
        f"- 核心冲突：{core_conflict}\n"
    )
    return {
        "title": title,
        "genre": genre,
        "logline": logline,
        "hook": hook,
        "episode_count": episode_count,
        "core_conflict": core_conflict,
        "audience": "竖屏短剧用户",
        "source": source,
        "markdown": markdown,
    }
