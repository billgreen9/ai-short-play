from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from langsmith import traceable

from app.adapters.media import realize_media_job
from app.llm import complete_tool_args, llm_enabled
from app.models import SkillRecord, StepResult
from app.skills.loader import format_reference
from app.skills.schema import SchemaError, validate_payload
from app.skills.tools import normalize_tool


def _load_run_module(skill: SkillRecord):
    script_path = Path(skill.script_path)
    if not script_path.is_file():
        raise FileNotFoundError(f"{skill.name} 缺少 scripts/run.py")
    module_name = f"skill_script_{skill.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise AttributeError(f"{script_path} 必须提供纯函数 run(params: dict) -> dict")
    return run


def _bind_tool_args(skill: SkillRecord, *, user_input: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    if not llm_enabled() or not skill.tool_schema:
        return {}
    tool = normalize_tool(
        skill.tool_schema,
        fallback_name=skill.name,
        fallback_description=skill.description,
    )
    reference = format_reference(skill.reference)
    system = "\n\n".join(
        part for part in (skill.body.strip(), reference) if part
    )
    prompt = (
        f"用户任务：{user_input}\n"
        f"上游 artifacts：{artifacts}\n"
        "根据 SKILL.md 与 reference/ 填写工具参数。"
        "枚举值必须来自 reference/enums。"
    )
    try:
        return complete_tool_args(prompt, tool=tool, system=system) or {}
    except Exception:
        return {}


@traceable(name="execute_skill", run_type="chain")
def execute_skill(
    skill: SkillRecord,
    *,
    user_input: str,
    run_id: str,
    step_index: int,
    artifacts: dict[str, Any],
) -> StepResult:
    params: dict[str, Any] = {
        "user_input": user_input,
        "artifacts": artifacts,
    }
    try:
        params.update(_bind_tool_args(skill, user_input=user_input, artifacts=artifacts))
        allowed = set((skill.input_schema.get("properties") or {}).keys())
        if allowed:
            params = {key: value for key, value in params.items() if key in allowed}
        validate_payload(params, skill.input_schema, label=f"{skill.name} input")
        output = _load_run_module(skill)(params)
        if not isinstance(output, dict):
            raise TypeError("run() 必须返回 dict")
        output = realize_media_job(run_id, skill.name, output)
        validate_payload(output, skill.output_schema, label=f"{skill.name} output")
    except (SchemaError, OSError, ImportError, AttributeError, TypeError, ValueError) as exc:
        return StepResult(
            skill_name=skill.name,
            step_index=step_index,
            status="error",
            script_path=skill.script_path,
            input=params,
            error=str(exc),
        )
    return StepResult(
        skill_name=skill.name,
        step_index=step_index,
        status="ok",
        script_path=skill.script_path,
        input=params,
        output=output,
    )
