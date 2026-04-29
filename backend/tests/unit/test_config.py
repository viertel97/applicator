import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import Settings


def _base_env(monkeypatch, *, app_secret_key: str):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x")
    monkeypatch.setenv("APP_SECRET_KEY", app_secret_key)
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://x/cb")
    monkeypatch.setenv("LLM_API_KEY", "k")


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x")
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
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


def test_valid_fernet_key_accepted(monkeypatch):
    valid_key = Fernet.generate_key().decode()
    _base_env(monkeypatch, app_secret_key=valid_key)
    s = Settings()
    assert s.app_secret_key == valid_key


def test_garbage_fernet_key_raises(monkeypatch):
    _base_env(monkeypatch, app_secret_key="change-me-fernet-key")
    with pytest.raises(ValidationError):
        Settings()


def test_wrong_length_key_raises(monkeypatch):
    _base_env(monkeypatch, app_secret_key="tooshort")
    with pytest.raises(ValidationError):
        Settings()
