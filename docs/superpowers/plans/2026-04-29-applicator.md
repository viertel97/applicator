# Applicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Self-hosted job application assistant — paste URL, crawl + LLM-extract, generate Anschreiben from CV/template, refine via chat, track status with interviews.

**Architecture:** FastAPI monolith with React SPA. Async via FastAPI `BackgroundTasks` + DB-stored job state. Microsoft OAuth2. Postgres. Per-module boundaries: crawler, extractor, generator, renderer, llm, auth — each pure and fake-able for tests.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic / httpx / Playwright / python-docx / msal / pydantic-settings ; React / Vite / TypeScript / TanStack Query / Tailwind / shadcn/ui ; Postgres 16 ; docker-compose.

---

## File Structure

### Backend (`backend/`)
```
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app factory
│   ├── config.py                   # pydantic-settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py              # engine, SessionLocal
│   │   └── models.py               # all SQLAlchemy models
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                 # LLMClient protocol
│   │   ├── groq.py                 # GroqClient
│   │   └── fakes.py                # FakeLLM (test only — but lives here for reuse)
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── httpx_fetcher.py
│   │   ├── playwright_fetcher.py
│   │   └── fetcher.py              # hybrid fetch with fallback
│   ├── extractor/
│   │   ├── __init__.py
│   │   ├── schemas.py              # JobPosting pydantic
│   │   └── prompts.py
│   ├── generator/
│   │   ├── __init__.py
│   │   └── prompts.py
│   ├── renderer/
│   │   ├── __init__.py
│   │   ├── docx.py                 # markdown → DOCX
│   │   └── template.docx
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── ms_oauth.py
│   │   └── session.py              # session middleware/dep
│   ├── pipeline.py                 # process_application orchestrator
│   ├── crypto.py                   # Fernet wrappers
│   └── api/
│       ├── __init__.py
│       ├── deps.py                 # shared FastAPI deps
│       ├── auth.py
│       ├── applications.py
│       ├── documents.py            # cv + anschreiben variants
│       ├── chat.py
│       └── interviews.py
└── tests/
    ├── conftest.py
    ├── fakes/
    │   ├── llm.py
    │   ├── fetcher.py
    │   └── browser.py
    ├── unit/
    │   ├── test_crawler.py
    │   ├── test_extractor.py
    │   ├── test_generator.py
    │   ├── test_renderer.py
    │   ├── test_llm_groq.py
    │   └── test_crypto.py
    ├── integration/
    │   ├── test_auth.py
    │   ├── test_documents.py
    │   ├── test_applications.py
    │   ├── test_pipeline.py
    │   ├── test_chat.py
    │   └── test_interviews.py
    └── e2e/
        └── test_happy_path.py
```

### Frontend (`frontend/`)
```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api/
    │   ├── client.ts               # fetch wrapper
    │   ├── auth.ts
    │   ├── applications.ts
    │   ├── documents.ts
    │   ├── chat.ts
    │   └── interviews.ts
    ├── pages/
    │   ├── Login.tsx
    │   ├── ApplicationsList.tsx
    │   ├── ApplicationDetail.tsx
    │   ├── SettingsCV.tsx
    │   ├── SettingsAnschreiben.tsx
    │   └── SettingsLLM.tsx
    ├── components/
    │   ├── AddApplicationForm.tsx
    │   ├── StatusBadge.tsx
    │   ├── JobPostingPanel.tsx
    │   ├── AnschreibenEditor.tsx
    │   ├── ChatPanel.tsx
    │   └── InterviewsList.tsx
    ├── hooks/
    │   ├── useAuth.ts
    │   └── useApplication.ts
    └── tests/
        └── e2e.spec.ts
```

### Root
```
docker-compose.yml
.env.example
README.md
```

---

## Task 0: Repository Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
node_modules/
dist/
build/
.pytest_cache/
.mypy_cache/
data/
*.docx
!backend/app/renderer/template.docx
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "applicator-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "psycopg[binary]>=3.2",
  "pydantic>=2.7",
  "pydantic-settings>=2.4",
  "httpx>=0.27",
  "playwright>=1.45",
  "python-docx>=1.1",
  "msal>=1.30",
  "cryptography>=43",
  "openai>=1.40",
  "markdown>=3.6",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "pytest-cov>=5",
  "ruff>=0.5",
  "mypy>=1.10",
  "testcontainers[postgres]>=4.7",
  "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "ASYNC"]
```

- [ ] **Step 3: Create `backend/app/__init__.py` (empty)** and `backend/tests/__init__.py` (empty).

- [ ] **Step 4: Create `backend/app/main.py`**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Applicator", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Create `backend/tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
```

- [ ] **Step 6: Write health-check test**

Create `backend/tests/unit/__init__.py` (empty), then `backend/tests/unit/test_health.py`:

```python
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 7: Install and run tests**

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/test_health.py -v
```
Expected: 1 passed.

- [ ] **Step 8: Create `.env.example`**

```
DATABASE_URL=postgresql+psycopg://applicator:applicator@localhost:5432/applicator
APP_SECRET_KEY=change-me-fernet-key
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_REDIRECT_URI=http://localhost:8000/api/auth/callback
LLM_PROVIDER=groq
LLM_MODEL=gpt-oss
LLM_API_KEY=
LLM_BASE_URL=https://api.groq.com/openai/v1
DATA_DIR=./data
FRONTEND_ORIGIN=http://localhost:5173
SESSION_COOKIE_NAME=applicator_session
SESSION_COOKIE_SECURE=false
```

- [ ] **Step 9: Create minimal `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: applicator
      POSTGRES_USER: applicator
      POSTGRES_PASSWORD: applicator
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
volumes:
  pgdata:
```

- [ ] **Step 10: Commit**

```bash
git add backend/ .gitignore .env.example docker-compose.yml
git commit -m "chore: scaffold backend project"
```

---

## Task 1: Config

**Files:**
- Create: `backend/app/config.py`
- Test: `backend/tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
import os
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
```

- [ ] **Step 2: Run — expect FAIL (module missing)**

```bash
pytest backend/tests/unit/test_config.py -v
```

- [ ] **Step 3: Implement `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_secret_key: str
    ms_tenant_id: str
    ms_client_id: str
    ms_client_secret: str
    ms_redirect_uri: str
    llm_provider: str = "groq"
    llm_model: str = "gpt-oss"
    llm_api_key: str
    llm_base_url: str = "https://api.groq.com/openai/v1"
    data_dir: str = "./data"
    frontend_origin: str = "http://localhost:5173"
    session_cookie_name: str = "applicator_session"
    session_cookie_secure: bool = False


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/unit/test_config.py
git commit -m "feat(config): pydantic settings"
```

---

## Task 2: Crypto helpers (Fernet)

**Files:**
- Create: `backend/app/crypto.py`
- Test: `backend/tests/unit/test_crypto.py`

- [ ] **Step 1: Write tests**

```python
from app.crypto import encrypt, decrypt, generate_key


def test_roundtrip():
    key = generate_key()
    ct = encrypt("hello", key)
    assert ct != "hello"
    assert decrypt(ct, key) == "hello"


def test_decrypt_wrong_key_raises():
    import pytest
    from cryptography.fernet import InvalidToken

    ct = encrypt("hello", generate_key())
    with pytest.raises(InvalidToken):
        decrypt(ct, generate_key())
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement `backend/app/crypto.py`**

```python
from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encrypt(plaintext: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/crypto.py backend/tests/unit/test_crypto.py
git commit -m "feat(crypto): fernet helpers"
```

---

## Task 3: Database models

**Files:**
- Create: `backend/app/db/__init__.py` (empty)
- Create: `backend/app/db/session.py`
- Create: `backend/app/db/models.py`
- Test: `backend/tests/integration/__init__.py` (empty), `backend/tests/integration/conftest.py`, `backend/tests/integration/test_models.py`

- [ ] **Step 1: Create `backend/app/db/session.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

Base = declarative_base()
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, future=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()
```

- [ ] **Step 2: Create `backend/app/db/models.py`**

```python
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    applied = "applied"
    offer = "offer"
    rejected = "rejected"
    accepted = "accepted"
    withdrawn = "withdrawn"


class JobState(str, enum.Enum):
    pending = "pending"
    crawling = "crawling"
    extracting = "extracting"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class InterviewKind(str, enum.Enum):
    phone = "phone"
    video = "video"
    onsite = "onsite"
    technical = "technical"
    final = "final"


class InterviewOutcome(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    cancelled = "cancelled"


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ms_oid: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    ms_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CVVariant(Base):
    __tablename__ = "cv_variant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_md: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnschreibenVariant(Base):
    __tablename__ = "anschreiben_variant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_md: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (UniqueConstraint("user_id", "url_hash", name="uq_user_url_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.draft
    )
    cv_variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cv_variant.id"))
    anschreiben_variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anschreiben_variant.id")
    )
    generated_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    job_state: Mapped[JobState] = mapped_column(Enum(JobState), default=JobState.pending)
    job_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    job_posting: Mapped[JobPosting | None] = relationship(
        "JobPosting", uselist=False, back_populates="application"
    )


class JobPosting(Base):
    __tablename__ = "job_posting"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id"), unique=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_person: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    benefits: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped[Application] = relationship("Application", back_populates="job_posting")


class Interview(Base):
    __tablename__ = "interview"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[InterviewKind] = mapped_column(Enum(InterviewKind))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[InterviewOutcome] = mapped_column(
        Enum(InterviewOutcome), default=InterviewOutcome.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application.id"))
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Session(Base):
    __tablename__ = "session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 3: Set up alembic**

```bash
cd backend && alembic init alembic
```

Edit `backend/alembic/env.py` — replace the `target_metadata = None` line with:

```python
from app.db.session import Base
from app.db import models  # noqa: F401  ensure models registered
from app.config import get_settings

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", get_settings().database_url)
```

- [ ] **Step 4: Generate the initial migration**

Start db: `docker compose up -d db` (from repo root).

```bash
cd backend && alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

- [ ] **Step 5: Create `backend/tests/integration/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from app.db.session import Base


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
def db_session(pg_container, monkeypatch):
    url = pg_container.get_connection_url().replace("postgresql://", "postgresql+psycopg://")
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(engine)
```

- [ ] **Step 6: Write `backend/tests/integration/test_models.py`**

```python
import uuid

from app.db.models import (
    Application,
    AnschreibenVariant,
    ApplicationStatus,
    CVVariant,
    JobState,
    User,
)


def test_create_application(db_session, monkeypatch):
    # need env vars for Settings inside session module
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u); db_session.flush()
    cv = CVVariant(user_id=u.id, name="default", source_md="cv", is_default=True)
    an = AnschreibenVariant(user_id=u.id, name="default", source_md="an", is_default=True)
    db_session.add_all([cv, an]); db_session.flush()
    app = Application(
        user_id=u.id, url="http://x", url_hash="h",
        cv_variant_id=cv.id, anschreiben_variant_id=an.id,
    )
    db_session.add(app); db_session.commit()
    fetched = db_session.get(Application, app.id)
    assert fetched.status == ApplicationStatus.draft
    assert fetched.job_state == JobState.pending
```

- [ ] **Step 7: Run — expect PASS**

```bash
pytest backend/tests/integration/test_models.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/ backend/alembic/ backend/alembic.ini backend/tests/integration/
git commit -m "feat(db): models, alembic init, integration test scaffolding"
```

---

## Task 4: LLM client — protocol + FakeLLM

**Files:**
- Create: `backend/app/llm/__init__.py` (empty)
- Create: `backend/app/llm/base.py`
- Create: `backend/tests/fakes/__init__.py` (empty)
- Create: `backend/tests/fakes/llm.py`
- Test: `backend/tests/unit/test_fake_llm.py`

- [ ] **Step 1: Define the protocol — `backend/app/llm/base.py`**

```python
from typing import Any, Protocol


class LLMMessage(dict):
    """Just a dict with role/content keys."""


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Return assistant text. If json_schema given, response is valid JSON for it."""
        ...
```

- [ ] **Step 2: Create FakeLLM — `backend/tests/fakes/llm.py`**

```python
from collections.abc import Callable
from typing import Any


class FakeLLM:
    def __init__(self, handler: Callable[[list[dict], dict | None], str] | None = None):
        self.calls: list[tuple[list[dict], dict | None]] = []
        self.handler = handler or (lambda msgs, schema: "FAKE_RESPONSE")

    def complete(self, messages, *, json_schema=None, temperature=0.2):
        self.calls.append((messages, json_schema))
        return self.handler(messages, json_schema)
```

- [ ] **Step 3: Test the fake — `backend/tests/unit/test_fake_llm.py`**

```python
from tests.fakes.llm import FakeLLM


def test_fake_records_calls():
    f = FakeLLM(handler=lambda m, s: "ok")
    out = f.complete([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert len(f.calls) == 1
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/ backend/tests/fakes/ backend/tests/unit/test_fake_llm.py
git commit -m "feat(llm): protocol and FakeLLM"
```

---

## Task 5: Groq client

**Files:**
- Create: `backend/app/llm/groq.py`
- Test: `backend/tests/unit/test_llm_groq.py`

- [ ] **Step 1: Write tests using `respx` to mock OpenAI-compatible HTTP**

```python
import json
import httpx
import respx

from app.llm.groq import GroqClient


def test_groq_plain():
    client = GroqClient(api_key="k", model="gpt-oss", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "hello"}}],
                },
            )
        )
        out = client.complete([{"role": "user", "content": "hi"}])
    assert out == "hello"
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "gpt-oss"


def test_groq_json_schema():
    client = GroqClient(api_key="k", model="gpt-oss", base_url="https://api.groq.com/openai/v1")
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"a":1}'}}]},
            )
        )
        out = client.complete(
            [{"role": "user", "content": "hi"}],
            json_schema={"type": "object", "properties": {"a": {"type": "integer"}}},
        )
    assert out == '{"a":1}'
```

- [ ] **Step 2: Run — expect FAIL (missing module).**

- [ ] **Step 3: Implement `backend/app/llm/groq.py`**

```python
from typing import Any

import httpx


class GroqClient:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "schema", "schema": json_schema, "strict": True},
            }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/groq.py backend/tests/unit/test_llm_groq.py
git commit -m "feat(llm): Groq OpenAI-compatible client"
```

---

## Task 6: Crawler — httpx fetcher

**Files:**
- Create: `backend/app/crawler/__init__.py` (empty)
- Create: `backend/app/crawler/httpx_fetcher.py`
- Test: `backend/tests/unit/test_crawler_httpx.py`

- [ ] **Step 1: Write tests**

```python
import httpx
import pytest
import respx

from app.crawler.httpx_fetcher import HttpxFetcher, FetchResult


def test_httpx_success():
    f = HttpxFetcher(timeout=2.0)
    with respx.mock(base_url="https://x.test") as mock:
        mock.get("/job/1").mock(return_value=httpx.Response(200, html="<h1>Hello</h1><p>Body</p>"))
        result = f.fetch("https://x.test/job/1")
    assert isinstance(result, FetchResult)
    assert result.status_code == 200
    assert "Hello" in result.text
    assert result.html.startswith("<")


def test_httpx_non_200_raises_for_status():
    f = HttpxFetcher(timeout=2.0)
    with respx.mock(base_url="https://x.test") as mock:
        mock.get("/x").mock(return_value=httpx.Response(404, html=""))
        with pytest.raises(httpx.HTTPStatusError):
            f.fetch("https://x.test/x")
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement `backend/app/crawler/httpx_fetcher.py`**

```python
from dataclasses import dataclass

import httpx


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    text: str


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _html_to_text(html: str) -> str:
    import re
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    no_tags = re.sub(r"<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", no_tags).strip()


class HttpxFetcher:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch(self, url: str) -> FetchResult:
        with httpx.Client(
            timeout=self.timeout, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            r = client.get(url)
            r.raise_for_status()
        return FetchResult(url=url, status_code=r.status_code, html=r.text, text=_html_to_text(r.text))
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/crawler/ backend/tests/unit/test_crawler_httpx.py
git commit -m "feat(crawler): httpx fetcher with html→text"
```

---

## Task 7: Crawler — Playwright fetcher + hybrid `fetcher.py`

**Files:**
- Create: `backend/app/crawler/playwright_fetcher.py`
- Create: `backend/app/crawler/fetcher.py`
- Create: `backend/tests/fakes/fetcher.py`
- Test: `backend/tests/unit/test_crawler_hybrid.py`

- [ ] **Step 1: Implement `backend/app/crawler/playwright_fetcher.py`**

```python
from app.crawler.httpx_fetcher import FetchResult, _html_to_text


class PlaywrightFetcher:
    def __init__(self, timeout_ms: int = 20000):
        self.timeout_ms = timeout_ms

    def fetch(self, url: str) -> FetchResult:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                html = page.content()
            finally:
                browser.close()
        return FetchResult(url=url, status_code=200, html=html, text=_html_to_text(html))
```

- [ ] **Step 2: Implement hybrid `backend/app/crawler/fetcher.py`**

```python
from typing import Protocol

from app.crawler.httpx_fetcher import FetchResult, HttpxFetcher
from app.crawler.playwright_fetcher import PlaywrightFetcher


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


_JS_MARKERS = ("Please enable JavaScript", "noscript", "loading...")
_MIN_TEXT_LEN = 500


def _looks_js_only(text: str) -> bool:
    if len(text) < _MIN_TEXT_LEN:
        return True
    lower = text.lower()
    return any(m.lower() in lower for m in _JS_MARKERS)


class HybridFetcher:
    def __init__(self, primary: Fetcher | None = None, fallback: Fetcher | None = None):
        self.primary = primary or HttpxFetcher()
        self.fallback = fallback or PlaywrightFetcher()

    def fetch(self, url: str) -> FetchResult:
        try:
            r = self.primary.fetch(url)
            if not _looks_js_only(r.text):
                return r
        except Exception:
            pass
        return self.fallback.fetch(url)
```

- [ ] **Step 3: Create fake fetcher — `backend/tests/fakes/fetcher.py`**

```python
from app.crawler.httpx_fetcher import FetchResult


class FakeFetcher:
    def __init__(self, result: FetchResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result
```

- [ ] **Step 4: Write hybrid tests — `backend/tests/unit/test_crawler_hybrid.py`**

```python
from app.crawler.fetcher import HybridFetcher
from app.crawler.httpx_fetcher import FetchResult
from tests.fakes.fetcher import FakeFetcher


def _result(text: str = "x" * 1000) -> FetchResult:
    return FetchResult(url="u", status_code=200, html=f"<p>{text}</p>", text=text)


def test_uses_primary_when_ok():
    primary = FakeFetcher(result=_result())
    fallback = FakeFetcher(result=_result("fallback"))
    out = HybridFetcher(primary=primary, fallback=fallback).fetch("u")
    assert out.text.startswith("x")
    assert primary.calls == ["u"]
    assert fallback.calls == []


def test_falls_back_when_primary_short():
    primary = FakeFetcher(result=FetchResult(url="u", status_code=200, html="x", text="short"))
    fallback = FakeFetcher(result=_result("fallback ok " * 100))
    out = HybridFetcher(primary=primary, fallback=fallback).fetch("u")
    assert "fallback ok" in out.text


def test_falls_back_when_primary_raises():
    primary = FakeFetcher(error=RuntimeError("boom"))
    fallback = FakeFetcher(result=_result("fb " * 200))
    out = HybridFetcher(primary=primary, fallback=fallback).fetch("u")
    assert out.text.startswith("fb")
```

- [ ] **Step 5: Run — expect PASS.**

- [ ] **Step 6: Commit**

```bash
git add backend/app/crawler/ backend/tests/fakes/fetcher.py backend/tests/unit/test_crawler_hybrid.py
git commit -m "feat(crawler): playwright fetcher and hybrid"
```

---

## Task 8: Extractor — JobPosting schema + `extract()`

**Files:**
- Create: `backend/app/extractor/__init__.py`
- Create: `backend/app/extractor/schemas.py`
- Create: `backend/app/extractor/prompts.py`
- Test: `backend/tests/unit/test_extractor.py`

- [ ] **Step 1: Create schema — `backend/app/extractor/schemas.py`**

```python
from pydantic import BaseModel, Field


class ExtractedJobPosting(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact_person: str | None = None
    application_email: str | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    seniority: str | None = None
    work_mode: str | None = None  # remote | hybrid | onsite
    benefits: list[str] = Field(default_factory=list)
    language: str = Field(description="ISO 639-1 of the posting body, e.g. 'de' or 'en'")
```

- [ ] **Step 2: Create prompts — `backend/app/extractor/prompts.py`**

```python
SYSTEM = (
    "You extract structured data from job postings. "
    "Return ONLY JSON matching the schema. "
    "If a field is not present, leave it null or empty list. "
    "Detect the posting language as ISO 639-1."
)


def user_prompt(raw_text: str) -> str:
    return f"Job posting raw text follows.\n\n---\n{raw_text}\n---"
```

- [ ] **Step 3: Implement `backend/app/extractor/__init__.py`**

```python
import json

from app.extractor.prompts import SYSTEM, user_prompt
from app.extractor.schemas import ExtractedJobPosting
from app.llm.base import LLMClient


def extract(raw_text: str, llm: LLMClient) -> ExtractedJobPosting:
    schema = ExtractedJobPosting.model_json_schema()
    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(raw_text)},
        ],
        json_schema=schema,
        temperature=0.0,
    )
    return ExtractedJobPosting.model_validate_json(raw)
```

- [ ] **Step 4: Write tests — `backend/tests/unit/test_extractor.py`**

```python
import json

from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from tests.fakes.llm import FakeLLM


def test_extract_parses_json():
    payload = {
        "title": "Senior Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "Build stuff",
        "requirements": "Python",
        "tech_stack": ["python", "fastapi"],
        "language": "en",
    }
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = extract("blob", llm)
    assert isinstance(result, ExtractedJobPosting)
    assert result.title == "Senior Engineer"
    assert result.tech_stack == ["python", "fastapi"]
    assert result.language == "en"


def test_extract_passes_schema_to_llm():
    captured = {}

    def handler(messages, schema):
        captured["schema"] = schema
        return '{"language":"de"}'

    extract("blob", FakeLLM(handler=handler))
    assert captured["schema"]["properties"]["title"]["anyOf"][0]["type"] == "string"
```

- [ ] **Step 5: Run — expect PASS.**

- [ ] **Step 6: Commit**

```bash
git add backend/app/extractor/ backend/tests/unit/test_extractor.py
git commit -m "feat(extractor): structured-output JobPosting extractor"
```

---

## Task 9: Generator — Anschreiben markdown

**Files:**
- Create: `backend/app/generator/__init__.py`
- Create: `backend/app/generator/prompts.py`
- Test: `backend/tests/unit/test_generator.py`

- [ ] **Step 1: Create prompts — `backend/app/generator/prompts.py`**

```python
from app.extractor.schemas import ExtractedJobPosting


SYSTEM = (
    "You are a senior career coach. Write a tailored Anschreiben (cover letter) "
    "in Markdown. Use the candidate's CV and the default Anschreiben template as base. "
    "Match the candidate's strengths to the role's requirements. "
    "Write in the language given. Output only the Markdown of the letter, "
    "no commentary, no code fences."
)


def user_prompt(
    job: ExtractedJobPosting,
    cv_md: str,
    anschreiben_md: str,
    language: str,
) -> str:
    return (
        f"Target language: {language}\n\n"
        f"=== JOB POSTING ===\n"
        f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
        f"Description:\n{job.description}\nRequirements:\n{job.requirements}\n"
        f"Tech stack: {', '.join(job.tech_stack)}\n"
        f"Contact person: {job.contact_person}\n\n"
        f"=== CANDIDATE CV (Markdown) ===\n{cv_md}\n\n"
        f"=== DEFAULT ANSCHREIBEN TEMPLATE (Markdown) ===\n{anschreiben_md}\n\n"
        f"Now produce the tailored Anschreiben in Markdown, in {language}."
    )
```

- [ ] **Step 2: Implement `backend/app/generator/__init__.py`**

```python
from app.extractor.schemas import ExtractedJobPosting
from app.generator.prompts import SYSTEM, user_prompt
from app.llm.base import LLMClient


def generate(
    job: ExtractedJobPosting,
    cv_md: str,
    anschreiben_md: str,
    language: str,
    llm: LLMClient,
) -> str:
    return llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(job, cv_md, anschreiben_md, language)},
        ],
        temperature=0.3,
    ).strip()
```

- [ ] **Step 3: Write tests — `backend/tests/unit/test_generator.py`**

```python
from app.extractor.schemas import ExtractedJobPosting
from app.generator import generate
from tests.fakes.llm import FakeLLM


def test_generate_returns_text():
    job = ExtractedJobPosting(title="Eng", company="Acme", language="de")
    llm = FakeLLM(handler=lambda m, s: "# Anschreiben\n\nSehr geehrte...")
    out = generate(job, "cv md", "template md", "de", llm)
    assert out.startswith("# Anschreiben")


def test_generate_passes_language_in_prompt():
    job = ExtractedJobPosting(title="Eng", company="Acme", language="en")
    captured = {}

    def handler(messages, schema):
        captured["user"] = messages[1]["content"]
        return "letter"

    generate(job, "cv", "tpl", "en", FakeLLM(handler=handler))
    assert "Target language: en" in captured["user"]
    assert "=== CANDIDATE CV" in captured["user"]
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/generator/ backend/tests/unit/test_generator.py
git commit -m "feat(generator): markdown Anschreiben generation"
```

---

## Task 10: Renderer — markdown to DOCX

**Files:**
- Create: `backend/app/renderer/__init__.py`
- Create: `backend/app/renderer/docx.py`
- Test: `backend/tests/unit/test_renderer.py`

- [ ] **Step 1: Implement `backend/app/renderer/docx.py`**

```python
from pathlib import Path

import markdown as md_lib
from docx import Document
from docx.shared import Pt


def to_docx(markdown_text: str, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            doc.add_paragraph("")
            continue
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("- "):
            doc.add_paragraph(line[2:], style="List Bullet")
        else:
            doc.add_paragraph(line)
    doc.save(str(out))
    return out


def to_html(markdown_text: str) -> str:
    return md_lib.markdown(markdown_text)
```

- [ ] **Step 2: Make `backend/app/renderer/__init__.py` re-export**

```python
from app.renderer.docx import to_docx, to_html

__all__ = ["to_docx", "to_html"]
```

- [ ] **Step 3: Write tests — `backend/tests/unit/test_renderer.py`**

```python
from pathlib import Path

from docx import Document

from app.renderer import to_docx, to_html


def test_to_docx_writes_file(tmp_path: Path):
    out = tmp_path / "out.docx"
    p = to_docx("# Title\n\nHello world\n\n- one\n- two", out)
    assert p.exists()
    doc = Document(str(p))
    texts = [par.text for par in doc.paragraphs]
    assert "Title" in texts
    assert "Hello world" in texts
    assert "one" in texts


def test_to_html():
    h = to_html("# Hi")
    assert "<h1>" in h
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/renderer/ backend/tests/unit/test_renderer.py
git commit -m "feat(renderer): markdown to DOCX"
```

---

## Task 11: MS OAuth + session middleware

**Files:**
- Create: `backend/app/auth/__init__.py` (empty)
- Create: `backend/app/auth/ms_oauth.py`
- Create: `backend/app/auth/session.py`
- Create: `backend/app/api/__init__.py` (empty)
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/auth.py`
- Test: `backend/tests/integration/test_auth.py`

- [ ] **Step 1: Implement `backend/app/auth/ms_oauth.py`**

```python
from dataclasses import dataclass

import msal


@dataclass
class MSConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...] = ("User.Read", "offline_access")


def authorize_url(cfg: MSConfig, state: str) -> str:
    app = msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential=cfg.client_secret,
    )
    return app.get_authorization_request_url(
        list(cfg.scopes), state=state, redirect_uri=cfg.redirect_uri
    )


def acquire_token_by_code(cfg: MSConfig, code: str) -> dict:
    app = msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential=cfg.client_secret,
    )
    return app.acquire_token_by_authorization_code(
        code, scopes=list(cfg.scopes), redirect_uri=cfg.redirect_uri
    )
```

- [ ] **Step 2: Implement `backend/app/auth/session.py`**

```python
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DBSession

from app.db.models import Session as SessionRow

SESSION_TTL_DAYS = 30


def create_session(db: DBSession, user_id) -> str:
    sid = secrets.token_urlsafe(32)
    row = SessionRow(
        id=sid,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(row)
    db.commit()
    return sid


def lookup_session(db: DBSession, sid: str) -> SessionRow | None:
    row = db.get(SessionRow, sid)
    if row is None:
        return None
    if row.expires_at < datetime.now(timezone.utc):
        return None
    return row


def delete_session(db: DBSession, sid: str) -> None:
    row = db.get(SessionRow, sid)
    if row is not None:
        db.delete(row)
        db.commit()
```

- [ ] **Step 3: Implement `backend/app/api/deps.py`**

```python
from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.session import lookup_session
from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db


def settings_dep() -> Settings:
    return get_settings()


def db_dep() -> Iterator[Session]:
    yield from get_db()


def current_user(
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    session_cookie: str | None = Cookie(default=None, alias="applicator_session"),
) -> User:
    if not session_cookie:
        raise HTTPException(401, "not authenticated")
    row = lookup_session(db, session_cookie)
    if row is None:
        raise HTTPException(401, "session invalid or expired")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, "user gone")
    return user
```

- [ ] **Step 4: Implement `backend/app/api/auth.py`**

```python
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep, settings_dep
from app.auth.ms_oauth import MSConfig, acquire_token_by_code, authorize_url
from app.auth.session import create_session, delete_session
from app.config import Settings
from app.crypto import encrypt
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_oauth_states: dict[str, bool] = {}  # in-memory; OK for single-user MVP


def _ms_config(s: Settings) -> MSConfig:
    return MSConfig(
        tenant_id=s.ms_tenant_id,
        client_id=s.ms_client_id,
        client_secret=s.ms_client_secret,
        redirect_uri=s.ms_redirect_uri,
    )


@router.get("/login")
def login(settings: Annotated[Settings, Depends(settings_dep)]) -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = True
    url = authorize_url(_ms_config(settings), state)
    return RedirectResponse(url=url)


@router.get("/callback")
def callback(
    code: str,
    state: str,
    response: Response,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    if not _oauth_states.pop(state, False):
        raise HTTPException(400, "invalid state")
    token = acquire_token_by_code(_ms_config(settings), code)
    if "id_token_claims" not in token:
        raise HTTPException(400, f"oauth failed: {token.get('error_description')}")
    claims = token["id_token_claims"]
    oid = claims["oid"]
    email = claims.get("preferred_username") or claims.get("email") or ""
    name = claims.get("name") or email
    user = db.query(User).filter_by(ms_oid=oid).first()
    refresh = token.get("refresh_token")
    refresh_enc = encrypt(refresh, settings.app_secret_key) if refresh else None
    if user is None:
        user = User(
            ms_oid=oid, email=email, display_name=name, ms_refresh_token_encrypted=refresh_enc
        )
        db.add(user); db.commit(); db.refresh(user)
    else:
        user.email = email; user.display_name = name
        if refresh_enc:
            user.ms_refresh_token_encrypted = refresh_enc
        db.commit()
    sid = create_session(db, user.id)
    redirect = RedirectResponse(url=settings.frontend_origin + "/applications")
    redirect.set_cookie(
        settings.session_cookie_name, sid,
        httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/",
    )
    return redirect


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> dict:
    sid = request.cookies.get(settings.session_cookie_name)
    if sid:
        delete_session(db, sid)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> dict:
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}
```

- [ ] **Step 5: Wire router in `backend/app/main.py`**

Replace existing `main.py` body with:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Applicator", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_api.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 6: Write integration tests — `backend/tests/integration/test_auth.py`**

```python
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth.session import create_session
from app.db.models import Session as SessionRow, User
from app.db.session import Base, get_session_factory


@pytest.fixture
def app_client(db_session, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "k" * 44)
    monkeypatch.setenv("MS_TENANT_ID", "t"); monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s")
    monkeypatch.setenv("MS_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    monkeypatch.setenv("LLM_API_KEY", "k")
    # rebind session factory to test engine
    import app.db.session as ds
    ds._engine = db_session.get_bind()
    ds._SessionLocal = get_session_factory.__wrapped__() if hasattr(get_session_factory, "__wrapped__") else None
    from app.main import create_app
    return TestClient(create_app())


def test_me_unauthenticated(app_client):
    r = app_client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_authenticated(db_session, app_client):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    r = app_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.c"


def test_logout_deletes_session(db_session, app_client):
    u = User(ms_oid="o2", email="x@y.z", display_name="X")
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    r = app_client.post("/api/auth/logout")
    assert r.status_code == 200
    assert db_session.get(SessionRow, sid) is None
```

The fixture above rebinds the session-factory globals to the test engine. If that fixture path proves brittle in your environment, switch to dependency overrides via `app.dependency_overrides[db_dep]`.

- [ ] **Step 7: Run — expect PASS for `me_unauthenticated`, `me_authenticated`, `logout_deletes_session`.**

```bash
pytest backend/tests/integration/test_auth.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth/ backend/app/api/auth.py backend/app/api/deps.py backend/app/api/__init__.py backend/app/main.py backend/tests/integration/test_auth.py
git commit -m "feat(auth): MS OAuth2 + session cookie"
```

---

## Task 12: Documents API — CV + Anschreiben variants

**Files:**
- Create: `backend/app/api/documents.py`
- Test: `backend/tests/integration/test_documents.py`

- [ ] **Step 1: Implement `backend/app/api/documents.py`**

```python
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import AnschreibenVariant, CVVariant, User

router = APIRouter(prefix="/api", tags=["documents"])


class VariantCreate(BaseModel):
    name: str
    source_md: str
    is_default: bool = False


class VariantUpdate(BaseModel):
    name: str | None = None
    source_md: str | None = None
    is_default: bool | None = None


class VariantOut(BaseModel):
    id: uuid.UUID
    name: str
    source_md: str
    is_default: bool

    class Config:
        from_attributes = True


def _model_for(kind: Literal["cv", "anschreiben"]):
    return CVVariant if kind == "cv" else AnschreibenVariant


def _list(db, user, kind):
    M = _model_for(kind)
    return db.query(M).filter_by(user_id=user.id).order_by(M.created_at.asc()).all()


def _set_default_exclusive(db, user, kind, target_id):
    M = _model_for(kind)
    db.query(M).filter_by(user_id=user.id).update({"is_default": False})
    db.query(M).filter_by(id=target_id).update({"is_default": True})


@router.get("/cv-variants", response_model=list[VariantOut])
def list_cv(
    db: Annotated[Session, Depends(db_dep)], user: Annotated[User, Depends(current_user)]
):
    return _list(db, user, "cv")


@router.post("/cv-variants", response_model=VariantOut)
def create_cv(
    body: VariantCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = CVVariant(user_id=user.id, name=body.name, source_md=body.source_md, is_default=False)
    db.add(v); db.flush()
    if body.is_default:
        _set_default_exclusive(db, user, "cv", v.id)
    db.commit(); db.refresh(v)
    return v


@router.patch("/cv-variants/{vid}", response_model=VariantOut)
def update_cv(
    vid: uuid.UUID,
    body: VariantUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(CVVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    if body.name is not None: v.name = body.name
    if body.source_md is not None: v.source_md = body.source_md
    if body.is_default:
        _set_default_exclusive(db, user, "cv", v.id)
    db.commit(); db.refresh(v)
    return v


@router.delete("/cv-variants/{vid}")
def delete_cv(
    vid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(CVVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    db.delete(v); db.commit()
    return {"ok": True}


# Mirror endpoints for anschreiben-variants:
@router.get("/anschreiben-variants", response_model=list[VariantOut])
def list_an(
    db: Annotated[Session, Depends(db_dep)], user: Annotated[User, Depends(current_user)]
):
    return _list(db, user, "anschreiben")


@router.post("/anschreiben-variants", response_model=VariantOut)
def create_an(
    body: VariantCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = AnschreibenVariant(
        user_id=user.id, name=body.name, source_md=body.source_md, is_default=False
    )
    db.add(v); db.flush()
    if body.is_default:
        _set_default_exclusive(db, user, "anschreiben", v.id)
    db.commit(); db.refresh(v)
    return v


@router.patch("/anschreiben-variants/{vid}", response_model=VariantOut)
def update_an(
    vid: uuid.UUID,
    body: VariantUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(AnschreibenVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    if body.name is not None: v.name = body.name
    if body.source_md is not None: v.source_md = body.source_md
    if body.is_default:
        _set_default_exclusive(db, user, "anschreiben", v.id)
    db.commit(); db.refresh(v)
    return v


@router.delete("/anschreiben-variants/{vid}")
def delete_an(
    vid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(AnschreibenVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    db.delete(v); db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Wire router in `main.py`** — add `app.include_router(documents_api.router)` and the import.

- [ ] **Step 3: Write integration tests — `backend/tests/integration/test_documents.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.auth.session import create_session
from app.db.models import User


@pytest.fixture
def auth_client(app_client, db_session):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    return app_client, u


def test_create_and_list_cv(auth_client):
    c, _ = auth_client
    r = c.post("/api/cv-variants", json={"name": "default", "source_md": "x", "is_default": True})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "default" and body["is_default"] is True
    r2 = c.get("/api/cv-variants")
    assert len(r2.json()) == 1


def test_set_default_exclusive(auth_client):
    c, _ = auth_client
    a = c.post("/api/cv-variants", json={"name": "a", "source_md": "x", "is_default": True}).json()
    b = c.post("/api/cv-variants", json={"name": "b", "source_md": "y", "is_default": True}).json()
    items = c.get("/api/cv-variants").json()
    flags = {it["id"]: it["is_default"] for it in items}
    assert flags[a["id"]] is False
    assert flags[b["id"]] is True


def test_anschreiben_endpoints(auth_client):
    c, _ = auth_client
    r = c.post("/api/anschreiben-variants", json={"name": "t", "source_md": "tpl"})
    assert r.status_code == 200
    assert c.get("/api/anschreiben-variants").json()[0]["name"] == "t"
```

Re-use `app_client` fixture from `test_auth.py` by promoting it to `backend/tests/integration/conftest.py` if not already there.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/documents.py backend/app/main.py backend/tests/integration/test_documents.py
git commit -m "feat(api): cv + anschreiben variants CRUD"
```

---

## Task 13: Pipeline orchestration

**Files:**
- Create: `backend/app/pipeline.py`
- Test: `backend/tests/integration/test_pipeline.py`

- [ ] **Step 1: Implement `backend/app/pipeline.py`**

```python
import hashlib
import uuid
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.config import Settings
from app.crawler.fetcher import HybridFetcher
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobPosting, JobState
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.generator import generate
from app.llm.base import LLMClient
from app.renderer import to_docx


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


class Pipeline:
    def __init__(
        self,
        db_factory: Callable[[], Session],
        llm: LLMClient,
        settings: Settings,
        fetcher=None,
    ):
        self.db_factory = db_factory
        self.llm = llm
        self.settings = settings
        self.fetcher = fetcher or HybridFetcher()

    def run(self, application_id: uuid.UUID) -> None:
        with self.db_factory() as db:
            app = db.get(Application, application_id)
            if app is None:
                return
            try:
                self._run_steps(db, app)
            except Exception as e:  # noqa: BLE001
                app.job_state = JobState.failed
                app.job_error = str(e)[:1000]
                db.commit()

    def _run_steps(self, db: Session, app: Application) -> None:
        app.job_state = JobState.crawling; db.commit()
        result = self.fetcher.fetch(app.url)
        raw_path = self._save_raw(app, result)

        app.job_state = JobState.extracting; db.commit()
        job: ExtractedJobPosting = extract(result.text, self.llm)
        jp = JobPosting(
            application_id=app.id,
            raw_text=result.text[:200000],
            raw_html_path=str(raw_path),
            title=job.title, company=job.company, location=job.location,
            description=job.description, requirements=job.requirements,
            contact_person=job.contact_person, application_email=job.application_email,
            deadline=job.deadline, salary=job.salary,
            tech_stack=job.tech_stack, seniority=job.seniority,
            work_mode=job.work_mode, benefits=job.benefits, language=job.language,
        )
        db.add(jp); db.commit()
        app.language = job.language

        app.job_state = JobState.generating; db.commit()
        from app.db.models import AnschreibenVariant, CVVariant
        cv = db.get(CVVariant, app.cv_variant_id)
        an = db.get(AnschreibenVariant, app.anschreiben_variant_id)
        md = generate(job, cv.source_md, an.source_md, job.language, self.llm)
        app.generated_md = md

        docx_path = Path(self.settings.data_dir) / str(app.user_id) / str(app.id) / "anschreiben.docx"
        to_docx(md, docx_path)
        app.generated_docx_path = str(docx_path)

        app.job_state = JobState.ready
        app.job_error = None
        db.commit()

    def _save_raw(self, app: Application, result: FetchResult) -> Path:
        raw_path = Path(self.settings.data_dir) / str(app.user_id) / str(app.id) / "raw.html"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(result.html, encoding="utf-8")
        return raw_path
```

- [ ] **Step 2: Write tests — `backend/tests/integration/test_pipeline.py`**

```python
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import (
    AnschreibenVariant, Application, ApplicationStatus, CVVariant, JobState, User,
)
from app.pipeline import Pipeline, url_hash
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "k")
    monkeypatch.setenv("MS_TENANT_ID", "t"); monkeypatch.setenv("MS_CLIENT_ID", "c")
    monkeypatch.setenv("MS_CLIENT_SECRET", "s"); monkeypatch.setenv("MS_REDIRECT_URI", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return Settings()


def _seed(db_session):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u); db_session.flush()
    cv = CVVariant(user_id=u.id, name="c", source_md="cv md", is_default=True)
    an = AnschreibenVariant(user_id=u.id, name="a", source_md="tpl md", is_default=True)
    db_session.add_all([cv, an]); db_session.flush()
    app = Application(
        user_id=u.id, url="https://x.test/job", url_hash=url_hash("https://x.test/job"),
        cv_variant_id=cv.id, anschreiben_variant_id=an.id,
    )
    db_session.add(app); db_session.commit(); db_session.refresh(app)
    return app


@contextmanager
def _db_factory(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def test_pipeline_happy_path(db_session, settings, tmp_path):
    app = _seed(db_session)
    fetcher = FakeFetcher(result=FetchResult(
        url=app.url, status_code=200, html="<html>x</html>", text="x" * 1000,
    ))
    job_payload = {
        "title": "Dev", "company": "Acme", "language": "en",
        "description": "Build", "requirements": "Py", "tech_stack": ["python"],
    }
    calls = {"n": 0}

    def llm_handler(messages, schema):
        calls["n"] += 1
        # first call: extraction (schema present)
        if schema is not None:
            return json.dumps(job_payload)
        # second call: generation
        return "# Anschreiben\n\nDear hiring team..."

    engine = db_session.get_bind()

    def factory():
        from contextlib import nullcontext
        return _db_factory(engine)

    p = Pipeline(db_factory=factory, llm=FakeLLM(handler=llm_handler), settings=settings, fetcher=fetcher)
    p.run(app.id)

    db_session.refresh(app)
    assert app.job_state == JobState.ready
    assert app.generated_md.startswith("# Anschreiben")
    assert Path(app.generated_docx_path).exists()
    assert app.language == "en"


def test_pipeline_records_failure(db_session, settings):
    app = _seed(db_session)
    fetcher = FakeFetcher(error=RuntimeError("network down"))
    engine = db_session.get_bind()
    p = Pipeline(
        db_factory=lambda: _db_factory(engine),
        llm=FakeLLM(handler=lambda m, s: "{}"),
        settings=settings,
        fetcher=fetcher,
    )
    p.run(app.id)
    db_session.refresh(app)
    assert app.job_state == JobState.failed
    assert "network down" in app.job_error
```

- [ ] **Step 3: Run — expect PASS.**

- [ ] **Step 4: Commit**

```bash
git add backend/app/pipeline.py backend/tests/integration/test_pipeline.py
git commit -m "feat(pipeline): crawl→extract→generate→render orchestration"
```

---

## Task 14: Applications API (create + list + get + retry + download)

**Files:**
- Create: `backend/app/api/applications.py`
- Test: `backend/tests/integration/test_applications.py`

- [ ] **Step 1: Implement `backend/app/api/applications.py`**

```python
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import current_user, db_dep, settings_dep
from app.config import Settings
from app.db.models import (
    AnschreibenVariant, Application, ApplicationStatus, CVVariant,
    JobPosting, JobState, User,
)
from app.db.session import get_engine
from app.llm.groq import GroqClient
from app.pipeline import Pipeline, url_hash

router = APIRouter(prefix="/api/applications", tags=["applications"])


class CreateApplication(BaseModel):
    url: HttpUrl
    cv_variant_id: uuid.UUID | None = None
    anschreiben_variant_id: uuid.UUID | None = None


class JobPostingOut(BaseModel):
    title: str | None
    company: str | None
    location: str | None
    description: str | None
    requirements: str | None
    contact_person: str | None
    application_email: str | None
    deadline: str | None
    salary: str | None
    tech_stack: list[str] | None
    seniority: str | None
    work_mode: str | None
    benefits: list[str] | None
    language: str | None

    class Config:
        from_attributes = True


class ApplicationOut(BaseModel):
    id: uuid.UUID
    url: str
    status: ApplicationStatus
    job_state: JobState
    job_error: str | None
    language: str | None
    generated_md: str | None
    has_docx: bool
    job_posting: JobPostingOut | None

    @classmethod
    def from_orm_row(cls, app: Application) -> "ApplicationOut":
        return cls(
            id=app.id, url=app.url, status=app.status, job_state=app.job_state,
            job_error=app.job_error, language=app.language,
            generated_md=app.generated_md,
            has_docx=app.generated_docx_path is not None,
            job_posting=JobPostingOut.from_orm(app.job_posting) if app.job_posting else None,
        )


def _llm(settings: Settings) -> GroqClient:
    return GroqClient(
        api_key=settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url
    )


def _kickoff(
    background_tasks: BackgroundTasks, application_id: uuid.UUID, settings: Settings
) -> None:
    factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)

    from contextlib import contextmanager

    @contextmanager
    def db_factory():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    pipeline = Pipeline(db_factory=db_factory, llm=_llm(settings), settings=settings)
    background_tasks.add_task(pipeline.run, application_id)


@router.post("", response_model=ApplicationOut, status_code=202)
def create(
    body: CreateApplication,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    cv_id = body.cv_variant_id or _default_id(db, user, CVVariant)
    an_id = body.anschreiben_variant_id or _default_id(db, user, AnschreibenVariant)
    if not cv_id or not an_id:
        raise HTTPException(400, "no default CV or Anschreiben configured")
    h = url_hash(str(body.url))
    existing = db.query(Application).filter_by(user_id=user.id, url_hash=h).first()
    if existing:
        raise HTTPException(409, f"application already exists: {existing.id}")
    app = Application(
        user_id=user.id, url=str(body.url), url_hash=h,
        cv_variant_id=cv_id, anschreiben_variant_id=an_id,
    )
    db.add(app); db.commit(); db.refresh(app)
    _kickoff(background_tasks, app.id, settings)
    return ApplicationOut.from_orm_row(app)


def _default_id(db: Session, user: User, model) -> uuid.UUID | None:
    row = db.query(model).filter_by(user_id=user.id, is_default=True).first()
    return row.id if row else None


@router.get("", response_model=list[ApplicationOut])
def list_apps(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    rows = (
        db.query(Application)
        .filter_by(user_id=user.id)
        .order_by(Application.created_at.desc())
        .all()
    )
    return [ApplicationOut.from_orm_row(r) for r in rows]


@router.get("/{aid}", response_model=ApplicationOut)
def get_app(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    return ApplicationOut.from_orm_row(app)


class StatusUpdate(BaseModel):
    status: ApplicationStatus


@router.patch("/{aid}", response_model=ApplicationOut)
def update_status(
    aid: uuid.UUID,
    body: StatusUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    app.status = body.status
    db.commit(); db.refresh(app)
    return ApplicationOut.from_orm_row(app)


@router.post("/{aid}/retry", response_model=ApplicationOut)
def retry(
    aid: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    # clear job_posting and reset state
    if app.job_posting:
        db.delete(app.job_posting)
    app.generated_md = None; app.generated_docx_path = None
    app.job_error = None; app.job_state = JobState.pending
    db.commit(); db.refresh(app)
    _kickoff(background_tasks, app.id, settings)
    return ApplicationOut.from_orm_row(app)


@router.get("/{aid}/docx")
def download_docx(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    if not app.generated_docx_path or not Path(app.generated_docx_path).exists():
        raise HTTPException(404, "docx not ready")
    fname = "anschreiben.docx"
    return FileResponse(
        app.generated_docx_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=fname,
    )
```

- [ ] **Step 2: Wire router in `main.py`** — `app.include_router(applications_api.router)`.

- [ ] **Step 3: Tests — `backend/tests/integration/test_applications.py`**

```python
import json

import pytest

from app.api import applications as applications_api
from app.config import Settings
from app.db.models import AnschreibenVariant, CVVariant, User
from app.auth.session import create_session
from app.crawler.httpx_fetcher import FetchResult
from app.pipeline import Pipeline
from tests.fakes.fetcher import FakeFetcher
from tests.fakes.llm import FakeLLM


@pytest.fixture
def auth_user(db_session, app_client):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u); db_session.flush()
    db_session.add_all([
        CVVariant(user_id=u.id, name="cv", source_md="cv", is_default=True),
        AnschreibenVariant(user_id=u.id, name="an", source_md="an", is_default=True),
    ])
    db_session.commit(); db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    return app_client, u


def _patch_pipeline(monkeypatch, db_session, settings, llm_handler, fetcher_result=None):
    """Replace _kickoff so BackgroundTasks runs synchronously with fakes."""
    from contextlib import contextmanager
    engine = db_session.get_bind()
    fetcher = FakeFetcher(result=fetcher_result)

    def fake_kickoff(bg, app_id, s):
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        @contextmanager
        def factory():
            ses = Session()
            try:
                yield ses
            finally:
                ses.close()

        Pipeline(db_factory=factory, llm=FakeLLM(handler=llm_handler),
                 settings=settings, fetcher=fetcher).run(app_id)

    monkeypatch.setattr(applications_api, "_kickoff", fake_kickoff)


def test_create_runs_pipeline_and_lists(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="https://x.test/j", status_code=200, html="<p>x</p>", text="x" * 1000)
    job = {"title": "Dev", "company": "Acme", "language": "en", "description": "d", "requirements": "r"}

    def llm_handler(messages, schema):
        return json.dumps(job) if schema is not None else "# Letter"

    _patch_pipeline(monkeypatch, db_session, settings, llm_handler, fetcher_result=fr)

    c, _ = auth_user
    r = c.post("/api/applications", json={"url": "https://x.test/j"})
    assert r.status_code == 202
    aid = r.json()["id"]
    g = c.get(f"/api/applications/{aid}").json()
    assert g["job_state"] == "ready"
    assert g["job_posting"]["title"] == "Dev"
    assert g["has_docx"] is True


def test_duplicate_url_returns_409(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: '{"language":"en"}' if s else "letter",
        fetcher_result=fr,
    )
    c, _ = auth_user
    c.post("/api/applications", json={"url": "https://x.test/j"})
    r = c.post("/api/applications", json={"url": "https://x.test/j"})
    assert r.status_code == 409


def test_status_patch(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: '{"language":"en"}' if s else "letter",
        fetcher_result=fr,
    )
    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/j"}).json()["id"]
    r = c.patch(f"/api/applications/{aid}", json={"status": "applied"})
    assert r.status_code == 200
    assert r.json()["status"] == "applied"


def test_docx_download(monkeypatch, auth_user, db_session, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    fr = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)
    _patch_pipeline(
        monkeypatch, db_session, settings,
        lambda m, s: '{"language":"en","title":"Dev"}' if s else "# Hi",
        fetcher_result=fr,
    )
    c, _ = auth_user
    aid = c.post("/api/applications", json={"url": "https://x.test/j"}).json()["id"]
    r = c.get(f"/api/applications/{aid}/docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml"
    )
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/applications.py backend/app/main.py backend/tests/integration/test_applications.py
git commit -m "feat(api): applications CRUD + pipeline kickoff + docx download"
```

---

## Task 15: Chat refinement API

**Files:**
- Create: `backend/app/api/chat.py`
- Test: `backend/tests/integration/test_chat.py`

- [ ] **Step 1: Implement `backend/app/api/chat.py`**

```python
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep, settings_dep
from app.config import Settings
from app.db.models import Application, ChatMessage, ChatRole, User
from app.llm.base import LLMClient
from app.llm.groq import GroqClient
from app.renderer import to_docx

router = APIRouter(prefix="/api/applications", tags=["chat"])

SYSTEM_REFINE = (
    "You are a writing assistant. The user already has a generated Anschreiben in Markdown. "
    "When the user asks for changes, return TWO things in JSON: "
    '{"assistant_message": str, "updated_md": str}. '
    "updated_md must be the full new Anschreiben in Markdown."
)

REFINE_SCHEMA = {
    "type": "object",
    "properties": {
        "assistant_message": {"type": "string"},
        "updated_md": {"type": "string"},
    },
    "required": ["assistant_message", "updated_md"],
}


class ChatIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: ChatRole
    content: str

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    assistant_message: str
    generated_md: str


def _llm(settings: Settings) -> LLMClient:
    return GroqClient(settings.llm_api_key, settings.llm_model, settings.llm_base_url)


@router.get("/{aid}/chat", response_model=list[ChatMessageOut])
def history(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    return (
        db.query(ChatMessage)
        .filter_by(application_id=aid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


@router.post("/{aid}/chat", response_model=ChatResponse)
def refine(
    aid: uuid.UUID,
    body: ChatIn,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
    llm: LLMClient | None = None,
):
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    if not app.generated_md:
        raise HTTPException(400, "no Anschreiben yet")
    client = llm or _llm(settings)
    history_rows = (
        db.query(ChatMessage)
        .filter_by(application_id=aid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_REFINE}]
    messages.append({"role": "system", "content": f"CURRENT_MD:\n{app.generated_md}"})
    for h in history_rows:
        messages.append({"role": h.role.value, "content": h.content})
    messages.append({"role": "user", "content": body.message})

    raw = client.complete(messages, json_schema=REFINE_SCHEMA, temperature=0.4)
    import json as _json
    parsed = _json.loads(raw)
    assistant_msg = parsed["assistant_message"]
    new_md = parsed["updated_md"]

    db.add(ChatMessage(application_id=aid, role=ChatRole.user, content=body.message))
    db.add(ChatMessage(application_id=aid, role=ChatRole.assistant, content=assistant_msg))
    app.generated_md = new_md
    if app.generated_docx_path:
        to_docx(new_md, app.generated_docx_path)
    db.commit()
    return ChatResponse(assistant_message=assistant_msg, generated_md=new_md)
```

For testability, the `refine` route accepts an `llm` dependency that integration tests override via `app.dependency_overrides`. Add to imports if needed.

- [ ] **Step 2: Wire router in `main.py`.**

- [ ] **Step 3: Tests — `backend/tests/integration/test_chat.py`**

```python
import json

import pytest

from app.api import chat as chat_api
from app.db.models import Application, ApplicationStatus, ChatMessage
from tests.fakes.llm import FakeLLM


@pytest.fixture
def auth_app(auth_user, db_session):
    c, u = auth_user
    from app.db.models import (
        AnschreibenVariant, Application, CVVariant, ApplicationStatus, JobState,
    )
    cv = db_session.query(CVVariant).filter_by(user_id=u.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=u.id).first()
    app = Application(
        user_id=u.id, url="https://x.test/j", url_hash="h",
        cv_variant_id=cv.id, anschreiben_variant_id=an.id,
        generated_md="# Letter\n\nHello", language="en",
        status=ApplicationStatus.draft, job_state=JobState.ready,
    )
    db_session.add(app); db_session.commit(); db_session.refresh(app)
    return c, u, app


def test_chat_refines_and_persists(auth_app, db_session, app_client):
    c, _, app = auth_app
    payload = {"assistant_message": "Tweaked.", "updated_md": "# Letter v2\n\nHello!"}
    fake = FakeLLM(handler=lambda m, s: json.dumps(payload))
    app_client.app.dependency_overrides[chat_api.refine.__wrapped__ if hasattr(chat_api.refine, '__wrapped__') else None] = lambda: fake  # noqa
    # simpler: monkeypatch _llm
    import app.api.chat as chat_module
    chat_module._llm = lambda s: fake
    r = c.post(f"/api/applications/{app.id}/chat", json={"message": "Make it shorter"})
    assert r.status_code == 200
    body = r.json()
    assert body["generated_md"].startswith("# Letter v2")
    msgs = c.get(f"/api/applications/{app.id}/chat").json()
    assert len(msgs) == 2
    assert any("shorter" in m["content"] for m in msgs)


def test_chat_requires_existing_anschreiben(auth_user, db_session):
    c, u = auth_user
    from app.db.models import (
        AnschreibenVariant, Application, CVVariant, ApplicationStatus, JobState,
    )
    cv = db_session.query(CVVariant).filter_by(user_id=u.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=u.id).first()
    app = Application(
        user_id=u.id, url="https://y/j", url_hash="h2",
        cv_variant_id=cv.id, anschreiben_variant_id=an.id,
        status=ApplicationStatus.draft, job_state=JobState.pending,
    )
    db_session.add(app); db_session.commit(); db_session.refresh(app)
    r = c.post(f"/api/applications/{app.id}/chat", json={"message": "x"})
    assert r.status_code == 400
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/app/main.py backend/tests/integration/test_chat.py
git commit -m "feat(api): chat refinement updates Anschreiben + DOCX"
```

---

## Task 16: Interviews API

**Files:**
- Create: `backend/app/api/interviews.py`
- Test: `backend/tests/integration/test_interviews.py`

- [ ] **Step 1: Implement `backend/app/api/interviews.py`**

```python
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Application, Interview, InterviewKind, InterviewOutcome, User

router = APIRouter(prefix="/api", tags=["interviews"])


class InterviewCreate(BaseModel):
    scheduled_at: datetime
    kind: InterviewKind
    notes: str | None = None


class InterviewUpdate(BaseModel):
    scheduled_at: datetime | None = None
    kind: InterviewKind | None = None
    notes: str | None = None
    outcome: InterviewOutcome | None = None


class InterviewOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    kind: InterviewKind
    notes: str | None
    outcome: InterviewOutcome

    class Config:
        from_attributes = True


def _own_app(db: Session, user: User, aid: uuid.UUID) -> Application:
    app = db.get(Application, aid)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "not found")
    return app


@router.get("/applications/{aid}/interviews", response_model=list[InterviewOut])
def list_interviews(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    _own_app(db, user, aid)
    return (
        db.query(Interview)
        .filter_by(application_id=aid)
        .order_by(Interview.scheduled_at.asc())
        .all()
    )


@router.post("/applications/{aid}/interviews", response_model=InterviewOut)
def create_interview(
    aid: uuid.UUID,
    body: InterviewCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    _own_app(db, user, aid)
    iv = Interview(
        application_id=aid, scheduled_at=body.scheduled_at, kind=body.kind, notes=body.notes
    )
    db.add(iv); db.commit(); db.refresh(iv)
    return iv


@router.patch("/interviews/{iid}", response_model=InterviewOut)
def update_interview(
    iid: uuid.UUID,
    body: InterviewUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    iv = db.get(Interview, iid)
    if not iv:
        raise HTTPException(404, "not found")
    _own_app(db, user, iv.application_id)
    if body.scheduled_at is not None: iv.scheduled_at = body.scheduled_at
    if body.kind is not None: iv.kind = body.kind
    if body.notes is not None: iv.notes = body.notes
    if body.outcome is not None: iv.outcome = body.outcome
    db.commit(); db.refresh(iv)
    return iv


@router.delete("/interviews/{iid}")
def delete_interview(
    iid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    iv = db.get(Interview, iid)
    if not iv:
        raise HTTPException(404, "not found")
    _own_app(db, user, iv.application_id)
    db.delete(iv); db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Wire router in `main.py`.**

- [ ] **Step 3: Tests — `backend/tests/integration/test_interviews.py`**

```python
def test_interview_lifecycle(auth_user, db_session):
    from app.db.models import (
        AnschreibenVariant, Application, ApplicationStatus, CVVariant, JobState,
    )
    c, u = auth_user
    cv = db_session.query(CVVariant).filter_by(user_id=u.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=u.id).first()
    app = Application(
        user_id=u.id, url="https://x/y", url_hash="h",
        cv_variant_id=cv.id, anschreiben_variant_id=an.id,
        status=ApplicationStatus.draft, job_state=JobState.ready,
    )
    db_session.add(app); db_session.commit(); db_session.refresh(app)
    r = c.post(
        f"/api/applications/{app.id}/interviews",
        json={"scheduled_at": "2026-05-10T10:00:00", "kind": "phone", "notes": "n1"},
    )
    assert r.status_code == 200
    iid = r.json()["id"]
    r2 = c.post(
        f"/api/applications/{app.id}/interviews",
        json={"scheduled_at": "2026-05-12T10:00:00", "kind": "technical"},
    )
    assert r2.status_code == 200
    r3 = c.get(f"/api/applications/{app.id}/interviews")
    assert len(r3.json()) == 2
    r4 = c.patch(f"/api/interviews/{iid}", json={"outcome": "passed", "notes": "ok"})
    assert r4.status_code == 200
    assert r4.json()["outcome"] == "passed"
    r5 = c.delete(f"/api/interviews/{iid}")
    assert r5.status_code == 200
    assert len(c.get(f"/api/applications/{app.id}/interviews").json()) == 1
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/interviews.py backend/app/main.py backend/tests/integration/test_interviews.py
git commit -m "feat(api): interviews CRUD with multi-interview support"
```

---

## Task 17: Frontend scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "applicator-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview --port 5173",
    "test": "playwright test"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.51.0",
    "@uiw/react-md-editor": "^4.0.4",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.45.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.6",
    "typescript": "^5.5.3",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `frontend/tailwind.config.js` and `frontend/postcss.config.js`**

```js
// tailwind.config.js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

```js
// postcss.config.js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Applicator</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 7: Create `frontend/src/main.tsx` and `frontend/src/App.tsx`**

```tsx
// main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const qc = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

```tsx
// App.tsx (placeholder)
export default function App() {
  return (
    <div className="p-6 text-2xl">
      Applicator — frontend scaffolded
    </div>
  );
}
```

- [ ] **Step 8: Install + run smoke**

```bash
cd frontend && npm install
npm run build
```
Expected: build succeeds.

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "chore(frontend): vite + react + tailwind scaffolding"
```

---

## Task 18: Frontend API client + auth flow

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/api/client.ts`**

```ts
export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(typeof body === "object" && body && "detail" in body ? String((body as any).detail) : `HTTP ${status}`);
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch {}
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
```

- [ ] **Step 2: Create `frontend/src/api/auth.ts`**

```ts
import { api } from "./client";

export type Me = { id: string; email: string; display_name: string };

export const auth = {
  me: () => api<Me>("/api/auth/me"),
  logout: () => api<{ ok: true }>("/api/auth/logout", { method: "POST" }),
  loginUrl: () => "/api/auth/login",
};
```

- [ ] **Step 3: Create `frontend/src/hooks/useAuth.ts`**

```ts
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { auth, Me } from "../api/auth";

export function useAuth() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await auth.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}
```

- [ ] **Step 4: Create `frontend/src/pages/Login.tsx`**

```tsx
export default function Login() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="bg-white p-8 rounded shadow w-96 text-center">
        <h1 className="text-2xl font-semibold mb-6">Applicator</h1>
        <a
          href="/api/auth/login"
          className="inline-block bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
        >
          Sign in with Microsoft
        </a>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Update `frontend/src/App.tsx` to route**

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import { useAuth } from "./hooks/useAuth";

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="*"
        element={
          <ProtectedShell>
            <div className="p-6">Authenticated — applications page next.</div>
          </ProtectedShell>
        }
      />
    </Routes>
  );
}
```

- [ ] **Step 6: Smoke**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): api client, auth hook, login page"
```

---

## Task 19: Frontend — Applications list + Add form

**Files:**
- Create: `frontend/src/api/applications.ts`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/AddApplicationForm.tsx`
- Create: `frontend/src/pages/ApplicationsList.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/api/applications.ts`**

```ts
import { api } from "./client";

export type AppStatus = "draft" | "applied" | "offer" | "rejected" | "accepted" | "withdrawn";
export type JobState = "pending" | "crawling" | "extracting" | "generating" | "ready" | "failed";

export type JobPosting = {
  title: string | null;
  company: string | null;
  location: string | null;
  description: string | null;
  requirements: string | null;
  contact_person: string | null;
  application_email: string | null;
  deadline: string | null;
  salary: string | null;
  tech_stack: string[] | null;
  seniority: string | null;
  work_mode: string | null;
  benefits: string[] | null;
  language: string | null;
};

export type Application = {
  id: string;
  url: string;
  status: AppStatus;
  job_state: JobState;
  job_error: string | null;
  language: string | null;
  generated_md: string | null;
  has_docx: boolean;
  job_posting: JobPosting | null;
};

export const applications = {
  list: () => api<Application[]>("/api/applications"),
  get: (id: string) => api<Application>(`/api/applications/${id}`),
  create: (url: string) =>
    api<Application>("/api/applications", { method: "POST", body: JSON.stringify({ url }) }),
  setStatus: (id: string, status: AppStatus) =>
    api<Application>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  retry: (id: string) =>
    api<Application>(`/api/applications/${id}/retry`, { method: "POST" }),
  docxUrl: (id: string) => `/api/applications/${id}/docx`,
};
```

- [ ] **Step 2: Create `frontend/src/components/StatusBadge.tsx`**

```tsx
import { AppStatus, JobState } from "../api/applications";

const STATUS_CLASS: Record<AppStatus, string> = {
  draft: "bg-slate-200 text-slate-700",
  applied: "bg-blue-100 text-blue-700",
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  accepted: "bg-green-200 text-green-800",
  withdrawn: "bg-slate-300 text-slate-600",
};

export function StatusBadge({ status }: { status: AppStatus }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_CLASS[status]}`}>
      {status}
    </span>
  );
}

const JOB_STATE_LABEL: Record<JobState, string> = {
  pending: "Queued",
  crawling: "Crawling…",
  extracting: "Extracting…",
  generating: "Generating…",
  ready: "Ready",
  failed: "Failed",
};

export function JobStateBadge({ state }: { state: JobState }) {
  const cls =
    state === "ready"
      ? "bg-emerald-100 text-emerald-700"
      : state === "failed"
      ? "bg-rose-100 text-rose-700"
      : "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${cls}`}>{JOB_STATE_LABEL[state]}</span>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/AddApplicationForm.tsx`**

```tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applications } from "../api/applications";

export function AddApplicationForm() {
  const [url, setUrl] = useState("");
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (u: string) => applications.create(u),
    onSuccess: () => { setUrl(""); qc.invalidateQueries({ queryKey: ["applications"] }); },
  });
  return (
    <form
      className="flex gap-2 mb-4"
      onSubmit={(e) => { e.preventDefault(); if (url.trim()) m.mutate(url.trim()); }}
    >
      <input
        type="url" required value={url} onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste job posting URL"
        className="border rounded px-3 py-2 flex-1"
      />
      <button
        type="submit" disabled={m.isPending}
        className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
      >Add</button>
      {m.isError && <span className="text-rose-600 self-center">{(m.error as Error).message}</span>}
    </form>
  );
}
```

- [ ] **Step 4: Create `frontend/src/pages/ApplicationsList.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { applications } from "../api/applications";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge } from "../components/StatusBadge";

export default function ApplicationsList() {
  const { data, isLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: applications.list,
    refetchInterval: (q) => {
      const arr = q.state.data;
      if (!arr) return false;
      const inFlight = arr.some(
        (a) => !["ready", "failed"].includes(a.job_state),
      );
      return inFlight ? 2000 : false;
    },
  });
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />
      {isLoading && <div>Loading…</div>}
      <ul className="divide-y border rounded bg-white">
        {(data ?? []).map((a) => (
          <li key={a.id} className="p-3 flex items-center gap-3 hover:bg-slate-50">
            <Link to={`/applications/${a.id}`} className="flex-1 truncate">
              <div className="font-medium">{a.job_posting?.title ?? a.url}</div>
              <div className="text-sm text-slate-500">{a.job_posting?.company}</div>
            </Link>
            <JobStateBadge state={a.job_state} />
            <StatusBadge status={a.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Wire into `App.tsx`**

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import ApplicationsList from "./pages/ApplicationsList";
import { useAuth } from "./hooks/useAuth";

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/applications"
        element={<ProtectedShell><ApplicationsList /></ProtectedShell>}
      />
      <Route path="*" element={<Navigate to="/applications" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 6: Smoke build**

```bash
cd frontend && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): applications list + add form with polling"
```

---

## Task 20: Frontend — Application detail (job posting + editor + chat + status + interviews)

**Files:**
- Create: `frontend/src/api/chat.ts`
- Create: `frontend/src/api/interviews.ts`
- Create: `frontend/src/components/JobPostingPanel.tsx`
- Create: `frontend/src/components/AnschreibenEditor.tsx`
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/components/InterviewsList.tsx`
- Create: `frontend/src/pages/ApplicationDetail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/api/chat.ts`**

```ts
import { api } from "./client";

export type ChatMsg = { id: string; role: "user" | "assistant" | "system"; content: string };

export const chat = {
  history: (aid: string) => api<ChatMsg[]>(`/api/applications/${aid}/chat`),
  refine: (aid: string, message: string) =>
    api<{ assistant_message: string; generated_md: string }>(
      `/api/applications/${aid}/chat`,
      { method: "POST", body: JSON.stringify({ message }) },
    ),
};
```

- [ ] **Step 2: Create `frontend/src/api/interviews.ts`**

```ts
import { api } from "./client";

export type InterviewKind = "phone" | "video" | "onsite" | "technical" | "final";
export type InterviewOutcome = "pending" | "passed" | "failed" | "cancelled";

export type Interview = {
  id: string;
  application_id: string;
  scheduled_at: string;
  kind: InterviewKind;
  notes: string | null;
  outcome: InterviewOutcome;
};

export const interviews = {
  list: (aid: string) => api<Interview[]>(`/api/applications/${aid}/interviews`),
  create: (aid: string, scheduled_at: string, kind: InterviewKind, notes?: string) =>
    api<Interview>(`/api/applications/${aid}/interviews`, {
      method: "POST",
      body: JSON.stringify({ scheduled_at, kind, notes }),
    }),
  update: (id: string, patch: Partial<Pick<Interview, "outcome" | "notes" | "scheduled_at" | "kind">>) =>
    api<Interview>(`/api/interviews/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  remove: (id: string) => api<{ ok: true }>(`/api/interviews/${id}`, { method: "DELETE" }),
};
```

- [ ] **Step 3: Create `frontend/src/components/JobPostingPanel.tsx`**

```tsx
import { JobPosting } from "../api/applications";

export function JobPostingPanel({ jp }: { jp: JobPosting | null }) {
  if (!jp) return <div className="text-slate-500">Awaiting extraction…</div>;
  const Field = ({ label, value }: { label: string; value: React.ReactNode }) =>
    value ? (
      <div className="mb-3">
        <div className="text-xs uppercase text-slate-500">{label}</div>
        <div>{value}</div>
      </div>
    ) : null;
  return (
    <div>
      <Field label="Title" value={jp.title} />
      <Field label="Company" value={jp.company} />
      <Field label="Location" value={jp.location} />
      <Field label="Work mode" value={jp.work_mode} />
      <Field label="Seniority" value={jp.seniority} />
      <Field label="Salary" value={jp.salary} />
      <Field label="Deadline" value={jp.deadline} />
      <Field label="Contact" value={jp.contact_person} />
      <Field label="Email" value={jp.application_email} />
      <Field label="Tech stack" value={jp.tech_stack?.join(", ")} />
      <Field label="Benefits" value={jp.benefits?.join(", ")} />
      <Field label="Requirements" value={<pre className="whitespace-pre-wrap">{jp.requirements}</pre>} />
      <Field label="Description" value={<pre className="whitespace-pre-wrap">{jp.description}</pre>} />
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/AnschreibenEditor.tsx`**

```tsx
import MDEditor from "@uiw/react-md-editor";
import { applications } from "../api/applications";

export function AnschreibenEditor({
  appId,
  md,
  onChange,
  hasDocx,
}: {
  appId: string;
  md: string;
  onChange: (v: string) => void;
  hasDocx: boolean;
}) {
  return (
    <div>
      <MDEditor value={md} onChange={(v) => onChange(v ?? "")} height={500} />
      <div className="mt-2 flex gap-2">
        {hasDocx && (
          <a
            href={applications.docxUrl(appId)}
            className="bg-emerald-600 text-white px-4 py-2 rounded"
          >
            Download DOCX
          </a>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/components/ChatPanel.tsx`**

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chat } from "../api/chat";

export function ChatPanel({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");
  const history = useQuery({
    queryKey: ["chat", appId],
    queryFn: () => chat.history(appId),
  });
  const m = useMutation({
    mutationFn: (text: string) => chat.refine(appId, text),
    onSuccess: () => {
      setMsg("");
      qc.invalidateQueries({ queryKey: ["chat", appId] });
      qc.invalidateQueries({ queryKey: ["application", appId] });
    },
  });
  return (
    <div className="border rounded bg-white p-3 mt-4">
      <div className="space-y-2 mb-3 max-h-64 overflow-y-auto">
        {(history.data ?? []).map((h) => (
          <div key={h.id} className={h.role === "user" ? "text-right" : ""}>
            <span
              className={`inline-block px-2 py-1 rounded ${
                h.role === "user" ? "bg-blue-100" : "bg-slate-100"
              }`}
            >{h.content}</span>
          </div>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); if (msg.trim()) m.mutate(msg.trim()); }}
      >
        <input
          value={msg} onChange={(e) => setMsg(e.target.value)}
          placeholder="Ask the assistant to refine the letter…"
          className="flex-1 border rounded px-3 py-2"
        />
        <button
          disabled={m.isPending}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >Send</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 6: Create `frontend/src/components/InterviewsList.tsx`**

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Interview, InterviewKind, InterviewOutcome, interviews } from "../api/interviews";

const KINDS: InterviewKind[] = ["phone", "video", "onsite", "technical", "final"];
const OUTCOMES: InterviewOutcome[] = ["pending", "passed", "failed", "cancelled"];

export function InterviewsList({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["interviews", appId], queryFn: () => interviews.list(appId) });
  const [when, setWhen] = useState("");
  const [kind, setKind] = useState<InterviewKind>("phone");
  const create = useMutation({
    mutationFn: () => interviews.create(appId, when, kind),
    onSuccess: () => { setWhen(""); qc.invalidateQueries({ queryKey: ["interviews", appId] }); },
  });
  const update = useMutation({
    mutationFn: (args: { id: string; outcome: InterviewOutcome }) =>
      interviews.update(args.id, { outcome: args.outcome }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["interviews", appId] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => interviews.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["interviews", appId] }),
  });
  return (
    <div className="border rounded bg-white p-3 mt-4">
      <h3 className="font-medium mb-2">Interviews</h3>
      <div className="flex gap-2 mb-3">
        <input
          type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <select value={kind} onChange={(e) => setKind(e.target.value as InterviewKind)} className="border rounded px-2 py-1">
          {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <button
          onClick={() => when && create.mutate()}
          className="bg-blue-600 text-white px-3 py-1 rounded"
        >Add</button>
      </div>
      <ul className="space-y-1">
        {(list.data ?? []).map((iv: Interview) => (
          <li key={iv.id} className="flex items-center gap-2">
            <span className="flex-1">
              {new Date(iv.scheduled_at).toLocaleString()} — {iv.kind}
            </span>
            <select
              value={iv.outcome}
              onChange={(e) => update.mutate({ id: iv.id, outcome: e.target.value as InterviewOutcome })}
              className="border rounded px-1 py-0.5"
            >
              {OUTCOMES.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <button onClick={() => remove.mutate(iv.id)} className="text-rose-600 text-sm">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 7: Create `frontend/src/pages/ApplicationDetail.tsx`**

```tsx
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppStatus, applications } from "../api/applications";
import { JobPostingPanel } from "../components/JobPostingPanel";
import { AnschreibenEditor } from "../components/AnschreibenEditor";
import { ChatPanel } from "../components/ChatPanel";
import { InterviewsList } from "../components/InterviewsList";
import { JobStateBadge, StatusBadge } from "../components/StatusBadge";

const STATUSES: AppStatus[] = ["draft", "applied", "offer", "rejected", "accepted", "withdrawn"];

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["application", id],
    queryFn: () => applications.get(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const a = query.state.data;
      if (!a) return false;
      return ["pending", "crawling", "extracting", "generating"].includes(a.job_state) ? 2000 : false;
    },
  });
  const [md, setMd] = useState("");
  useEffect(() => {
    if (q.data?.generated_md != null) setMd(q.data.generated_md);
  }, [q.data?.generated_md]);

  const setStatus = useMutation({
    mutationFn: (s: AppStatus) => applications.setStatus(id!, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });
  const retry = useMutation({
    mutationFn: () => applications.retry(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["application", id] }),
  });

  if (q.isLoading || !q.data) return <div className="p-6">Loading…</div>;
  const a = q.data;
  return (
    <div className="p-6 grid grid-cols-2 gap-6 max-w-7xl mx-auto">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h1 className="text-xl font-semibold flex-1 truncate">
            {a.job_posting?.title ?? a.url}
          </h1>
          <JobStateBadge state={a.job_state} />
          <StatusBadge status={a.status} />
        </div>
        {a.job_state === "failed" && (
          <div className="bg-rose-50 border border-rose-200 p-3 rounded mb-3">
            <div className="text-rose-700 text-sm mb-2">Failed: {a.job_error}</div>
            <button onClick={() => retry.mutate()} className="bg-rose-600 text-white px-3 py-1 rounded">Retry</button>
          </div>
        )}
        <div className="bg-white border rounded p-3">
          <JobPostingPanel jp={a.job_posting} />
        </div>
        <div className="mt-4 flex items-center gap-2">
          <span>Status:</span>
          <select
            value={a.status}
            onChange={(e) => setStatus.mutate(e.target.value as AppStatus)}
            className="border rounded px-2 py-1"
          >
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <InterviewsList appId={a.id} />
      </div>
      <div>
        {a.generated_md != null ? (
          <>
            <AnschreibenEditor appId={a.id} md={md} onChange={setMd} hasDocx={a.has_docx} />
            <ChatPanel appId={a.id} />
          </>
        ) : (
          <div className="text-slate-500">Anschreiben pending…</div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Wire into `App.tsx`**

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import ApplicationsList from "./pages/ApplicationsList";
import ApplicationDetail from "./pages/ApplicationDetail";
import { useAuth } from "./hooks/useAuth";

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/applications" element={<ProtectedShell><ApplicationsList /></ProtectedShell>} />
      <Route
        path="/applications/:id"
        element={<ProtectedShell><ApplicationDetail /></ProtectedShell>}
      />
      <Route path="*" element={<Navigate to="/applications" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 9: Smoke build**

```bash
cd frontend && npm run build
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): application detail with editor, chat, interviews"
```

---

## Task 21: Frontend — Settings pages (CV / Anschreiben / LLM)

**Files:**
- Create: `frontend/src/api/documents.ts`
- Create: `frontend/src/pages/SettingsCV.tsx`
- Create: `frontend/src/pages/SettingsAnschreiben.tsx`
- Create: `frontend/src/pages/SettingsLLM.tsx`
- Modify: `frontend/src/App.tsx` (add routes + nav)

- [ ] **Step 1: Create `frontend/src/api/documents.ts`**

```ts
import { api } from "./client";

export type Variant = { id: string; name: string; source_md: string; is_default: boolean };

function crud(path: "cv-variants" | "anschreiben-variants") {
  return {
    list: () => api<Variant[]>(`/api/${path}`),
    create: (name: string, source_md: string, is_default = false) =>
      api<Variant>(`/api/${path}`, {
        method: "POST", body: JSON.stringify({ name, source_md, is_default }),
      }),
    update: (id: string, patch: Partial<Variant>) =>
      api<Variant>(`/api/${path}/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    remove: (id: string) => api<{ ok: true }>(`/api/${path}/${id}`, { method: "DELETE" }),
  };
}

export const cv = crud("cv-variants");
export const anschreiben = crud("anschreiben-variants");
```

- [ ] **Step 2: Create a generic settings page** — `frontend/src/pages/_VariantSettings.tsx`

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import MDEditor from "@uiw/react-md-editor";
import type { Variant } from "../api/documents";

type CrudApi = {
  list: () => Promise<Variant[]>;
  create: (name: string, md: string, is_default?: boolean) => Promise<Variant>;
  update: (id: string, patch: Partial<Variant>) => Promise<Variant>;
  remove: (id: string) => Promise<unknown>;
};

export function VariantSettings({ title, api, queryKey }: { title: string; api: CrudApi; queryKey: string }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: [queryKey], queryFn: api.list });
  const [name, setName] = useState("");
  const [md, setMd] = useState("");
  const [editing, setEditing] = useState<Variant | null>(null);
  const create = useMutation({
    mutationFn: () => api.create(name, md, list.data?.length === 0),
    onSuccess: () => { setName(""); setMd(""); qc.invalidateQueries({ queryKey: [queryKey] }); },
  });
  const save = useMutation({
    mutationFn: (v: Variant) => api.update(v.id, { name: v.name, source_md: v.source_md }),
    onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey: [queryKey] }); },
  });
  const setDefault = useMutation({
    mutationFn: (id: string) => api.update(id, { is_default: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [queryKey] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [queryKey] }),
  });
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">{title}</h1>
      <ul className="space-y-2 mb-6">
        {(list.data ?? []).map((v) =>
          editing?.id === v.id ? (
            <li key={v.id} className="border rounded p-3 bg-white">
              <input
                value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                className="border rounded px-2 py-1 mb-2 w-full"
              />
              <MDEditor
                value={editing.source_md}
                onChange={(s) => setEditing({ ...editing, source_md: s ?? "" })}
                height={400}
              />
              <div className="flex gap-2 mt-2">
                <button className="bg-blue-600 text-white px-3 py-1 rounded" onClick={() => save.mutate(editing)}>Save</button>
                <button className="px-3 py-1" onClick={() => setEditing(null)}>Cancel</button>
              </div>
            </li>
          ) : (
            <li key={v.id} className="border rounded p-3 bg-white flex items-center gap-2">
              <span className="flex-1">
                {v.name} {v.is_default && <span className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">default</span>}
              </span>
              {!v.is_default && (
                <button onClick={() => setDefault.mutate(v.id)} className="text-sm text-blue-600">Make default</button>
              )}
              <button onClick={() => setEditing(v)} className="text-sm">Edit</button>
              <button onClick={() => remove.mutate(v.id)} className="text-sm text-rose-600">Delete</button>
            </li>
          ),
        )}
      </ul>
      <h2 className="text-lg font-medium mb-2">New</h2>
      <input
        placeholder="Name" value={name} onChange={(e) => setName(e.target.value)}
        className="border rounded px-2 py-1 mb-2 w-full"
      />
      <MDEditor value={md} onChange={(v) => setMd(v ?? "")} height={300} />
      <button
        disabled={!name || !md}
        onClick={() => create.mutate()}
        className="bg-blue-600 text-white px-4 py-2 rounded mt-2 disabled:opacity-50"
      >Add</button>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/pages/SettingsCV.tsx` and `SettingsAnschreiben.tsx`**

```tsx
// SettingsCV.tsx
import { cv } from "../api/documents";
import { VariantSettings } from "./_VariantSettings";
export default () => <VariantSettings title="CV variants" api={cv} queryKey="cv-variants" />;
```

```tsx
// SettingsAnschreiben.tsx
import { anschreiben } from "../api/documents";
import { VariantSettings } from "./_VariantSettings";
export default () => (
  <VariantSettings title="Anschreiben templates" api={anschreiben} queryKey="anschreiben-variants" />
);
```

- [ ] **Step 4: Create `frontend/src/pages/SettingsLLM.tsx`**

LLM settings live in `.env` for MVP — document the placeholder in UI.

```tsx
export default function SettingsLLM() {
  return (
    <div className="max-w-2xl mx-auto p-6 prose">
      <h1>LLM settings</h1>
      <p>
        LLM provider, model, base URL and API key are configured via the backend{" "}
        <code>.env</code> for MVP. Defaults: <code>LLM_PROVIDER=groq</code>,{" "}
        <code>LLM_MODEL=gpt-oss</code>,{" "}
        <code>LLM_BASE_URL=https://api.groq.com/openai/v1</code>.
      </p>
    </div>
  );
}
```

- [ ] **Step 5: Update `App.tsx` with nav + routes**

```tsx
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Login from "./pages/Login";
import ApplicationsList from "./pages/ApplicationsList";
import ApplicationDetail from "./pages/ApplicationDetail";
import SettingsCV from "./pages/SettingsCV";
import SettingsAnschreiben from "./pages/SettingsAnschreiben";
import SettingsLLM from "./pages/SettingsLLM";
import { useAuth } from "./hooks/useAuth";

function Nav() {
  const loc = useLocation();
  const item = (to: string, label: string) => (
    <Link
      to={to}
      className={`px-3 py-2 ${loc.pathname.startsWith(to) ? "font-semibold" : ""}`}
    >{label}</Link>
  );
  return (
    <nav className="bg-white border-b px-4 py-2 flex gap-2 items-center">
      <span className="font-bold mr-3">Applicator</span>
      {item("/applications", "Applications")}
      {item("/settings/cv", "CV")}
      {item("/settings/anschreiben", "Anschreiben")}
      {item("/settings/llm", "LLM")}
      <form action="/api/auth/logout" method="post" className="ml-auto">
        <button className="text-sm text-slate-600">Logout</button>
      </form>
    </nav>
  );
}

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useAuth();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (!data) return <Navigate to="/login" replace />;
  return <><Nav />{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/applications" element={<ProtectedShell><ApplicationsList /></ProtectedShell>} />
      <Route path="/applications/:id" element={<ProtectedShell><ApplicationDetail /></ProtectedShell>} />
      <Route path="/settings/cv" element={<ProtectedShell><SettingsCV /></ProtectedShell>} />
      <Route path="/settings/anschreiben" element={<ProtectedShell><SettingsAnschreiben /></ProtectedShell>} />
      <Route path="/settings/llm" element={<ProtectedShell><SettingsLLM /></ProtectedShell>} />
      <Route path="*" element={<Navigate to="/applications" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 6: Smoke build**

```bash
cd frontend && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): settings pages + nav"
```

---

## Task 22: docker-compose, Dockerfiles, README

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Modify: `docker-compose.yml`
- Create: `README.md`

- [ ] **Step 1: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libcups2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libasound2 libxshmfence1 \
    libxss1 fonts-liberation libdrm2 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .
RUN python -m playwright install chromium
COPY . /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20 AS build
WORKDIR /app
COPY package.json /app/
RUN npm install
COPY . /app
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

- [ ] **Step 3: Create `frontend/nginx.conf`**

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
  }

  location / {
    try_files $uri /index.html;
  }
}
```

- [ ] **Step 4: Update `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: applicator
      POSTGRES_USER: applicator
      POSTGRES_PASSWORD: applicator
    volumes: ["pgdata:/var/lib/postgresql/data"]

  api:
    build: ./backend
    env_file: .env
    depends_on: [db]
    volumes:
      - ./data:/app/data
    command: ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

  web:
    build: ./frontend
    depends_on: [api]
    ports: ["8080:80"]

volumes:
  pgdata:
```

- [ ] **Step 5: Create `README.md`**

```markdown
# Applicator

Self-hosted job application assistant.

## Run locally

1. Copy `.env.example` to `.env` and fill MS OAuth + LLM keys.
2. `docker compose up --build`
3. Open http://localhost:8080

## Tests

Backend:
```
cd backend && pytest
```

Frontend e2e:
```
cd frontend && npx playwright install && npx playwright test
```
```

- [ ] **Step 6: Build & smoke**

```bash
docker compose build
```
Expected: builds succeed.

- [ ] **Step 7: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile frontend/nginx.conf docker-compose.yml README.md
git commit -m "chore: docker compose + Dockerfiles + README"
```

---

## Task 23: E2E happy-path test (Playwright)

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/e2e.spec.ts`

This test stubs `/api/*` endpoints to avoid running real backend. It validates the SPA flow: list → add → polled → ready → download visible.

- [ ] **Step 1: Create `frontend/playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  webServer: {
    command: "npm run dev",
    port: 5173,
    reuseExistingServer: true,
  },
  use: { baseURL: "http://localhost:5173" },
});
```

- [ ] **Step 2: Create `frontend/tests/e2e.spec.ts`**

```ts
import { test, expect } from "@playwright/test";

test("happy path: add URL, poll until ready, see download", async ({ page }) => {
  let getCalls = 0;
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify({ id: "u", email: "x@y.z", display_name: "X" }) }),
  );
  await page.route("**/api/applications", async (route, req) => {
    if (req.method() === "POST") {
      return route.fulfill({
        status: 202,
        body: JSON.stringify({
          id: "a1", url: "https://x.test/j", status: "draft",
          job_state: "pending", job_error: null, language: null,
          generated_md: null, has_docx: false, job_posting: null,
        }),
      });
    }
    return route.fulfill({ status: 200, body: JSON.stringify([]) });
  });
  await page.route("**/api/applications/a1", (route) => {
    getCalls++;
    const states = ["pending", "extracting", "ready"];
    const s = states[Math.min(getCalls - 1, states.length - 1)];
    return route.fulfill({
      status: 200,
      body: JSON.stringify({
        id: "a1", url: "https://x.test/j", status: "draft",
        job_state: s, job_error: null, language: "en",
        generated_md: s === "ready" ? "# Hello" : null,
        has_docx: s === "ready",
        job_posting:
          s === "ready"
            ? {
                title: "Dev", company: "Acme", location: null,
                description: "d", requirements: "r", contact_person: null,
                application_email: null, deadline: null, salary: null,
                tech_stack: ["python"], seniority: null, work_mode: null,
                benefits: null, language: "en",
              }
            : null,
      }),
    });
  });
  await page.route("**/api/applications/a1/chat", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );
  await page.route("**/api/applications/a1/interviews", (r) =>
    r.fulfill({ status: 200, body: JSON.stringify([]) }),
  );

  await page.goto("/applications");
  await page.fill("input[type=url]", "https://x.test/j");
  await page.click("button:has-text('Add')");
  await page.goto("/applications/a1");
  await expect(page.locator("text=Dev")).toBeVisible({ timeout: 10000 });
  await expect(page.locator("a:has-text('Download DOCX')")).toBeVisible();
});
```

- [ ] **Step 3: Run**

```bash
cd frontend && npx playwright install chromium
npx playwright test
```
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add frontend/playwright.config.ts frontend/tests/
git commit -m "test(frontend): e2e happy path with mocked API"
```

---

## Task 24: Final verification + README polish

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && pytest -v
```
Expected: all pass.

- [ ] **Step 2: Run frontend build + e2e**

```bash
cd frontend && npm run build && npx playwright test
```
Expected: build clean, e2e passes.

- [ ] **Step 3: Manual verification checklist**

Bring up the stack: `docker compose up --build` and verify:
- `/login` redirects to MS, callback creates session, lands on `/applications`
- Settings → CV → add a default CV
- Settings → Anschreiben → add a default template
- Add a real job URL → list polls → detail page shows extracted fields and generated Anschreiben
- Chat panel: send "Make it shorter" → Anschreiben updates, DOCX is regenerated
- Download DOCX → opens cleanly in Word
- Status → set "applied"; add an interview; mark outcome "passed"

- [ ] **Step 4: Commit any final tweaks**

```bash
git add -A
git commit -m "chore: final verification fixes" || true
```

---

## Self-Review

**1. Spec coverage:**
- Microsoft OAuth2 → Task 11
- Paste URL pipeline → Tasks 6, 7, 8, 9, 10, 13, 14
- Chat refinement → Task 15
- Versioned CV/Anschreiben w/ defaults → Task 12, 21
- Status + interviews → Task 14, 16, 20
- Configurable LLM (Groq default) → Task 5, 21
- Postgres + Alembic → Task 3
- Docker compose deploy → Task 22
- E2E happy path → Task 23
- All in scope. OneDrive token storage handled in Task 11 (`ms_refresh_token_encrypted`).

**2. Placeholder scan:** No `TBD`/`TODO`/"add appropriate error handling"; every step shows code or a concrete command.

**3. Type consistency:** `JobPosting` is the DB model; `ExtractedJobPosting` is the pydantic schema returned by the extractor; `JobPostingOut` is the API response. Each used consistently. `applications.create/list/get/setStatus/retry/docxUrl` names match between frontend `api/applications.ts` and backend routes.

**Note on test fixtures:** Several integration tests share `app_client` and `auth_user` fixtures. To avoid duplication, promote them to `backend/tests/integration/conftest.py` once they appear in two tests; the plan text shows them inline for clarity but consolidating during implementation is expected DRY work.
