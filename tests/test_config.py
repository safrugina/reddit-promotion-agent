from app.config import Settings


def test_settings_defaults_from_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "test"
    assert settings.LLM_PROVIDER == "anthropic"
    assert settings.LLM_API_KEY == "sk-test"


def test_settings_have_sane_fallback_defaults():
    settings = Settings(_env_file=None, APP_ENV="development")

    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert settings.APP_BASE_URL == "http://localhost:8000"
