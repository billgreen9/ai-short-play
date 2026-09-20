from app.graph.confirm import (
    format_confirm_prompt,
    interrupt_payload,
    pending_interrupts,
    public_candidates,
    resolve_choice,
)


def test_public_candidates_skips_empty_skill_name():
    raw = [
        {"score": 0.6, "intent": {"skill_name": "build_profiles", "msg": "人物小传"}},
        {"score": 0.5, "intent": {"skill_name": "", "msg": "faq"}},
    ]
    items = public_candidates(raw)
    assert items == [{"skill_name": "build_profiles", "score": 0.6, "msg": "人物小传"}]


def test_resolve_choice_skip_does_not_need_db():
    name, error = resolve_choice("skip", [])
    assert name is None
    assert "取消" in error


def test_interrupt_payload_and_prompt():
    payload = interrupt_payload(
        "写一个短剧",
        [{"score": 0.66, "intent": {"skill_name": "create_short_play", "msg": "写一个短剧"}}],
    )
    text = format_confirm_prompt(payload)
    assert payload["type"] == "confirm_skill"
    assert "create_short_play" in text
    assert "skip" in text


def test_candidates_for_confirm_uses_matched_skill():
    from app.graph.confirm import candidates_for_confirm
    from app.models import MatchResult, SkillRecord

    decision = MatchResult(
        query="写短剧",
        status="matched",
        score=0.9,
        skill=SkillRecord(id=1, skill_name="create_short_play", description="全流程"),
    )
    items = candidates_for_confirm(decision)
    assert items[0]["intent"]["skill_name"] == "create_short_play"


def test_pending_interrupts_reads_langgraph_key():
    assert pending_interrupts({}) == []
    assert pending_interrupts({"__interrupt__": ("x",)}) == ["x"]
