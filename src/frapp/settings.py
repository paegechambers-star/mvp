from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FraPP"
    env: str = "dev"
    version: str = "0.0.1"

    # Auth
    api_key: str = "dev-key"
    secret_key: str = "dev-secret-change-in-production"

    # Database
    database_url: str = "sqlite:///./frapp.db"

    # Localisation
    timezone: str = "UTC"

    # Logging
    log_level: str = "INFO"

    # CORS — JSON array in env: CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Optional integrations
    anthropic_api_key: str = ""
    redis_url: str = ""


settings = Settings()
