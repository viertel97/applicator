# Telegram Bot — Design Spec

**Date:** 2026-05-24  
**Status:** Approved

## Goal

Allow job posting URLs to be submitted to Applicator via Telegram even when the app is down. Telegram buffers messages server-side; the bot drains the backlog on startup and processes URLs through the existing pipeline.

---

## Architecture

```
Telegram servers
      │
      │  getUpdates (polling)
      ▼
┌─────────────┐   POST /api/bot/applications   ┌──────────────┐
│  bot service│  ──────────────────────────▶  │  api service │
│  (own ctnr) │  Authorization: Bearer TOKEN   │              │
└─────────────┘                                └──────┬───────┘
                                                      │ enqueue crawl_task(app_id, chat_id)
                                                      ▼
                                               ┌──────────────┐
                                               │    worker    │
                                               │  (Celery)    │
                                               └──────┬───────┘
                                                      │ notify_task → sendMessage
                                                      ▼
                                               Telegram servers
```

The bot container is the only piece with a Telegram dependency. The worker sends the "Done" notification directly to the Telegram Bot API via httpx — no PTB needed in the worker.

---

## Bot Container (`bot/`)

**Files:**
- `bot/bot.py` — all bot logic
- `bot/Dockerfile` — slim Python image

**Dependencies:** `python-telegram-bot[http2]`, `httpx`

**Behavior:**
- PTB async polling with `drop_pending_updates=False` — drains backlog on startup automatically
- Silently ignores all messages where `from_user.id != TELEGRAM_ALLOWED_USER_ID`
- On URL message: POST to API, reply `"Queued: <url>"`
- On non-URL message: reply `"Send a job posting URL"`

**Env vars:**

| Var | Description |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_ALLOWED_USER_ID` | Your Telegram numeric user ID |
| `BOT_API_KEY` | Static secret for bot→API auth |
| `API_URL` | Internal API base URL, default `http://api:8000` |

---

## Backend Changes

### New endpoint: `POST /api/bot/applications`

**File:** `backend/app/api/bot.py`

**Auth:** validates `Authorization: Bearer <BOT_API_KEY>` header. Returns 401 otherwise.

**Request body:**
```json
{ "url": "https://...", "chat_id": 123456789 }
```

**Behavior:**
1. Deduplicates by `url_hash` (same as existing `create` endpoint)
2. Creates `Application` record under `APP_USER_ID`
3. Enqueues the full pipeline chain: `crawl_task | extract_task | generate_task | notify_task`
4. `chat_id` flows through the task chain payload

**Response:**
```json
{ "app_id": "...", "url": "..." }
```

**New env vars (backend/worker):**

| Var | Description |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | Same token — worker uses it to send "Done" |
| `BOT_API_KEY` | Validated on every bot endpoint request |
| `APP_USER_ID` | Postgres UUID of the user applications are created under |

### New Celery task: `notify_task`

**File:** `backend/app/tasks/pipeline.py` (added alongside existing tasks)

Chained at the end of the pipeline. Receives `payload` dict which includes `chat_id` (if present — bot submissions have it, manual submissions don't). Calls `https://api.telegram.org/bot<TOKEN>/sendMessage` via httpx with:

```
"Done: <job_title>"
```

If `chat_id` is absent or `TELEGRAM_BOT_TOKEN` is unset, task is a no-op.

---

## Docker

New service in `docker-compose.yml`:

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

The bot starts only after the API is healthy. Stops with the stack. No port exposure needed.

Existing `worker` service already uses `env_file: .env` — it picks up `TELEGRAM_BOT_TOKEN` and `BOT_API_KEY` without changes.

---

## Data Flow (URL submitted while app is down)

1. User sends URL to bot — app stack is down
2. Telegram stores message (server-side, up to Telegram's retention)
3. User starts stack: `docker compose up`
4. `api` becomes healthy → `bot` container starts
5. PTB polls `getUpdates` → receives backlogged message(s)
6. Bot POSTs each URL to API → API creates Application + enqueues pipeline
7. Worker processes pipeline → `notify_task` sends "Done: `<job title>`" back to user

---

## Env File Changes

Add to `.env.example`:

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
BOT_API_KEY=
APP_USER_ID=
```

---

## Out of Scope

- Multiple users / multi-tenant
- Commands (`/start`, `/help`, `/list`) — can be added later via PTB handlers
- Webhook mode — polling is correct for self-hosted intermittent deployments
- Retry on failed pipeline (existing Celery retry logic covers this)
