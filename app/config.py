from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    postgres_dsn: str = "postgresql://postgres:123456@localhost:5432/short-play"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "doubao-embedding-vision-251215"
    embedding_dim: int = 2048
    score_limit: float = 0.72
    score_confirm_limit: float = 0.45
    match_top_k: int = 20
    hybrid_keyword_weight: float = 0.4
    llm_rerank_weight: float = 0.7
    llm_timeout_seconds: float = 120.0
    llm_rerank_timeout_seconds: float = 20.0
    max_tool_rounds: int = 8
    langsmith_tracing: bool = Field(
        default=True,
        validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"),
    )
    langsmith_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    langsmith_project: str = Field(
        default="ai-short-play",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )
    langsmith_endpoint: str = Field(default="", validation_alias=AliasChoices("LANGSMITH_ENDPOINT"))
    langsmith_workspace_id: str = Field(
        default="",
        validation_alias=AliasChoices("LANGSMITH_WORKSPACE_ID"),
    )

    @property
    def langsmith_enabled(self) -> bool:
        return bool(self.langsmith_tracing and self.langsmith_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
