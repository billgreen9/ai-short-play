from pathlib import Path

from app.config import PROJECT_ROOT, get_settings
from app.skills.loader import discover_skills, load_skill
from app.skills.schema import validate_payload
from app.skills.tools import assemble_openai_tools, tool_name_for


def test_each_skill_has_required_layout() -> None:
    skills = discover_skills(PROJECT_ROOT / "skills")
    names = {skill.name for skill in skills}
    assert "generate-concept" in names
    assert "swap-character-voice" in names
    for meta in skills:
        root = Path(meta.skill_dir)
        assert (root / "SKILL.md").is_file()
        assert (root / "tool_schema.json").is_file()
        assert (root / "input_schema.json").is_file()
        assert (root / "output_schema.json").is_file()
        assert (root / "scripts" / "run.py").is_file()
        assert (root / "reference" / "examples" / "demo_input.json").is_file()
        assert (root / "reference" / "examples" / "demo_output.json").is_file()
        record = load_skill(root, skills_root=PROJECT_ROOT / "skills")
        assert record.tool_schema["type"] == "function"
        assert record.input_schema["type"] == "object"
        assert record.output_schema["type"] == "object"
        validate_payload(record.reference.examples["demo_input"], record.input_schema, label="demo_input")
        validate_payload(record.reference.examples["demo_output"], record.output_schema, label="demo_output")


def test_assemble_openai_tools_from_tool_schema() -> None:
    skills = discover_skills(get_settings().skills_root)
    tools = assemble_openai_tools(skills)
    names = [item["function"]["name"] for item in tools]
    assert names == [
        tool_name_for(skill) for skill in skills if not skill.disable_model_invocation
    ]
    assert "generate_concept" in names
    assert "write_script" in names


def test_write_script_reference_has_camera_and_transition() -> None:
    record = load_skill(
        PROJECT_ROOT / "skills/production/screenplay/write-script",
        skills_root=PROJECT_ROOT / "skills",
    )
    assert "camera_move.md" in record.reference.enums
    assert "transition_list.md" in record.reference.enums
    assert "shot_spec.md" in record.reference.specs
