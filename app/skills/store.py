from __future__ import annotations

from app.config import get_settings
from app.db import (
    fetch_skill_by_name,
    find_canonical_intent,
    find_intent_by_skill_msg,
    insert_intent_match,
    list_intent_matches,
    list_skills,
    update_intent_match_msg,
    upsert_skill,
)
from app.llm import embed_text
from app.models import SkillRecord, parse_csv
from app.tools.registry import resolve_tools
import app.tools as _tools  # noqa: F401


def sync_skill_intent(skill: SkillRecord) -> None:
    """每个 skill 的 description 写入 intent_match.msg，供端上匹配。"""
    settings = get_settings()
    embedding = embed_text(skill.description)
    existing = find_canonical_intent(skill.id)
    if existing:
        update_intent_match_msg(int(existing["id"]), msg=skill.description, embedding=embedding)
        return
    insert_intent_match(
        msg=skill.description,
        embedding=embedding,
        score_limit=settings.score_limit,
        score_confirm_limit=settings.score_confirm_limit,
        skill_id=skill.id,
        answer=None,
        support=1,
    )


def add_skill(
    *,
    skill_name: str,
    description: str,
    skill_prompt: str,
    function_tools: str = "",
    depends_on: str | None = None,
    status: int = 1,
) -> SkillRecord:
    if function_tools:
        resolve_tools(function_tools)
    for dep in parse_csv(depends_on):
        if fetch_skill_by_name(dep) is None:
            raise ValueError(f"depends_on 引用了不存在或无效的技能: {dep}")
    skill = upsert_skill(
        skill_name=skill_name,
        description=description,
        skill_prompt=skill_prompt,
        function_tools=function_tools,
        depends_on=depends_on or None,
        status=status,
    )
    sync_skill_intent(skill)
    return skill


def add_intent_msg(skill: SkillRecord, msg: str) -> None:
    """为已有 skill 追加一条匹配语料，不覆盖 description 对应的主记录。"""
    msg = msg.strip()
    if not msg:
        return
    if find_intent_by_skill_msg(skill.id, msg):
        return
    settings = get_settings()
    insert_intent_match(
        msg=msg,
        embedding=embed_text(msg),
        score_limit=settings.score_limit,
        score_confirm_limit=settings.score_confirm_limit,
        skill_id=skill.id,
        answer=None,
        support=1,
    )


def load_active_skills() -> list[SkillRecord]:
    return list_skills(include_disabled=False)


def backfill_intent_embeddings(*, only_missing: bool = True) -> dict[str, int]:
    """用当前向量模型重写 intent_match.msg_embedding。"""
    stats = {"total": 0, "updated": 0, "skipped": 0, "failed": 0}
    for row in list_intent_matches():
        stats["total"] += 1
        if only_missing and row.get("msg_embedding") is not None:
            stats["skipped"] += 1
            continue
        embedding = embed_text(row["msg"] or "")
        if embedding is None:
            stats["failed"] += 1
            continue
        update_intent_match_msg(int(row["id"]), msg=row["msg"], embedding=embedding)
        stats["updated"] += 1
    return stats
