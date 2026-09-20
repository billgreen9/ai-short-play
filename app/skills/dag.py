from __future__ import annotations

from collections.abc import Callable

from app.models import SkillRecord


class SkillDagError(ValueError):
    pass


def expand_skill_dag(
    entry: SkillRecord,
    load_by_name: Callable[[str], SkillRecord | None],
) -> list[SkillRecord]:
    """递归展开 depends_on，返回可执行的拓扑顺序。"""
    order: list[SkillRecord] = []
    done: set[str] = set()
    visiting: set[str] = set()

    def walk(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = " -> ".join([*visiting, name])
            raise SkillDagError(f"技能依赖成环: {cycle}")
        visiting.add(name)
        skill = entry if name == entry.skill_name else load_by_name(name)
        if skill is None:
            raise SkillDagError(f"依赖技能不存在或已失效: {name}")
        for dep in skill.dependency_names():
            walk(dep)
        visiting.remove(name)
        done.add(name)
        order.append(skill)

    walk(entry.skill_name)
    return order
