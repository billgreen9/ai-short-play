from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SkillRecord(BaseModel):
    id: int
    skill_name: str
    description: str = ""
    skill_prompt: str = ""
    function_tools: str = ""
    depends_on: str | None = None
    status: int = 1

    def tool_names(self) -> list[str]:
        return parse_csv(self.function_tools)

    def dependency_names(self) -> list[str]:
        return parse_csv(self.depends_on)


class IntentMatchRecord(BaseModel):
    id: int
    msg: str
    score_limit: float
    score_confirm_limit: float
    skill_id: int | None = None
    answer: str | None = None
    support: int = 1
    skill_name: str | None = None
    skill_status: int | None = None


class ScoredIntent(BaseModel):
    intent: IntentMatchRecord
    keyword_score: float | None = None
    semantic_score: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None
    score: float = 0.0
    band: Literal["matched", "confirm", "reject"] = "reject"


class MatchResult(BaseModel):
    query: str
    status: Literal["matched", "need_confirm", "answer", "unsupported", "unmatched"]
    score: float = 0.0
    reason: str = ""
    skill: SkillRecord | None = None
    answer: str | None = None
    support: int | None = None
    hits: list[ScoredIntent] = Field(default_factory=list)
    confirm_candidates: list[ScoredIntent] = Field(default_factory=list)


class StepResult(BaseModel):
    skill_name: str
    step_index: int
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    tools: list[str] = Field(default_factory=list)


def parse_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def classify_band(score: float, score_limit: float, score_confirm_limit: float) -> Literal["matched", "confirm", "reject"]:
    """score > score_limit 自动命中；confirm_limit < score <= limit 交给用户确认。"""
    if score > score_limit:
        return "matched"
    if score_confirm_limit < score <= score_limit:
        return "confirm"
    return "reject"
