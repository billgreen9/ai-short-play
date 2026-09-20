from __future__ import annotations

import re
from collections import defaultdict, deque

from app.llm import complete_json, llm_enabled
from app.models import RouteDecision, SkillMeta
from app.skills.tools import assemble_openai_tools, tool_name_for

BROAD_HINTS = (
    "短剧",
    "短篇",
    "全集",
    "全流程",
    "完整",
    "写一个",
    "写一部",
    "生成一部",
    "创作",
    "从零",
    "一键",
)

CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "ideation": ("创意", "概念", "logline", "故事核", "选题", "钩子", "题材"),
    "character": ("人物", "角色", "人设", "小传", "关系"),
    "plot": ("大纲", "剧情", "情节", "分集", "节拍", "结构"),
    "screenplay": ("剧本", "台本", "对白", "场次", "分镜台词", "运镜", "转场", "镜头"),
    "review": ("审稿", "质检", "润色", "检查", "评分", "问题"),
    "media": ("视频", "成片", "mp4", "配音", "换声", "声音", "音色", "声线"),
}

VOICE_SWAP_HINTS = ("换声", "配音", "声音换成", "声音替换", "替换为另外", "音色", "声线")

ONLY_HINTS = ("只要", "只做", "仅", "单独", "只生成", "只写")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _grams(text: str) -> set[str]:
    compact = _normalize(text)
    grams: set[str] = set()
    for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", compact):
        grams.add(token)
    for size in (2, 3):
        if len(compact) >= size:
            grams.update(compact[i : i + size] for i in range(len(compact) - size + 1))
    return grams


def _by_name(skills: list[SkillMeta]) -> dict[str, SkillMeta]:
    return {skill.name: skill for skill in skills}


def score_skill(query: str, skill: SkillMeta) -> float:
    if skill.disable_model_invocation:
        return 0.0
    q_grams = _grams(query)
    blob = f"{skill.name} {skill.category} {skill.description}"
    s_grams = _grams(blob)
    if not q_grams or not s_grams:
        return 0.0
    overlap = len(q_grams & s_grams)
    score = overlap / max(len(q_grams), 1)

    category_leaf = skill.category.split("/")[-1]
    for key, hints in CATEGORY_HINTS.items():
        if key in skill.category or key == category_leaf:
            if any(hint in query for hint in hints):
                score += 0.45
    if skill.name.replace("-", "") in _normalize(query):
        score += 0.6
    return round(score, 4)


def _is_broad(query: str) -> bool:
    return any(hint in query for hint in BROAD_HINTS) and not any(hint in query for hint in ONLY_HINTS)


def expand_dependencies(names: list[str], skills: list[SkillMeta]) -> list[str]:
    index = _by_name(skills)
    required: set[str] = set()
    queue = deque(names)
    while queue:
        name = queue.popleft()
        if name in required or name not in index:
            continue
        required.add(name)
        for dep in index[name].depends_on:
            if dep not in required:
                queue.append(dep)
    ordered = [skill.name for skill in sorted(index.values(), key=lambda item: item.sort_order) if skill.name in required]
    return ordered


def _pipeline_plan(skills: list[SkillMeta], pipeline: str) -> list[str]:
    return [
        skill.name
        for skill in sorted(skills, key=lambda item: item.sort_order)
        if skill.pipeline == pipeline
    ]


def _detect_pipeline(query: str) -> str | None:
    if any(hint in query for hint in VOICE_SWAP_HINTS) or ("声音" in query and "视频" in query):
        return "voice-replace"
    if _is_broad(query):
        return "writing"
    return None


def lexical_plan(query: str, skills: list[SkillMeta], *, force: list[str] | None = None) -> RouteDecision:
    usable = [skill for skill in skills if not skill.disable_model_invocation]
    scores = {skill.name: score_skill(query, skill) for skill in usable}

    if force:
        plan = expand_dependencies(force, usable)
        return RouteDecision(
            query=query,
            plan=plan,
            scores=scores,
            reason="显式指定 skill，并按 depends_on 补齐前置步骤",
            strategy="forced",
        )

    if not usable:
        return RouteDecision(query=query, plan=[], reason="没有可自动调用的 skill", strategy="lexical")

    family = _detect_pipeline(query)
    if family:
        plan = _pipeline_plan(usable, family)
        return RouteDecision(
            query=query,
            plan=plan,
            scores=scores,
            reason=f"查询命中 {family} 流水线",
            strategy="pipeline",
        )

    ranked = sorted(usable, key=lambda item: (scores[item.name], -item.sort_order), reverse=True)
    best = scores[ranked[0].name]
    if best < 0.12:
        plan = _pipeline_plan(usable, ranked[0].pipeline)
        return RouteDecision(
            query=query,
            plan=plan,
            scores=scores,
            reason="关键词不够确定，回退到命中 skill 所在流水线",
            strategy="pipeline-fallback",
        )

    threshold = max(best * 0.55, 0.12)
    selected = [skill.name for skill in ranked if scores[skill.name] >= threshold]
    plan = expand_dependencies(selected, usable)
    return RouteDecision(
        query=query,
        plan=plan,
        scores=scores,
        reason="独立路由层按 description/目录/依赖做检索与补齐",
        strategy="lexical",
    )


def _llm_plan(query: str, skills: list[SkillMeta], lexical: RouteDecision) -> RouteDecision | None:
    catalog = [
        {
            "name": skill.name,
            "tool": tool_name_for(skill) if skill.tool_schema else skill.name,
            "description": skill.description,
            "category": skill.category,
            "order": skill.sort_order,
            "depends_on": skill.depends_on,
        }
        for skill in skills
        if not skill.disable_model_invocation
    ]
    tools = assemble_openai_tools(skills)
    payload = complete_json(
        (
            "根据用户任务选出需要执行的 skills，按依赖从前往后排序。"
            "不要发明 catalog 之外的 name。可以少选，但缺依赖时要补齐。\n"
            f"用户任务：{query}\n"
            f"候选：{catalog}\n"
            f"已组装 OpenAI tools：{[item['function']['name'] for item in tools]}\n"
            f"词法初排：{lexical.plan}\n"
            '只输出 JSON：{"plan": ["skill-name"], "reason": "一句话"}'
        ),
        system="你是短剧生产流水线的 skill 路由器，只做选择和排序。",
    )
    if not payload or not isinstance(payload.get("plan"), list):
        return None
    names = [str(name) for name in payload["plan"] if str(name) in {s.name for s in skills}]
    if not names:
        return None
    plan = expand_dependencies(names, skills)
    return RouteDecision(
        query=query,
        plan=plan,
        scores=lexical.scores,
        reason=str(payload.get("reason") or "LLM 对检索短名单重排"),
        strategy="retrieve-and-rerank",
    )


class SkillRouter:
    """Host-side router: score metadata, compose a plan, optionally LLM-rerank."""

    def route(
        self,
        query: str,
        skills: list[SkillMeta],
        *,
        force: list[str] | None = None,
        use_llm: bool = True,
    ) -> RouteDecision:
        lexical = lexical_plan(query, skills, force=force)
        if force or not use_llm or not llm_enabled() or lexical.strategy in {"forced"}:
            return lexical
        reranked = _llm_plan(query, skills, lexical)
        return reranked or lexical

    def group_by_category(self, skills: list[SkillMeta]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for skill in skills:
            grouped[skill.category].append(skill.name)
        return dict(grouped)
