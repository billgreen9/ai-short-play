from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig
from langsmith import traceable, tracing_context

from app.config import get_settings
from app.db import (
    create_run,
    finish_run,
    init_schema,
    insert_step,
    update_run_plan,
    upsert_skills,
)
from app.graph.state import AgentState
from app.models import SkillMeta
from app.skills.executor import execute_skill
from app.skills.loader import discover_skills, load_skill_by_name
from app.skills.router import SkillRouter
from app.tracing import configure_tracing

ARTIFACT_TITLES = {
    "generate-concept": "故事概念",
    "build-profiles": "人物小传",
    "write-outline": "分集大纲",
    "write-script": "剧本",
    "quality-check": "质检意见",
    "ingest-source-video": "源视频入库",
    "swap-character-voice": "角色换声",
    "publish-final-cut": "成片发布",
}


def _catalog_node(state: AgentState) -> dict[str, Any]:
    settings = get_settings()
    skills = discover_skills(settings.skills_root)
    upsert_skills(skills)
    create_run(state["run_id"], state["user_input"])
    return {"catalog": [skill.model_dump() for skill in skills], "current_index": 0, "artifacts": {}, "steps": []}


def _route_node(state: AgentState) -> dict[str, Any]:
    skills = [SkillMeta.model_validate(item) for item in state.get("catalog", [])]
    decision = SkillRouter().route(
        state["user_input"],
        skills,
        force=state.get("force_skills") or None,
    )
    update_run_plan(state["run_id"], decision.plan, decision.reason, decision.strategy)
    error = "" if decision.plan else "没有匹配到可用 skill"
    return {
        "plan": decision.plan,
        "route_reason": decision.reason,
        "route_strategy": decision.strategy,
        "error": error,
        "current_index": 0,
    }


def _load_skill_node(state: AgentState) -> dict[str, Any]:
    plan = state.get("plan") or []
    index = state.get("current_index") or 0
    if index >= len(plan):
        return {"error": "plan 已执行完"}
    settings = get_settings()
    skills = [SkillMeta.model_validate(item) for item in state.get("catalog", [])]
    record = load_skill_by_name(plan[index], skills, settings.skills_root)
    return {
        "current_skill_name": record.name,
        "current_skill_body": record.body,
    }


def _execute_node(state: AgentState) -> dict[str, Any]:
    settings = get_settings()
    skills = [SkillMeta.model_validate(item) for item in state.get("catalog", [])]
    name = state["current_skill_name"]
    record = load_skill_by_name(name, skills, settings.skills_root)
    index = state.get("current_index") or 0
    step = execute_skill(
        record,
        user_input=state["user_input"],
        run_id=state["run_id"],
        step_index=index,
        artifacts=state.get("artifacts") or {},
    )
    insert_step(state["run_id"], record.body, step)
    artifacts = dict(state.get("artifacts") or {})
    if step.status == "ok":
        artifacts[name] = step.output
        error = ""
    else:
        error = step.error
    return {
        "artifacts": artifacts,
        "steps": [step.model_dump()],
        "current_index": index + 1,
        "error": error,
    }


def _assemble_node(state: AgentState) -> dict[str, Any]:
    chunks = [
        f"任务：{state['user_input']}",
        f"路由：{state.get('route_strategy')} / {state.get('route_reason')}",
        "执行计划：" + " -> ".join(state.get("plan") or []),
    ]
    artifacts = state.get("artifacts") or {}
    for name in state.get("plan") or []:
        title = ARTIFACT_TITLES.get(name, name)
        chunks.append(f"\n## {title}（{name}）\n{_format_artifact(artifacts.get(name))}")
    error = state.get("error") or ""
    status = "error" if error else "succeeded"
    if error:
        chunks.append(f"\n## 中断原因\n{error}")
    final_output = "\n".join(chunks).strip()
    finish_run(state["run_id"], status, final_output)
    return {"final_output": final_output}


def _format_artifact(value: Any) -> str:
    if value is None:
        return "（无输出）"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "markdown" in value and isinstance(value["markdown"], str):
            return value["markdown"]
        lines = []
        for key, item in value.items():
            if key == "raw":
                continue
            if isinstance(item, (dict, list)):
                lines.append(f"- {key}:")
                lines.append(_indent(_format_artifact(item)))
            else:
                lines.append(f"- {key}: {item}")
        return "\n".join(lines) or str(value)
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value, start=1):
            lines.append(f"{index}. {_format_artifact(item)}")
        return "\n".join(lines)
    return str(value)


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


def _after_route(state: AgentState) -> Literal["load_skill", "assemble"]:
    if state.get("plan"):
        return "load_skill"
    return "assemble"


def _after_execute(state: AgentState) -> Literal["load_skill", "assemble"]:
    if state.get("error"):
        return "assemble"
    index = state.get("current_index") or 0
    plan = state.get("plan") or []
    if index < len(plan):
        return "load_skill"
    return "assemble"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("catalog", _catalog_node)
    graph.add_node("route", _route_node)
    graph.add_node("load_skill", _load_skill_node)
    graph.add_node("execute", _execute_node)
    graph.add_node("assemble", _assemble_node)
    graph.add_edge(START, "catalog")
    graph.add_edge("catalog", "route")
    graph.add_conditional_edges("route", _after_route, {"load_skill": "load_skill", "assemble": "assemble"})
    graph.add_edge("load_skill", "execute")
    graph.add_conditional_edges("execute", _after_execute, {"load_skill": "load_skill", "assemble": "assemble"})
    graph.add_edge("assemble", END)
    return graph


@traceable(name="short-play-run", run_type="chain")
def run_task(user_input: str, *, force_skills: list[str] | None = None, thread_id: str | None = None) -> dict[str, Any]:
    configure_tracing()
    init_schema()
    run_id = thread_id or str(uuid4())
    graph = build_graph()
    initial: AgentState = {
        "user_input": user_input,
        "run_id": run_id,
        "force_skills": force_skills or [],
        "catalog": [],
        "plan": [],
        "route_reason": "",
        "route_strategy": "",
        "current_index": 0,
        "current_skill_name": "",
        "current_skill_body": "",
        "artifacts": {},
        "steps": [],
        "final_output": "",
        "error": "",
    }
    settings = get_settings()
    config: RunnableConfig = {
        "configurable": {"thread_id": run_id},
        "run_name": f"short-play:{user_input[:48]}",
        "tags": ["ai-short-play", "langgraph"],
        "metadata": {"run_id": run_id},
    }
    with PostgresSaver.from_conn_string(settings.postgres_dsn) as checkpointer:
        checkpointer.setup()
        compiled = graph.compile(checkpointer=checkpointer)
        with tracing_context(
            enabled=settings.langsmith_enabled,
            project_name=settings.langsmith_project,
        ):
            result = compiled.invoke(initial, config)
    return result
