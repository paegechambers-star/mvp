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

    # Localisation — Termine ohne Zeitzonenangabe gelten als Ortszeit dieser Zone
    timezone: str = "Europe/Berlin"

    # Logging
    log_level: str = "INFO"

    # CORS — JSON array in env: CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Optional integrations
    anthropic_api_key: str = ""
    # G.O.D.A.I.-Backend: "" = automatisch (SCRIPTOR-Einstellung, sonst Claude mit Key,
    # sonst Echo) | "anthropic" | "ollama" | "echo"
    llm_provider: str = ""
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    redis_url: str = ""


settings = Settings()
