from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/reddit_agent"

    LLM_PROVIDER: str = "anthropic"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "claude-opus-5"

    EMBEDDING_PROVIDER: str = "voyage"
    VOYAGE_API_KEY: str = ""
    EMBEDDING_MODEL: str = "voyage-3"

    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = ""
    REDDIT_USERNAME: str = ""
    REDDIT_PASSWORD: str = ""

    APP_BASE_URL: str = "http://localhost:8000"

    # Application-level publishing rate limits (spec section 23). Conservative
    # defaults -- this is not a mass-posting tool.
    MAX_PUBLICATIONS_PER_DAY: int = 5
    MAX_PUBLICATIONS_PER_HOUR: int = 2
    MIN_PUBLICATION_INTERVAL_SECONDS: int = 600
    MAX_PUBLICATIONS_PER_SUBREDDIT_PER_DAY: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
