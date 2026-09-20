from __future__ import annotations

from typing import Any

from app.skills.heuristics import infer_genre, infer_title

DEFAULT_CHARACTERS = [
    {"name": "林晚", "role": "女主", "want": "拿回被夺走的成果与体面", "wound": "被最信任的人背刺", "trait": "表面克制，下手极准"},
    {"name": "沈衡", "role": "男主", "want": "确认她不是自己看走眼的人", "wound": "被利益同盟利用过", "trait": "冷、观察型、关键时刻站队"},
    {"name": "许蔓", "role": "对手", "want": "顶替女主位置", "wound": "出身焦虑", "trait": "会演、会借力"},
]


def run(params: dict[str, Any]) -> dict[str, Any]:
    user_input = params["user_input"]
    concept = (params.get("artifacts") or {}).get("generate-concept") or {}
    title = concept.get("title") or infer_title(user_input)
    genre = concept.get("genre") or infer_genre(user_input)
    characters = params.get("characters") or DEFAULT_CHARACTERS
    relationships = params.get("relationships") or [
        "林晚与许蔓：同事/假姐妹，核心背叛线",
        "林晚与沈衡：对手戏拉扯，后期结盟",
    ]
    lines = [f"- {item['name']}（{item['role']}）：{item['trait']}；欲望：{item['want']}" for item in characters]
    markdown = f"# 《{title}》人物\n\n类型：{genre}\n\n" + "\n".join(lines) + "\n"
    return {
        "characters": characters,
        "relationships": relationships,
        "source": "llm" if params.get("characters") else "template",
        "markdown": markdown,
    }
