from __future__ import annotations

from typing import Any

ALLOWED_CAMERA = {"static", "push_in", "pull_out", "pan", "tilt", "handheld", "otc"}
ALLOWED_TRANSITION = {"cut", "smash_cut", "match_cut", "whip_pan", "fade", "jump_cut"}


def _clip_duration(value: Any) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        duration = 4.0
    return min(max(duration, 1.0), 8.0)


def _normalize_shot(shot: dict[str, Any]) -> dict[str, Any]:
    camera = shot.get("camera_move") or "push_in"
    transition = shot.get("transition") or "cut"
    if camera not in ALLOWED_CAMERA:
        camera = "static"
    if transition not in ALLOWED_TRANSITION:
        transition = "cut"
    return {
        "scene": shot.get("scene") or "未标注场景",
        "camera_move": camera,
        "transition": transition,
        "duration_sec": _clip_duration(shot.get("duration_sec")),
        "action": shot.get("action") or "",
        "dialogue": shot.get("dialogue") or "",
    }


def _default_episodes() -> list[dict[str, Any]]:
    return [
        {
            "episode": 1,
            "shots": [
                _normalize_shot(
                    {
                        "scene": "公司会议室",
                        "camera_move": "push_in",
                        "transition": "cut",
                        "duration_sec": 4,
                        "action": "女主被当众抢走方案",
                        "dialogue": "林晚：这份方案是我做的。",
                    }
                ),
                _normalize_shot(
                    {
                        "scene": "公司会议室",
                        "camera_move": "otc",
                        "transition": "cut",
                        "duration_sec": 3,
                        "action": "对手出示会议纪要",
                        "dialogue": "许蔓：会议纪要上可不是这个名字。",
                    }
                ),
                _normalize_shot(
                    {
                        "scene": "公司会议室门口",
                        "camera_move": "pull_out",
                        "transition": "smash_cut",
                        "duration_sec": 3,
                        "action": "男主要求调原始文件",
                        "dialogue": "沈衡：把原始文件调出来。",
                    }
                ),
            ],
        },
        {
            "episode": 2,
            "shots": [
                _normalize_shot(
                    {
                        "scene": "资料室",
                        "camera_move": "handheld",
                        "transition": "cut",
                        "duration_sec": 4,
                        "action": "女主找回底稿碎片",
                        "dialogue": "林晚：对手不是一个人。",
                    }
                )
            ],
        },
    ]


def run(params: dict[str, Any]) -> dict[str, Any]:
    raw_episodes = params.get("episodes") or _default_episodes()
    episodes = []
    for item in raw_episodes:
        shots = [_normalize_shot(shot) for shot in item.get("shots") or []]
        episodes.append({"episode": int(item.get("episode") or len(episodes) + 1), "shots": shots})
    lines: list[str] = []
    for episode in episodes:
        lines.append(f"## 第{episode['episode']}集")
        for shot in episode["shots"]:
            lines.append(
                f"- {shot['scene']} / {shot['camera_move']} / {shot['transition']} / {shot['duration_sec']}s"
            )
            if shot["action"]:
                lines.append(f"  动作：{shot['action']}")
            if shot["dialogue"]:
                lines.append(f"  {shot['dialogue']}")
    return {
        "episodes": episodes,
        "source": "llm" if params.get("episodes") else "template",
        "markdown": "\n".join(lines),
    }
