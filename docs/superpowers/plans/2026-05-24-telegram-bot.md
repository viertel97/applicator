# Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Telegram bot that queues job posting URLs when the app is down and processes them through the pipeline when the app restarts.

**Architecture:** A standalone `bot/` container uses python-telegram-bot (PTB v20, async polling) to receive URLs and POST them to a new internal `POST /api/bot/applications` endpoint protected by a bearer token. A new `notify_task` Celery task is chained at the end of the pipeline to send a "Done: <job title>" reply directly to the Telegram Bot API via httpx.

**Tech Stack:** python-telegram-bot[http2] ≥20, httpx (already in backend), FastAPI, Celery, Docker Compose

---

## File Map

**Create:**
- `bot/bot.py` — PTB async bot: polling loop, user-ID filter, URL handler, POST to API
- `bot/Dockerfile` — slim Python image for bot container
- `bot/requirements.txt` — `python-telegram-bot[http2]`, `httpx`
- `backend/app/api/bot.py` — `POST /api/bot/applications` endpoint with bearer auth
- `backend/tests/integration/test_bot_api.py` — integration tests for bot endpoint
- `backend/tests/unit/test_notify_task.py` — unit tests for notify_task

**Modify:**
- `backend/app/config.py` — add `telegram_bot_token`, `bot_api_key`, `app_user_id` settings
- `backend/app/tasks/pipeline.py` — add `notify_task`
- `backend/app/main.py` — register bot API router
- `backend/tests/conftest.py` — add new env var defaults
- `docker-compose.yml` — add `bot` service
- `.env.example` — add new env vars

---

## Task 1: Add bot/telegram settings to `Settings`

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Add fields to `Settings`**

In `backend/app/config.py`, add three optional fields after `redis_url`:

```python
telegram_bot_token: str = ""
bot_api_key: str = ""
app_user_id: str = ""
```

- [ ] **Step 2: Add env defaults to test conftest**

In `backend/tests/conftest.py`, add three `os.environ.setdefault` lines after the existing ones:

```python
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("BOT_API_KEY", "test-bot-key")
os.environ.setdefault("APP_USER_ID", "")
```

- [ ] **Step 3: Verify settings load**

```bash
cd backend && python -c "from app.config import get_settings; s = get_settings(); print(s.bot_api_key)"
```

Expected output: *(empty string or whatever is in .env)*

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py backend/tests/conftest.py
git commit -m "feat(config): add telegram_bot_token, bot_api_key, app_user_id settings"
```

---

## Task 2: Add `notify_task` to pipeline

**Files:**
- Modify: `backend/app/tasks/pipeline.py`
- Create: `backend/tests/unit/test_notify_task.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_notify_task.py`:

```python
import os
import pytest


def test_notify_task_sends_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json

        class R:
            status_code = 200
        return R()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    # Stub out DB factory so notify_task doesn't need a real DB
    from contextlib import contextmanager
    import app.tasks.pipeline as tp

    @contextmanager
    def fake_cm():
        class FakeDB:
            def get(self, model, pk):
                return None
        yield FakeDB()

    monkeypatch.setattr(tp, "_db_factory", lambda: fake_cm)

    from app.tasks.pipeline import notify_task
    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=42)

    assert sent["url"] == "https://api.telegram.org/bottest-token/sendMessage"
    assert sent["json"]["chat_id"] == 42


def test_notify_task_noop_without_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    called = []

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task
    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=None)

    assert called == []


def test_notify_task_noop_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    called = []

    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(True))

    from app.tasks.pipeline import notify_task
    notify_task({"app_id": "00000000-0000-0000-0000-000000000001"}, chat_id=42)

    assert called == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/unit/test_notify_task.py -v
```

Expected: `ImportError` or `AttributeError` — `notify_task` not yet defined.

- [ ] **Step 3: Add `notify_task` to `pipeline.py`**

Append to `backend/app/tasks/pipeline.py` (after `generate_task`):

```python
@celery_app.task(name="pipeline.notify", bind=False)
def notify_task(payload: dict, chat_id: int | None = None) -> dict:
    if not chat_id:
        return payload
    token = _settings().telegram_bot_token
    if not token:
        return payload
    app_id = payload.get("app_id")
    text = "Done"
    if app_id:
        cm = _db_factory()
        with cm() as db:
            app = db.get(Application, uuid.UUID(app_id))
            if app and app.job_posting and app.job_posting.title:
                text = f"Done: {app.job_posting.title}"
    import httpx as _httpx
    _httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10.0,
    )
    return payload
```

Also add `"app.tasks.pipeline"` is already in `celery_app.include` — no change needed there.

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/unit/test_notify_task.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/pipeline.py backend/tests/unit/test_notify_task.py
git commit -m "feat(pipeline): add notify_task for Telegram done-confirmation"
```

---

## Task 3: Bot API endpoint

**Files:**
- Create: `backend/app/api/bot.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_bot_api.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_bot_api.py`:

```python
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from app.api.deps import db_dep
from app.db import models  # noqa: F401
from app.db.models import Application, User
from app.db.session import Base


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
def db_session(pg, monkeypatch, reset_db_session_singletons):
    raw_url = pg.get_connection_url()
    url = (
        raw_url
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def bot_client(db_session, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "tfCTeAU_0mgpv_WhKykdY0HAXhHRinLOumXAM7HtEMM=")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("BOT_API_KEY", "secret-bot-key")

    from app.main import create_app
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[db_dep] = override_db
    return TestClient(app)


@pytest.fixture
def bot_user(db_session, monkeypatch, bot_client):
    """Create a User and set APP_USER_ID to its id."""
    u = User(ms_oid="bot-oid", email="bot@test.com", display_name="Bot User")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    monkeypatch.setenv("APP_USER_ID", str(u.id))
    return u


@pytest.fixture
def no_celery(monkeypatch):
    import app.api.bot as bot_module
    monkeypatch.setattr(bot_module, "_start_bot_chain", lambda app_id, chat_id: None)


def test_bot_create_application(bot_client, bot_user, db_session, no_celery):
    resp = bot_client.post(
        "/api/bot/applications",
        json={"url": "https://example.com/job/123", "chat_id": 42},
        headers={"Authorization": "Bearer secret-bot-key"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com/job/123"
    assert "app_id" in data

    app_row = db_session.query(Application).filter_by(url="https://example.com/job/123").first()
    assert app_row is not None
    assert app_row.user_id == bot_user.id


def test_bot_rejects_wrong_token(bot_client, bot_user, no_celery):
    resp = bot_client.post(
        "/api/bot/applications",
        json={"url": "https://example.com/job/456", "chat_id": 42},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_bot_rejects_missing_token(bot_client, bot_user, no_celery):
    resp = bot_client.post(
        "/api/bot/applications",
        json={"url": "https://example.com/job/789", "chat_id": 42},
    )
    assert resp.status_code == 401


def test_bot_deduplicates_url(bot_client, bot_user, db_session, no_celery):
    payload = {"url": "https://example.com/job/dup", "chat_id": 42}
    headers = {"Authorization": "Bearer secret-bot-key"}

    resp1 = bot_client.post("/api/bot/applications", json=payload, headers=headers)
    resp2 = bot_client.post("/api/bot/applications", json=payload, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/integration/test_bot_api.py -v
```

Expected: FAIL — `404 Not Found` (endpoint doesn't exist yet).

- [ ] **Step 3: Create `backend/app/api/bot.py`**

```python
import uuid
from typing import Annotated

from celery import chain
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.deps import db_dep, settings_dep
from app.config import Settings
from app.db.models import Application
from app.pipeline import url_hash
from app.tasks.pipeline import crawl_task, extract_task, notify_task

router = APIRouter(prefix="/api/bot", tags=["bot"])


class BotCreateApplication(BaseModel):
    url: HttpUrl
    chat_id: int


def _bot_auth(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(settings_dep),
) -> None:
    expected = f"Bearer {settings.bot_api_key}"
    if not settings.bot_api_key or authorization != expected:
        raise HTTPException(401, "unauthorized")


def _start_bot_chain(app_id: uuid.UUID, chat_id: int) -> None:
    chain(
        crawl_task.s(str(app_id)),
        extract_task.s(),
        notify_task.s(chat_id),
    ).apply_async()


@router.post("/applications")
def bot_create_application(
    body: BotCreateApplication,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    _auth: Annotated[None, Depends(_bot_auth)],
):
    if not settings.app_user_id:
        raise HTTPException(500, "APP_USER_ID not configured")
    user_id = uuid.UUID(settings.app_user_id)
    h = url_hash(str(body.url))
    existing = db.query(Application).filter_by(user_id=user_id, url_hash=h).first()
    if existing:
        raise HTTPException(409, f"application already exists: {existing.id}")
    app_row = Application(user_id=user_id, url=str(body.url), url_hash=h)
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    _start_bot_chain(app_row.id, body.chat_id)
    return {"app_id": str(app_row.id), "url": str(body.url)}
```

- [ ] **Step 4: Register router in `main.py`**

Add to `backend/app/main.py`:

```python
from app.api import bot as bot_api
```

Add inside `create_app()` alongside the other `include_router` calls:

```python
app.include_router(bot_api.router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/integration/test_bot_api.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
cd backend && python -m pytest --ignore=tests/integration -v
```

Expected: all passing (no regressions from router registration).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/bot.py backend/app/main.py backend/tests/integration/test_bot_api.py
git commit -m "feat(api): POST /api/bot/applications with bearer auth"
```

---

## Task 4: Bot container

**Files:**
- Create: `bot/requirements.txt`
- Create: `bot/Dockerfile`
- Create: `bot/bot.py`

- [ ] **Step 1: Create `bot/requirements.txt`**

```
python-telegram-bot[http2]==21.6
httpx==0.27.0
```

- [ ] **Step 2: Create `bot/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
```

- [ ] **Step 3: Create `bot/bot.py`**

```python
import asyncio
import logging
import os

import httpx
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
BOT_API_KEY = os.environ["BOT_API_KEY"]
API_URL = os.environ.get("API_URL", "http://api:8000")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id != ALLOWED_USER_ID:
        return
    if update.message is None or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if not text.startswith("http"):
        await update.message.reply_text("Send a job posting URL")
        return

    try:
        resp = httpx.post(
            f"{API_URL}/api/bot/applications",
            json={"url": text, "chat_id": chat_id},
            headers={"Authorization": f"Bearer {BOT_API_KEY}"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            await update.message.reply_text(f"Queued: {text}")
        elif resp.status_code == 409:
            await update.message.reply_text(f"Already queued: {text}")
        else:
            await update.message.reply_text(f"Error {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        logger.exception("Failed to submit URL")
        await update.message.reply_text(f"Failed to reach API: {exc}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot starting, draining backlog...")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify bot builds**

```bash
docker build ./bot -t applicator-bot-test
```

Expected: image builds without errors.

- [ ] **Step 5: Commit**

```bash
git add bot/
git commit -m "feat(bot): Telegram bot container with PTB polling"
```

---

## Task 5: Docker wiring and env docs

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Add `bot` service to `docker-compose.yml`**

Append to `docker-compose.yml` (after the `worker` service):

```yaml
  bot:
    build: ./bot
    env_file: .env
    environment:
      API_URL: http://api:8000
    depends_on:
      api:
        condition: service_healthy
```

- [ ] **Step 2: Add new vars to `.env.example`**

Append to `.env.example`:

```
# Telegram bot
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
BOT_API_KEY=
APP_USER_ID=
```

- [ ] **Step 3: Verify compose config is valid**

```bash
docker compose config --quiet
```

Expected: exits 0 with no errors.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat(docker): add bot service, document new env vars"
```

---

## Task 6: Smoke test end-to-end

This task verifies the async buffering behaviour manually — no automated test needed since it crosses container boundaries.

- [ ] **Step 1: Set required env vars in `.env`**

```
TELEGRAM_BOT_TOKEN=<your token from BotFather>
TELEGRAM_ALLOWED_USER_ID=<your numeric Telegram user ID>
BOT_API_KEY=<any random secret, e.g. openssl rand -hex 16>
APP_USER_ID=<UUID of your user row — query: SELECT id FROM "user" LIMIT 1>
```

- [ ] **Step 2: Start the full stack**

```bash
docker compose up --build
```

- [ ] **Step 3: Send a job posting URL to the bot while stack is running**

Send any `https://...` URL to your bot in Telegram. Expected: bot replies `"Queued: <url>"`. Expected later: bot sends `"Done: <job title>"` (or `"Done"` if title not extracted).

- [ ] **Step 4: Test the async buffering (the whole point)**

```bash
docker compose down
```

Send another job posting URL to the bot in Telegram while stack is down.

```bash
docker compose up
```

Expected: within seconds of startup, bot replies `"Queued: <url>"` for the message sent while it was down — Telegram queued it server-side and PTB drained it on reconnect.
