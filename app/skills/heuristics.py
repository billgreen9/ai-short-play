from __future__ import annotations

import re


GENRE_HINTS = (
    ("职场", "职场"),
    ("抢功", "职场"),
    ("复仇", "复仇"),
    ("霸总", "霸总甜宠"),
    ("甜宠", "甜宠"),
    ("穿越", "穿越"),
    ("重生", "重生"),
    ("悬疑", "悬疑"),
    ("家庭", "家庭伦理"),
    ("校园", "校园"),
)


def infer_genre(user_input: str) -> str:
    hits = [label for token, label in GENRE_HINTS if token in user_input]
    return "×".join(dict.fromkeys(hits)) if hits else "都市情感"


def infer_title(user_input: str) -> str:
    compact = re.sub(r"\s+", "", user_input)
    compact = re.sub(r"^只要[^，,。]*[，,。]?", "", compact)
    compact = re.sub(r"^(帮我|请|麻烦|想要|想|要)", "", compact)
    compact = re.sub(r"^(写一部|写一个|写个|生成一部|生成一个|做一部|做个)", "", compact)
    compact = re.sub(r"(短剧|剧本|故事|台本)$", "", compact)
    if 2 <= len(compact) <= 12:
        return compact
    genre = infer_genre(user_input)
    return f"{genre}短剧"


def infer_logline(user_input: str) -> str:
    return f"围绕「{user_input.strip()}」展开的强冲突短剧，前三秒抛钩子，每集一个反转。"


def parse_video_url(user_input: str) -> str:
    match = re.search(r"https?://\S+", user_input)
    return match.group(0).rstrip("。，,") if match else "https://media.short-play.local/demo/source.mp4"


def parse_voice_swap(user_input: str) -> tuple[str, str]:
    match = re.search(
        r"里([^的]{1,8})的声音(?:全部)?(?:换成|替换为|替换成)([^，。,\s]+)",
        user_input,
    )
    if not match:
        match = re.search(
            r"(?:把|将)(?!视频)([^的]{1,8})的声音(?:全部)?(?:换成|替换为|替换成)([^，。,\s]+)",
            user_input,
        )
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "林晚", "沈衡"
