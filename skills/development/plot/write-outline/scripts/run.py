from __future__ import annotations

from typing import Any

from app.skills.heuristics import infer_title

BEATS = [
    ("被夺", "女主成果被抢，当众受辱"),
    ("反击萌芽", "她发现关键证据缺口"),
    ("假意示弱", "对手以为她已出局"),
    ("关键盟友", "男主第一次提供资源"),
    ("反转翻盘", "旧把柄被当众甩出"),
    ("更大危机", "真正幕后黑手出现"),
    ("对决", "女主用专业能力当众拆台"),
    ("新秩序", "位置对调，留下下一季钩子"),
]


def run(params: dict[str, Any]) -> dict[str, Any]:
    user_input = params["user_input"]
    artifacts = params.get("artifacts") or {}
    concept = artifacts.get("generate-concept") or {}
    title = concept.get("title") or infer_title(user_input)
    count = int(concept.get("episode_count") or 8)
    episodes = params.get("episodes")
    if not episodes:
        episodes = []
        for index, (beat, conflict) in enumerate(BEATS[:count], start=1):
            episodes.append(
                {
                    "episode": index,
                    "title": f"第{index}集 {beat}",
                    "beat": beat,
                    "conflict": conflict,
                    "hook": "集尾悬念必须让人滑到下一集",
                }
            )
    markdown = f"# 《{title}》大纲\n\n" + "\n".join(
        f"- {item['title']}：{item['conflict']}" for item in episodes
    )
    return {
        "episodes": episodes,
        "source": "llm" if params.get("episodes") else "template",
        "markdown": markdown,
    }
