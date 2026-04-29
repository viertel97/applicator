# Applicator

Self-hosted job application assistant.

## Run locally

1. Copy `.env.example` to `.env` and fill values:
   - Generate a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` → `APP_SECRET_KEY`
   - Microsoft OAuth: register app at https://entra.microsoft.com → set `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`
   - For dockerized deploy, override `MS_REDIRECT_URI=http://localhost:8080/api/auth/callback` and `FRONTEND_ORIGIN=http://localhost:8080`
   - LLM: set `LLM_API_KEY` (Groq by default)
   - `DATABASE_URL` in `.env` is ignored under compose — the `api` service points at the `db` service automatically.
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
