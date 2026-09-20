from __future__ import annotations

import re

from app.config import get_settings
from app.db import fetch_skill_by_id, keyword_search, row_to_intent, semantic_search
from app.llm import complete_json, embed_text, llm_enabled
from app.models import MatchResult, ScoredIntent, classify_band


def lexical_score(query: str, msg: str) -> float:
    q = re.sub(r"\s+", "", query.lower())
    m = re.sub(r"\s+", "", msg.lower())
    if not q or not m:
        return 0.0
    if q in m or m in q:
        return 1.0
    return max(_coverage(q, m), _coverage(m, q))


def _coverage(needle: str, haystack: str, size: int = 2) -> float:
    if len(needle) < size:
        return 1.0 if needle in haystack else 0.0
    grams = [needle[i : i + size] for i in range(len(needle) - size + 1)]
    return sum(1 for gram in grams if gram in haystack) / len(grams)


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _fuse(keyword: float | None, semantic: float | None, keyword_weight: float) -> float:
    if keyword is None and semantic is None:
        return 0.0
    if keyword is None:
        return float(semantic or 0.0)
    if semantic is None:
        return keyword
    semantic_weight = 1.0 - keyword_weight
    return keyword_weight * keyword + semantic_weight * semantic


def _merge_rows(
    query: str,
    keyword_rows: list[dict],
    semantic_rows: list[dict],
    keyword_weight: float,
) -> list[ScoredIntent]:
    merged: dict[int, dict] = {}
    for row in keyword_rows:
        merged[int(row["id"])] = dict(row)
    for row in semantic_rows:
        item = merged.setdefault(int(row["id"]), dict(row))
        item.update({key: value for key, value in row.items() if value is not None})
        if row.get("semantic_score") is not None:
            item["semantic_score"] = row["semantic_score"]
        if row.get("keyword_score") is not None:
            item["keyword_score"] = row["keyword_score"]
    hits: list[ScoredIntent] = []
    for row in merged.values():
        sql_keyword = _as_float(row.get("keyword_score"))
        lexical = lexical_score(query, str(row.get("msg") or ""))
        keyword = max(score for score in (sql_keyword or 0.0, lexical))
        semantic = _as_float(row.get("semantic_score"))
        fused = _fuse(keyword, semantic, keyword_weight)
        intent = row_to_intent(row)
        hits.append(
            ScoredIntent(
                intent=intent,
                keyword_score=keyword,
                semantic_score=semantic,
                fused_score=fused,
                score=fused,
                band=classify_band(fused, intent.score_limit, intent.score_confirm_limit),
            )
        )
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits


def dedupe_by_skill_id(hits: list[ScoredIntent]) -> list[ScoredIntent]:
    """同一 skill_id 只保留分值最大的一条；skill_id 为空的应答行不去重。"""
    ordered = sorted(hits, key=lambda item: (-item.score, item.intent.id))
    seen: set[int] = set()
    unique: list[ScoredIntent] = []
    for hit in ordered:
        skill_id = hit.intent.skill_id
        if skill_id is None:
            unique.append(hit)
            continue
        if skill_id in seen:
            continue
        seen.add(skill_id)
        unique.append(hit)
    return unique


def _llm_rerank(query: str, hits: list[ScoredIntent]) -> list[ScoredIntent]:
    if not hits or not llm_enabled():
        return hits
    settings = get_settings()
    catalog = [
        {"id": item.intent.id, "msg": item.intent.msg, "skill_name": item.intent.skill_name}
        for item in hits[: min(8, settings.match_top_k)]
    ]
    payload = complete_json(
        (
            "根据用户输入，给每条候选意图打 0 到 1 的相关性分数。"
            "只评估语义是否匹配，不要发明 id。\n"
            f"用户输入：{query}\n"
            f"候选：{catalog}\n"
            '只输出 JSON：{"scores": [{"id": 1, "score": 0.0}]}'
        ),
        system="你是技能意图 rerank 器，只打分不解释。",
    )
    if not payload or not isinstance(payload.get("scores"), list):
        return hits
    llm_scores: dict[int, float] = {}
    for item in payload["scores"]:
        if not isinstance(item, dict):
            continue
        try:
            llm_scores[int(item["id"])] = max(0.0, min(1.0, float(item["score"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not llm_scores:
        return hits
    weight = settings.llm_rerank_weight
    reranked: list[ScoredIntent] = []
    for hit in hits:
        llm_score = llm_scores.get(hit.intent.id)
        if llm_score is None:
            score = hit.fused_score
        else:
            score = (1.0 - weight) * hit.fused_score + weight * llm_score
        hit.rerank_score = llm_score
        hit.score = score
        hit.band = classify_band(score, hit.intent.score_limit, hit.intent.score_confirm_limit)
        reranked.append(hit)
    reranked.sort(key=lambda item: item.score, reverse=True)
    return reranked


def match_intent(query: str, *, use_llm_rerank: bool = True) -> MatchResult:
    settings = get_settings()
    query = query.strip()
    if not query:
        return MatchResult(query=query, status="unmatched", reason="空输入")

    keyword_rows = keyword_search(query, settings.match_top_k)
    embedding = embed_text(query)
    semantic_rows = semantic_search(embedding, settings.match_top_k) if embedding else []
    hits = _merge_rows(query, keyword_rows, semantic_rows, settings.hybrid_keyword_weight)
    hits = dedupe_by_skill_id(hits)
    if use_llm_rerank:
        hits = _llm_rerank(query, hits)

    matched = [item for item in hits if item.band == "matched"]
    confirms = [item for item in hits if item.band == "confirm"]

    if matched:
        best = matched[0]
        if best.intent.skill_id:
            skill = fetch_skill_by_id(best.intent.skill_id)
            if skill is None:
                return MatchResult(
                    query=query,
                    status="unmatched",
                    score=best.score,
                    reason="命中的 skill 无效",
                    hits=hits,
                )
            return MatchResult(
                query=query,
                status="matched",
                score=best.score,
                reason="关键词+语义检索后 rerank，分数高于 score_limit",
                skill=skill,
                hits=hits,
            )
        status = "answer" if best.intent.support != 0 else "unsupported"
        return MatchResult(
            query=query,
            status=status,
            score=best.score,
            reason="命中无 skill_id 的意图应答",
            answer=best.intent.answer or "",
            support=best.intent.support,
            hits=hits,
        )

    if confirms:
        return MatchResult(
            query=query,
            status="need_confirm",
            score=confirms[0].score,
            reason="分数介于 score_confirm_limit 与 score_limit 之间，需要用户确认",
            confirm_candidates=confirms,
            hits=hits,
        )

    return MatchResult(query=query, status="unmatched", reason="没有达到确认阈值的意图", hits=hits)
