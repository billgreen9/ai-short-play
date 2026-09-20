from __future__ import annotations

import pytest

from app.config import get_settings
from app.db import delete_skill_by_name, init_schema, insert_intent_match, upsert_skill
from app.matching.hybrid import match_intent
from app.skills.store import add_skill


@pytest.fixture
def db():
    init_schema()
    names = (
        "test_match_concept",
        "test_match_profiles",
        "test_match_confirm",
        "test_sync_skill",
    )
    for name in names:
        delete_skill_by_name(name)
    yield
    for name in names:
        delete_skill_by_name(name)


def _unit(index: int) -> list[float]:
    dim = get_settings().embedding_dim
    vector = [0.0] * dim
    vector[index] = 1.0
    return vector


def test_auto_match_when_score_above_limit(db, monkeypatch):
    monkeypatch.setattr("app.matching.hybrid.embed_text", lambda query: _unit(0))
    concept = upsert_skill(
        skill_name="test_match_concept",
        description="TOKEN_CONCEPT_XYZ_MATCH",
        skill_prompt="x",
        function_tools="",
    )
    profiles = upsert_skill(
        skill_name="test_match_profiles",
        description="TOKEN_PROFILE_XYZ_MATCH",
        skill_prompt="x",
        function_tools="",
    )
    insert_intent_match(
        msg="TOKEN_CONCEPT_XYZ_MATCH",
        embedding=_unit(0),
        score_limit=0.72,
        score_confirm_limit=0.4,
        skill_id=concept.id,
    )
    insert_intent_match(
        msg="TOKEN_PROFILE_XYZ_MATCH",
        embedding=_unit(1),
        score_limit=0.72,
        score_confirm_limit=0.4,
        skill_id=profiles.id,
    )
    matched = match_intent("TOKEN_CONCEPT_XYZ_MATCH", use_llm_rerank=False)
    assert matched.status == "matched"
    assert matched.skill is not None
    assert matched.skill.skill_name == "test_match_concept"


def test_confirm_when_score_between_thresholds(db, monkeypatch):
    skill = upsert_skill(
        skill_name="test_match_confirm",
        description="confirm-band-skill",
        skill_prompt="x",
        function_tools="",
    )
    insert_intent_match(
        msg="TOKEN_CONFIRM_UNIQUE_MSG",
        embedding=_unit(5),
        score_limit=0.9,
        score_confirm_limit=0.2,
        skill_id=skill.id,
    )
    query_vec = _unit(5)
    query_vec[5] = 0.7
    query_vec[6] = 0.71414
    monkeypatch.setattr("app.matching.hybrid.embed_text", lambda query: query_vec)
    result = match_intent("qqq_unrelated_zzzz", use_llm_rerank=False)
    assert result.status == "need_confirm"
    assert result.confirm_candidates
    assert result.confirm_candidates[0].intent.skill_name == "test_match_confirm"
    assert result.confirm_candidates[0].band == "confirm"


def test_add_skill_writes_intent_match(db, monkeypatch):
    monkeypatch.setattr("app.skills.store.embed_text", lambda text: _unit(2))
    skill = add_skill(
        skill_name="test_sync_skill",
        description="TOKEN_SYNC_INTENT_MSG",
        skill_prompt="prompt",
        function_tools="",
    )
    monkeypatch.setattr("app.matching.hybrid.embed_text", lambda query: _unit(2))
    result = match_intent("TOKEN_SYNC_INTENT_MSG", use_llm_rerank=False)
    assert result.status == "matched"
    assert result.skill is not None
    assert result.skill.id == skill.id
