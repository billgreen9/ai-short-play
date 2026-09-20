from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SkillMeta(BaseModel):
    """L1: frontmatter + tool_schema. Body/reference stay on disk until selected."""

    name: str
    description: str
    category: str
    rel_path: str
    skill_dir: str
    skill_file: str
    sort_order: int = 100
    depends_on: list[str] = Field(default_factory=list)
    disable_model_invocation: bool = False
    scripts: list[str] = Field(default_factory=list)
    script_path: str = ""
    tool_schema: dict[str, Any] = Field(default_factory=dict)
    input_schema_file: str = ""
    output_schema_file: str = ""
    pipeline: str = "writing"


class SkillReference(BaseModel):
    examples: dict[str, Any] = Field(default_factory=dict)
    enums: dict[str, str] = Field(default_factory=dict)
    specs: dict[str, str] = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)


class SkillRecord(SkillMeta):
    body: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    reference: SkillReference = Field(default_factory=SkillReference)


class RouteDecision(BaseModel):
    query: str
    plan: list[str]
    scores: dict[str, float] = Field(default_factory=dict)
    reason: str = ""
    strategy: str = "lexical"


class StepResult(BaseModel):
    skill_name: str
    step_index: int
    status: str
    script_path: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
