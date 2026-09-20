from app.models import SkillRecord
from app.skills.dag import SkillDagError, expand_skill_dag
import pytest


def _skill(name: str, depends_on: str | None = None) -> SkillRecord:
    return SkillRecord(id=hash(name) % 10000, skill_name=name, depends_on=depends_on)


def test_linear_dag_order():
    catalog = {
        "a": _skill("a"),
        "b": _skill("b", "a"),
        "c": _skill("c", "b"),
    }
    plan = expand_skill_dag(catalog["c"], catalog.get)
    assert [item.skill_name for item in plan] == ["a", "b", "c"]


def test_diamond_dag_loads_shared_dep_once():
    catalog = {
        "a": _skill("a"),
        "b": _skill("b", "a"),
        "c": _skill("c", "a"),
        "d": _skill("d", "b,c"),
    }
    plan = expand_skill_dag(catalog["d"], catalog.get)
    names = [item.skill_name for item in plan]
    assert names[0] == "a"
    assert names[-1] == "d"
    assert set(names) == {"a", "b", "c", "d"}
    assert len(names) == 4


def test_cycle_raises():
    catalog = {
        "a": _skill("a", "b"),
        "b": _skill("b", "a"),
    }
    with pytest.raises(SkillDagError, match="成环"):
        expand_skill_dag(catalog["a"], catalog.get)


def test_missing_dependency_raises():
    catalog = {"a": _skill("a", "ghost")}
    with pytest.raises(SkillDagError, match="不存在"):
        expand_skill_dag(catalog["a"], catalog.get)
