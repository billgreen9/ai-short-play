from app.llm import _parse_embedding
from app.matching.hybrid import lexical_score
from app.models import classify_band, parse_csv


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
