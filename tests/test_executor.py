from app.config import PROJECT_ROOT, get_settings
from app.skills.executor import execute_skill
from app.skills.loader import discover_skills, load_skill_by_name


def test_execute_generate_concept_pure_run() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    record = load_skill_by_name("generate-concept", skills, get_settings().skills_root)
    step = execute_skill(
        record,
        user_input="写一个职场复仇短剧",
        run_id="test-run",
        step_index=0,
        artifacts={},
    )
    assert step.status == "ok", step.error
    assert step.output["genre"]
    assert "markdown" in step.output
    assert step.output["episode_count"] == 8


def test_execute_write_script_clamps_camera_enums() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    record = load_skill_by_name("write-script", skills, get_settings().skills_root)
    step = execute_skill(
        record,
        user_input="写第1集",
        run_id="test-run",
        step_index=0,
        artifacts={},
    )
    assert step.status == "ok", step.error
    shot = step.output["episodes"][0]["shots"][0]
    assert shot["duration_sec"] <= 8
    assert shot["camera_move"] in {"static", "push_in", "pull_out", "pan", "tilt", "handheld", "otc"}
