from typing import Any, NotRequired, TypedDict

from typing_extensions import Annotated
import operator


class AgentState(TypedDict):
    user_input: str
    run_id: str
    force_skills: list[str]
    catalog: list[dict[str, Any]]
    plan: list[str]
    route_reason: str
    route_strategy: str
    current_index: int
    current_skill_name: str
    current_skill_body: str
    artifacts: dict[str, Any]
    steps: Annotated[list[dict[str, Any]], operator.add]
    final_output: str
    error: NotRequired[str]
