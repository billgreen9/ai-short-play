from app.llm import _parse_embedding
from app.matching.hybrid import dedupe_by_skill_id, lexical_score
from app.models import IntentMatchRecord, ScoredIntent, classify_band, parse_csv


def test_parse_csv_strips_and_skips_empty():
    assert parse_csv("a, b,c,,") == ["a", "b", "c"]
    assert parse_csv(None) == []
    assert parse_csv("") == []


def test_classify_band_matches_spec():
    assert classify_band(0.81, 0.8, 0.4) == "matched"
    assert classify_band(0.8, 0.8, 0.4) == "confirm"
    assert classify_band(0.5, 0.8, 0.4) == "confirm"
    assert classify_band(0.4, 0.8, 0.4) == "reject"
    assert classify_band(0.39, 0.8, 0.4) == "reject"


def test_lexical_score_prefers_short_utterance_covered_by_query():
    query = "帮我写一个职场复仇短剧"
    assert lexical_score(query, "写一个短剧") >= 0.7
    assert lexical_score("只要人物小传", "只要人物小传") == 1.0
    assert lexical_score("只要人物小传", "写人物小传") >= 0.5


def test_parse_embedding_supports_openai_and_multimodal_shapes():
    openai = _parse_embedding({"data": [{"embedding": [0.1, 0.2]}]})
    multimodal = _parse_embedding({"data": {"embedding": [0.3, 0.4]}})
    assert openai == [0.1, 0.2]
    assert multimodal == [0.3, 0.4]


def _hit(intent_id: int, score: float, skill_id: int | None) -> ScoredIntent:
    return ScoredIntent(
        intent=IntentMatchRecord(
            id=intent_id,
            msg=f"msg-{intent_id}",
            score_limit=0.72,
            score_confirm_limit=0.45,
            skill_id=skill_id,
        ),
        fused_score=score,
        score=score,
    )


def test_dedupe_by_skill_id_keeps_highest_score():
    hits = [
        _hit(1, 0.4, skill_id=10),
        _hit(2, 0.9, skill_id=10),
        _hit(3, 0.7, skill_id=11),
        _hit(4, 0.8, skill_id=None),
        _hit(5, 0.3, skill_id=None),
    ]
    unique = dedupe_by_skill_id(hits)
    skill_hits = [item for item in unique if item.intent.skill_id is not None]
    null_hits = [item for item in unique if item.intent.skill_id is None]
    assert [item.intent.id for item in skill_hits] == [2, 3]
    assert [item.intent.id for item in null_hits] == [4, 5]
    assert unique[0].intent.id == 2
