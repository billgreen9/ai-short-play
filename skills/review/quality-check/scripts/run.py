from __future__ import annotations

from typing import Any

DEFAULT_ISSUES = [
    {"type": "hook", "detail": "开场钩子还不够具体，建议第一句台词直接点出被抢的成果名称"},
    {"type": "character", "detail": "对手动机偏功能化，需要一个更私人的伤口"},
    {"type": "structure", "detail": "第2集后半应提前埋幕后黑手"},
]
DEFAULT_FIXES = [
    "第1集结尾改成：原始文件出现在男主办公室",
    "给对手加一条「曾经被女主无意压制」的旧怨",
]


def run(params: dict[str, Any]) -> dict[str, Any]:
    issues = params.get("issues") or DEFAULT_ISSUES
    fixes = params.get("fixes") or DEFAULT_FIXES
    score = float(params.get("score") if params.get("score") is not None else 7.5)
    score = min(max(score, 0.0), 10.0)
    markdown = "# 质检意见\n\n" + f"- 分数：{score}/10\n" + "\n".join(
        f"- [{item.get('type')}] {item.get('detail')}" for item in issues
    )
    return {
        "score": score,
        "issues": issues,
        "fixes": fixes,
        "source": "llm" if params.get("issues") else "template",
        "markdown": markdown,
    }
