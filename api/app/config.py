from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://datadesigner:local-development-only@localhost:5432/datadesigner"
    )
    cookie_secure: bool = True
    session_ttl_hours: int = 12
    login_rate_limit: int = 5
    login_rate_window_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
