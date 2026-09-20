from __future__ import annotations

from typing import Any

from app.db import fetch_skill_by_name
from app.models import MatchResult
from app.skills.dag import expand_skill_dag


def candidates_for_confirm(decision: MatchResult) -> list[dict[str, Any]]:
    if decision.confirm_candidates:
        return [item.model_dump() for item in decision.confirm_candidates]
    if decision.skill:
        return [
            {
                "score": decision.score,
                "intent": {
                    "skill_name": decision.skill.skill_name,
                    "msg": decision.skill.description,
                },
            }
        ]
    return []


CANCEL_CHOICES = {"", "skip", "cancel", "n", "no"}


def public_candidates(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in raw:
        intent = item.get("intent") if isinstance(item, dict) else None
        if not isinstance(intent, dict):
            intent = item if isinstance(item, dict) else {}
        name = intent.get("skill_name") or ""
        if not name:
            continue
        items.append(
            {
                "skill_name": name,
                "score": item.get("score"),
                "msg": intent.get("msg") or "",
            }
        )
    return items


def interrupt_payload(query: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "confirm_skill",
        "query": query,
        "message": "rerank 已完成。请确认要执行的 skill，确认后才会调用执行大模型；输入 skip 取消。",
        "candidates": public_candidates(candidates),
    }


def pending_interrupts(result: dict[str, Any] | None) -> list[Any]:
    if not result:
        return []
    raw = result.get("__interrupt__")
    if not raw:
        return []
    return list(raw)


def interrupt_value(result: dict[str, Any] | None) -> dict[str, Any] | None:
    items = pending_interrupts(result)
    if not items:
        return None
    first = items[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"message": str(value)}


def resolve_choice(chosen: object, candidates: list[dict[str, Any]]) -> tuple[str | None, str]:
    raw = str(chosen or "").strip()
    if raw.lower() in CANCEL_CHOICES:
        return None, "用户取消确认"
    published = public_candidates(candidates)
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(published):
            raw = published[index]["skill_name"]
        else:
            return None, f"无效序号: {raw}"
    skill = fetch_skill_by_name(raw)
    if skill is None:
        return None, f"确认的技能不存在或已失效: {raw}"
    plan = [item.skill_name for item in expand_skill_dag(skill, fetch_skill_by_name)]
    return skill.skill_name, "" if plan else "确认的技能没有可执行计划"


def format_confirm_prompt(payload: dict[str, Any]) -> str:
    lines = [payload.get("message") or "请确认要执行的技能：", f"原问题：{payload.get('query') or ''}"]
    for index, item in enumerate(payload.get("candidates") or [], start=1):
        lines.append(f"  [{index}] {item.get('skill_name')}  score={item.get('score')}  {item.get('msg')}")
    lines.append("请输入 skill_name 或序号（skip 取消）：")
    return "\n".join(lines)
