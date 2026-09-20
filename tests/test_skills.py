from pathlib import Path

from app.config import PROJECT_ROOT
from app.skills.loader import discover_skills
from app.skills.router import SkillRouter


def test_discover_nested_skills() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    names = {skill.name for skill in skills}
    assert "generate-concept" in names
    assert "swap-character-voice" in names
    assert "publish-final-cut" in names
    by_name = {skill.name: skill for skill in skills}
    assert by_name["build-profiles"].category == "development/character"
    assert by_name["write-script"].category == "production/screenplay"
    assert by_name["generate-concept"].tool_schema["function"]["name"] == "generate_concept"
    assert (Path(by_name["generate-concept"].skill_dir) / "scripts" / "run.py").is_file()


def test_router_full_pipeline_for_broad_query() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    decision = SkillRouter().route("帮我写一个职场复仇短剧", skills, use_llm=False)
    assert decision.plan == [
        "generate-concept",
        "build-profiles",
        "write-outline",
        "write-script",
        "quality-check",
    ]
    assert decision.strategy in {"pipeline", "pipeline-fallback"}


def test_router_character_only_expands_concept_dep() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    decision = SkillRouter().route("只要人物小传", skills, use_llm=False)
    assert "build-profiles" in decision.plan
    assert "generate-concept" in decision.plan
    assert "write-script" not in decision.plan


def test_router_voice_replace_pipeline() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    decision = SkillRouter().route("把视频里林晚的声音换成沈衡", skills, use_llm=False)
    assert decision.plan == [
        "ingest-source-video",
        "swap-character-voice",
        "publish-final-cut",
    ]
    assert "generate-concept" not in decision.plan
