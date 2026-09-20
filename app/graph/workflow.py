from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RunnableConfig, interrupt
from langsmith import tracing_context

from app.config import get_settings
from app.db import (
    create_run,
    fetch_skill_by_name,
    finish_run,
    init_schema,
    insert_step,
    update_run_plan,
    update_run_status,
)
from app.graph.confirm import candidates_for_confirm, interrupt_payload, pending_interrupts, resolve_choice
from app.graph.state import AgentState
from app.matching import match_intent
from app.skills.dag import expand_skill_dag
from app.skills.executor import execute_skill
from app.tracing import configure_tracing


def _match_node(state: AgentState) -> dict[str, Any]:
    create_run(state["run_id"], state["user_input"])
    force = (state.get("force_skill") or "").strip()
    if force:
        skill = fetch_skill_by_name(force)
        if skill is None:
            return {
                "match_status": "unmatched",
                "route_reason": f"指定技能不存在或已失效: {force}",
                "plan": [],
                "error": f"指定技能不存在或已失效: {force}",
            }
        plan = [item.skill_name for item in expand_skill_dag(skill, fetch_skill_by_name)]
        update_run_plan(state["run_id"], plan, "显式指定 skill，并按 depends_on 展开 DAG")
        return {
            "match_status": "matched",
            "route_reason": "显式指定 skill，并按 depends_on 展开 DAG",
            "plan": plan,
            "current_index": 0,
            "artifacts": {},
            "error": "",
        }

    decision = match_intent(state["user_input"])
    if decision.status in {"answer", "unsupported"}:
        update_run_plan(state["run_id"], [], decision.reason)
        return {
            "match_status": decision.status,
            "route_reason": decision.reason,
            "match_score": decision.score,
            "answer": decision.answer or "",
            "plan": [],
            "error": "",
        }

    candidates = candidates_for_confirm(decision)
    if candidates:
        update_run_plan(state["run_id"], [], "rerank 完成，等待用户确认后再调用执行大模型")
        return {
            "match_status": "need_confirm",
            "route_reason": "rerank 完成，等待用户确认后再调用执行大模型",
            "match_score": decision.score,
            "plan": [],
            "confirm_candidates": candidates,
            "error": "",
        }

    update_run_plan(state["run_id"], [], decision.reason)
    return {
        "match_status": decision.status,
        "route_reason": decision.reason,
        "match_score": decision.score,
        "answer": decision.answer or "",
        "plan": [],
        "confirm_candidates": [],
        "error": "" if decision.status in {"need_confirm", "answer", "unsupported"} else decision.reason,
    }


def _confirm_node(state: AgentState) -> dict[str, Any]:
    update_run_status(state["run_id"], "waiting_confirm")
    payload = interrupt_payload(state["user_input"], state.get("confirm_candidates") or [])
    chosen = interrupt(payload)
    skill_name, error = resolve_choice(chosen, state.get("confirm_candidates") or [])
    if error or not skill_name:
        return {
            "match_status": "unmatched",
            "route_reason": error or "用户取消确认",
            "plan": [],
            "error": error or "用户取消确认",
        }
    skill = fetch_skill_by_name(skill_name)
    if skill is None:
        return {
            "match_status": "unmatched",
            "route_reason": f"确认的技能不存在或已失效: {skill_name}",
            "plan": [],
            "error": f"确认的技能不存在或已失效: {skill_name}",
        }
    plan = [item.skill_name for item in expand_skill_dag(skill, fetch_skill_by_name)]
    update_run_plan(state["run_id"], plan, "用户确认后执行")
    return {
        "match_status": "matched",
        "route_reason": "用户确认后执行",
        "plan": plan,
        "current_index": 0,
        "artifacts": {},
        "error": "",
    }


def _execute_node(state: AgentState) -> dict[str, Any]:
    plan = state.get("plan") or []
    index = state.get("current_index") or 0
    if index >= len(plan):
        return {"error": "plan 已执行完"}
    skill = fetch_skill_by_name(plan[index])
    if skill is None:
        error = f"计划中的技能不存在或已失效: {plan[index]}"
        return {"error": error, "current_index": index + 1}
    step = execute_skill(
        skill,
        user_input=state["user_input"],
        run_id=state["run_id"],
        step_index=index,
        artifacts=state.get("artifacts") or {},
    )
    insert_step(state["run_id"], step)
    artifacts = dict(state.get("artifacts") or {})
    error = ""
    if step.status == "ok":
        artifacts[skill.skill_name] = step.output
    else:
        error = step.error
    return {
        "artifacts": artifacts,
        "steps": [step.model_dump()],
        "current_index": index + 1,
        "error": error,
    }


def _assemble_node(state: AgentState) -> dict[str, Any]:
    status = state.get("match_status") or "unmatched"
    error = state.get("error") or ""
    chunks: list[str] = [f"任务：{state['user_input']}", f"匹配：{status} / {state.get('route_reason')}"]
    if status == "need_confirm":
        chunks.append("已暂停，等待用户确认技能。")
        run_status = "waiting_confirm"
    elif status in {"answer", "unsupported"}:
        chunks.append(state.get("answer") or "")
        run_status = status
    elif error:
        chunks.append(f"中断原因：{error}")
        chunks.append("已执行：" + " -> ".join((state.get("plan") or [])[: state.get("current_index") or 0]))
        run_status = "error"
    else:
        chunks.append("执行计划：" + " -> ".join(state.get("plan") or []))
        artifacts = state.get("artifacts") or {}
        for name in state.get("plan") or []:
            chunks.append(f"\n## {name}\n{_format_artifact(artifacts.get(name))}")
        run_status = "succeeded"
    final_output = "\n".join(part for part in chunks if part).strip()
    finish_run(state["run_id"], run_status, final_output)
    return {"final_output": final_output, "error": error}


def _format_artifact(value: Any) -> str:
    if value is None:
        return "（无输出）"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        skip = {"tool_trace"}
        lines = []
        for key, item in value.items():
            if key in skip:
                continue
            lines.append(f"- {key}: {item}")
        return "\n".join(lines) or str(value)
    return str(value)


def _after_match(state: AgentState) -> Literal["confirm", "execute", "assemble"]:
    if state.get("match_status") == "need_confirm":
        return "confirm"
    if state.get("match_status") == "matched" and state.get("plan"):
        return "execute"
    return "assemble"


def _after_confirm(state: AgentState) -> Literal["execute", "assemble"]:
    if state.get("match_status") == "matched" and state.get("plan"):
        return "execute"
    return "assemble"


def _after_execute(state: AgentState) -> Literal["execute", "assemble"]:
    if state.get("error"):
        return "assemble"
    index = state.get("current_index") or 0
    plan = state.get("plan") or []
    if index < len(plan):
        return "execute"
    return "assemble"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("match", _match_node)
    graph.add_node("confirm", _confirm_node)
    graph.add_node("execute", _execute_node)
    graph.add_node("assemble", _assemble_node)
    graph.add_edge(START, "match")
    graph.add_conditional_edges(
        "match",
        _after_match,
        {"confirm": "confirm", "execute": "execute", "assemble": "assemble"},
    )
    graph.add_conditional_edges("confirm", _after_confirm, {"execute": "execute", "assemble": "assemble"})
    graph.add_conditional_edges("execute", _after_execute, {"execute": "execute", "assemble": "assemble"})
    graph.add_edge("assemble", END)
    return graph


def _invoke(compiled, payload: Any, run_id: str, user_input: str) -> dict[str, Any]:
    settings = get_settings()
    config: RunnableConfig = {
        "configurable": {"thread_id": run_id},
        "run_name": f"short-play:{user_input[:48]}",
        "tags": ["ai-short-play", "langgraph"],
        "metadata": {"run_id": run_id},
    }
    with tracing_context(
        enabled=settings.langsmith_enabled,
        project_name=settings.langsmith_project,
    ):
        result = compiled.invoke(payload, config)
    if pending_interrupts(result):
        update_run_status(run_id, "waiting_confirm")
    return result


def run_task(user_input: str, *, force_skill: str | None = None, thread_id: str | None = None) -> dict[str, Any]:
    configure_tracing()
    init_schema()
    run_id = thread_id or str(uuid4())
    graph = build_graph()
    initial: AgentState = {
        "user_input": user_input,
        "run_id": run_id,
        "force_skill": force_skill or "",
        "match_status": "",
        "route_reason": "",
        "match_score": 0.0,
        "answer": "",
        "plan": [],
        "current_index": 0,
        "artifacts": {},
        "confirm_candidates": [],
        "steps": [],
        "final_output": "",
        "error": "",
    }
    settings = get_settings()
    with PostgresSaver.from_conn_string(settings.postgres_dsn) as checkpointer:
        checkpointer.setup()
        compiled = graph.compile(checkpointer=checkpointer)
        return _invoke(compiled, initial, run_id, user_input)


def resume_task(thread_id: str, chosen: str, *, user_input: str = "") -> dict[str, Any]:
    configure_tracing()
    init_schema()
    settings = get_settings()
    graph = build_graph()
    with PostgresSaver.from_conn_string(settings.postgres_dsn) as checkpointer:
        checkpointer.setup()
        compiled = graph.compile(checkpointer=checkpointer)
        return _invoke(compiled, Command(resume=chosen), thread_id, user_input or thread_id)
