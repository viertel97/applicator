from app.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x")
    monkeypatch.setenv("APP_SECRET_KEY", "k" * 44)
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://x/cb")
    monkeypatch.setenv("LLM_API_KEY", "k")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://x"
    assert s.llm_provider == "groq"
    assert s.llm_model == "gpt-oss"
    assert s.data_dir.endswith("data")
