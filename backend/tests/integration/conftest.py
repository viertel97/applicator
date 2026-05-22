import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from app.api.deps import db_dep
from app.auth.session import create_session
from app.db import models  # noqa: F401 — register all ORM models with Base
from app.db.models import AnschreibenVariant, Application, CVVariant, User
from app.db.session import Base


class _FakeLock:
    """Minimal lock compatible with redis-py Lock API."""

    def __init__(self):
        self._held = False

    def acquire(self, blocking=True):
        if self._held:
            return False
        self._held = True
        return True

    def release(self):
        self._held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


class _FakeRedis:
    """Minimal Redis stub that supports .lock()."""

    def __init__(self):
        self._locks: dict = {}

    def lock(self, name, timeout=None, blocking_timeout=None):
        if name not in self._locks:
            self._locks[name] = _FakeLock()
        return self._locks[name]


@pytest.fixture(autouse=True)
def fake_redis_client(monkeypatch):
    """Replace redis.Redis.from_url with an in-process stub."""
    fake = _FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake)
    return fake


@pytest.fixture(autouse=True)
def reset_db_session_singletons():
    """Reset the SQLAlchemy engine/session singletons between tests.

    The task module uses get_session_factory() which caches a module-level
    engine. After each test drops and recreates tables (including enum types),
    the cached engine's psycopg type cache becomes stale and causes
    'cache lookup failed for type' errors on the next test.
    """
    import app.db.session as sess_mod
    yield
    if sess_mod._engine is not None:
        try:
            sess_mod._engine.dispose()
        except Exception:
            pass
    sess_mod._engine = None
    sess_mod._SessionLocal = None


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
def db_session(pg_container, monkeypatch):
    raw_url = pg_container.get_connection_url()
    url = (
        raw_url
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = session_factory()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def app_client(db_session, monkeypatch):
    # Required env for Settings()
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("MS_TENANT_ID", "t")
    monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from app.main import create_app
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[db_dep] = override_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_user(db_session, app_client):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u)
    db_session.flush()
    db_session.add_all([
        CVVariant(user_id=u.id, name="cv", source_md="cv", is_default=True),
        AnschreibenVariant(user_id=u.id, name="an", source_md="an", is_default=True),
    ])
    db_session.commit()
    db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    return app_client, u


@pytest.fixture
def client(auth_user):
    """Authenticated TestClient for tests that use client + db_session separately."""
    app_client, _ = auth_user
    return app_client


@pytest.fixture
def no_celery(monkeypatch):
    from app.api import applications as apps_module
    monkeypatch.setattr(apps_module, "_start_crawl_chain", lambda app_id: None)
    monkeypatch.setattr(apps_module, "_start_generate", lambda app_id: None)


@pytest.fixture
def client(auth_user):
    c, _ = auth_user
    return c


@pytest.fixture
def sample_application(auth_user, db_session):
    _, user = auth_user
    app_row = Application(
        user_id=user.id,
        url="https://x.test/sample",
        url_hash="s" * 64,
    )
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(app_row)
    return str(app_row.id)
