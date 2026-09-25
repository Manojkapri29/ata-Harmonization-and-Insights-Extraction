"""Runtime configuration. Every secret comes from environment variables / .env - never from code."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
                                      env_file_encoding="utf-8", extra="ignore")

    app_name: str = "JobPilot AI"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'jobpilot.db'}"
    storage_dir: Path = BACKEND_DIR / "data" / "files"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_url: str = "http://localhost:5173"

    # background scheduler for search profiles with auto-run enabled
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 60
    task_workers: int = 2

    # polite fetching
    http_user_agent: str = "JobPilotAI/1.0 (personal job search assistant)"
    http_timeout_seconds: int = 20
    min_seconds_between_requests_per_domain: float = 2.0

    # AI provider: none | openai | anthropic | ollama
    ai_provider: str = "none"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: str = "low"          # short rewrite tasks do well at low effort
    anthropic_fallbacks: bool = True       # server-side fallback model on refusals
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ai_timeout_seconds: int = 120

    # job source credentials (all optional)
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite:///"):
        Path(s.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return s
