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
