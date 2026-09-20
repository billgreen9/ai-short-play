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
    skills_dir: Path = Field(default=Path("skills"))
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    script_timeout_seconds: int = 90
    media_cdn_base: str = "https://cdn.short-play.local/assets"
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

    @property
    def skills_root(self) -> Path:
        path = self.skills_dir
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
