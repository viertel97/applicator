import os

import pytest
from fastapi.testclient import TestClient

# Set env defaults before any app module is imported during test collection.
# monkeypatch fixtures run after imports, so these module-level defaults ensure
# get_settings() / celery_app construction never sees missing env vars.
os.environ.setdefault("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
os.environ.setdefault("MS_TENANT_ID", "test-tenant")
os.environ.setdefault("MS_CLIENT_ID", "test-client")
os.environ.setdefault("MS_CLIENT_SECRET", "test-secret")
os.environ.setdefault("MS_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
os.environ.setdefault("LLM_API_KEY", "test-llm-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    from app.main import create_app
    return TestClient(create_app())
