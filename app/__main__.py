from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.db import init_schema, load_final_cut, load_run, upsert_skills
from app.graph.workflow import run_task
from app.skills.loader import discover_skills
from app.skills.router import SkillRouter
from app.skills.tools import assemble_openai_tools
from app.tracing import configure_tracing, tracing_status_line


def _list_skills() -> None:
    skills = discover_skills(get_settings().skills_root)
    init_schema()
    upsert_skills(skills)
    grouped: dict[str, list[str]] = {}
    for skill in skills:
        grouped.setdefault(skill.category, []).append(skill.name)
    print("已发现的多级 skills：")
    for category, names in grouped.items():
        print(f"  {category}/")
        for name in names:
            skill = next(item for item in skills if item.name == name)
            print(f"    - {name}: {skill.description}")


def _preview_route(query: str, force: list[str]) -> None:
    skills = discover_skills(get_settings().skills_root)
    decision = SkillRouter().route(query, skills, force=force or None, use_llm=False)
    print(json.dumps(decision.model_dump(), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按用户输入路由并逐步执行多级目录 skills")
    parser.add_argument("query", nargs="?", help="用户任务，例如：写一个职场复仇短剧")
    parser.add_argument("--list", action="store_true", help="列出已发现的 skills")
    parser.add_argument("--route-only", action="store_true", help="只跑路由层，不执行脚本")
    parser.add_argument("--dump-tools", action="store_true", help="打印由 tool_schema.json 组装的 OpenAI tools")
    parser.add_argument("--final-url", metavar="RUN_ID", help="查询某次任务发布的成片地址")
    parser.add_argument("--skill", action="append", dest="skills", default=[], help="强制指定 skill，可重复")
    args = parser.parse_args(argv)
    configure_tracing()

    if args.list:
        _list_skills()
        return 0
    if args.dump_tools:
        skills = discover_skills(get_settings().skills_root)
        print(json.dumps(assemble_openai_tools(skills), ensure_ascii=False, indent=2))
        return 0
    if args.final_url:
        init_schema()
        asset = load_final_cut(args.final_url)
        if not asset:
            print(f"run_id={args.final_url} 没有 ready 的 final_cut", file=sys.stderr)
            return 1
        print(json.dumps({
            "run_id": str(asset["run_id"]),
            "output_url": asset["output_url"],
            "from_character": asset["from_character"],
            "to_character": asset["to_character"],
            "status": asset["status"],
        }, ensure_ascii=False, indent=2))
        return 0
    if not args.query:
        parser.print_help()
        return 1
    if args.route_only:
        _preview_route(args.query, args.skills)
        return 0

    result = run_task(args.query, force_skills=args.skills or None)
    print(result.get("final_output") or "")
    print(f"\n{tracing_status_line()}")
    if result.get("error"):
        print(f"\n[error] {result['error']}", file=sys.stderr)
        return 1
    run = load_run(result["run_id"])
    if run:
        print(f"\nrun_id={run['id']} status={run['status']}")
    asset = load_final_cut(result["run_id"])
    if asset and asset.get("output_url"):
        print(f"final_cut={asset['output_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
