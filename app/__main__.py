from __future__ import annotations

import argparse
import json
import sys

from app.db import fetch_skill_by_name, init_schema, list_skills, load_run
from app.graph.confirm import format_confirm_prompt, interrupt_value
from app.graph.workflow import resume_task, run_task
from app.matching import match_intent
from app.skills.dag import expand_skill_dag
from app.skills.seed import seed_default_skills
from app.skills.store import add_skill, backfill_intent_embeddings
from app.tools import list_tool_names
from app.tracing import configure_tracing, tracing_status_line


def _init_db(seed: bool = True) -> None:
    init_schema()
    if seed:
        seed_default_skills()
        print("已初始化 skill / intent_match，并写入默认技能。")
    else:
        print("已初始化 skill / intent_match 表结构。")


def _list_skills() -> None:
    init_schema()
    skills = list_skills()
    if not skills:
        print("还没有有效技能，先运行 python -m app --init-db")
        return
    print("有效技能：")
    for skill in skills:
        deps = skill.depends_on or "-"
        tools = skill.function_tools or "-"
        print(f"  - {skill.skill_name}: {skill.description}")
        print(f"      depends_on={deps}  tools={tools}")


def _preview_route(query: str, force: str | None) -> None:
    init_schema()
    if force:
        skill = fetch_skill_by_name(force)
        payload = {
            "status": "matched" if skill else "unmatched",
            "force_skill": force,
            "plan": [item.skill_name for item in expand_skill_dag(skill, fetch_skill_by_name)] if skill else [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    decision = match_intent(query)
    data = decision.model_dump()
    if decision.skill:
        data["plan"] = [item.skill_name for item in expand_skill_dag(decision.skill, fetch_skill_by_name)]
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按 intent_match 匹配数据库 skill，并按 depends_on DAG 执行")
    parser.add_argument("query", nargs="?", help="用户任务，例如：写一个职场复仇短剧")
    parser.add_argument("--init-db", action="store_true", help="创建表并写入默认技能")
    parser.add_argument("--no-seed", action="store_true", help="只建表，不写入默认技能")
    parser.add_argument("--list", action="store_true", help="列出有效技能")
    parser.add_argument("--list-tools", action="store_true", help="列出可注册的 function tools")
    parser.add_argument("--route-only", action="store_true", help="只做意图匹配，不执行")
    parser.add_argument("--use-skill", metavar="NAME", help="跳过匹配，直接按该 skill 及其依赖 DAG 执行")
    parser.add_argument("--add-skill", action="store_true", help="新增或更新一个 skill，并同步写入 intent_match")
    parser.add_argument("--backfill-embeddings", action="store_true", help="为 intent_match 补写或刷新 msg_embedding")
    parser.add_argument("--name", help="skill_name")
    parser.add_argument("--description", help="skill description，同时作为 intent_match.msg")
    parser.add_argument("--prompt", help="skill_prompt")
    parser.add_argument("--tools", default="", help="function_tools，逗号分隔")
    parser.add_argument("--depends-on", default="", help="depends_on，逗号分隔 skill_name")
    args = parser.parse_args(argv)
    configure_tracing()

    if args.init_db:
        _init_db(seed=not args.no_seed)
        return 0
    if args.list:
        _list_skills()
        return 0
    if args.list_tools:
        print("\n".join(list_tool_names()) or "(无)")
        return 0
    if args.backfill_embeddings:
        init_schema()
        stats = backfill_intent_embeddings(only_missing=True)
        print(
            "embedding 回填完成 "
            f"total={stats['total']} updated={stats['updated']} "
            f"skipped={stats['skipped']} failed={stats['failed']}"
        )
        return 0 if stats["failed"] == 0 or stats["updated"] > 0 else 1
    if args.add_skill:
        if not args.name or not args.description or args.prompt is None:
            parser.error("--add-skill 需要 --name --description --prompt")
        init_schema()
        skill = add_skill(
            skill_name=args.name,
            description=args.description,
            skill_prompt=args.prompt,
            function_tools=args.tools,
            depends_on=args.depends_on or None,
        )
        print(json.dumps(skill.model_dump(), ensure_ascii=False, indent=2))
        return 0
    if not args.query:
        parser.print_help()
        return 1
    if args.route_only:
        _preview_route(args.query, args.use_skill)
        return 0

    result = run_task(args.query, force_skill=args.use_skill)
    payload = interrupt_value(result)
    if payload:
        print(format_confirm_prompt(payload))
        if not sys.stdin.isatty():
            print(f"\n图已暂停，等待用户输入。run_id={result.get('run_id')}")
            print(f"\n{tracing_status_line()}")
            return 0
        chosen = input().strip()
        result = resume_task(str(result["run_id"]), chosen, user_input=args.query)
    print(result.get("final_output") or "")
    print(f"\n{tracing_status_line()}")
    if result.get("error"):
        print(f"\n[error] {result['error']}", file=sys.stderr)
        return 1
    run = load_run(result["run_id"])
    if run:
        print(f"\nrun_id={run['id']} status={run['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
