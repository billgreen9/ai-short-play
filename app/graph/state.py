from typing import Any, NotRequired, TypedDict

from typing_extensions import Annotated
import operator


class AgentState(TypedDict):
    user_input: str
    run_id: str
    force_skill: str
    match_status: str
    route_reason: str
    match_score: float
    answer: str
    plan: list[str]
    current_index: int
    artifacts: dict[str, Any]
    confirm_candidates: list[dict[str, Any]]
    steps: Annotated[list[dict[str, Any]], operator.add]
    final_output: str
    error: NotRequired[str]
