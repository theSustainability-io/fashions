from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", env="OPENAI_MODEL")

    shopify_store_domain: Optional[str] = Field(
        default=None, env="SHOPIFY_STORE_DOMAIN"
    )
    shopify_access_token: Optional[str] = Field(
        default=None, env="SHOPIFY_ACCESS_TOKEN"
    )

    input_dir: Path = Field(default=Path("./input"), env="INPUT_DIR")
    output_dir: Path = Field(default=Path("./output"), env="OUTPUT_DIR")
    prompt_file: Path = Field(default=Path("./prompts.json"), env="PROMPT_FILE")

    poll_interval_minutes: int = Field(default=1440, env="POLL_INTERVAL_MINUTES")
    enable_background_runner: bool = Field(default=False, env="ENABLE_BACKGROUND_RUNNER")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("input_dir", "output_dir", "prompt_file", mode="before")
    @classmethod
    def _ensure_path(cls, value):  # type: ignore[override]
        if value is None:
            return value
        return Path(value)


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.prompt_file.parent.mkdir(parents=True, exist_ok=True)
    return settings
