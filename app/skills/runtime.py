from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillRuntime:
    user_input: str
    run_id: str
    skill_name: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    saved_result: dict[str, Any] | None = None


_RUNTIME: SkillRuntime | None = None


def get_runtime() -> SkillRuntime:
    if _RUNTIME is None:
        raise RuntimeError("当前没有正在执行的 skill")
    return _RUNTIME


def set_runtime(runtime: SkillRuntime | None) -> SkillRuntime | None:
    global _RUNTIME
    previous = _RUNTIME
    _RUNTIME = runtime
    return previous
