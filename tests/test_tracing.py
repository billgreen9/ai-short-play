from app.config import get_settings
from app.tracing import configure_tracing, tracing_status_line


def test_langsmith_settings_alias_and_status() -> None:
    settings = get_settings()
    assert settings.langsmith_project
    configure_tracing()
    line = tracing_status_line()
    assert "LangSmith" in line
