from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "zomato-ai-powered-recommender"
    dataset_url: str = Field(..., validation_alias="DATASET_URL")
    gemini_api_key: str = Field(..., validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.5-flash", validation_alias="GEMINI_MODEL")
    request_timeout_seconds: int = Field(30, validation_alias="REQUEST_TIMEOUT_SECONDS")
    default_candidate_limit: int = Field(20, validation_alias="DEFAULT_CANDIDATE_LIMIT")
    default_result_limit: int = Field(5, validation_alias="DEFAULT_RESULT_LIMIT")
    server_host: str = Field("0.0.0.0", validation_alias="SERVER_HOST")
    server_port: int = Field(8000, validation_alias="SERVER_PORT")
    environment: Literal["development", "production", "test"] = "development"

    @field_validator("dataset_url", "gemini_api_key")
    @classmethod
    def validate_required_strings(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("This setting is required and cannot be blank.")
        return value.strip()


@lru_cache

def get_settings() -> Settings:
    return Settings()
