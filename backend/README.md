# Backend

FastAPI service for Sentellent Phase 1–2.

## Scope

- Versioned API under `/api/v1`
- Google OAuth sign-in with JWT sessions
- Redis-backed session cache with in-memory fallback
- LangGraph chief-of-staff agent with Groq LLM integration
- **Google Workspace tools:** Gmail inbox fetch, Calendar list/create
- **Email-driven memory:** reading inbox automatically persists facts to memory
- Tenant-scoped PostgreSQL persistence with Alembic migrations
- Memory extraction and semantic retrieval

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Tests

```bash
pytest -q
```

## Key routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/auth/google/login` | Google OAuth URL |
| GET | `/api/v1/auth/me` | Current user |
| GET | `/api/v1/auth/workspace` | Google connection status |
| GET/POST | `/api/v1/conversations` | Conversation list/create |
| DELETE | `/api/v1/conversations/{id}` | Delete a conversation |
| POST | `/api/v1/conversations/{id}/messages` | Chat with agent (Gmail/Calendar tools) |
| GET | `/api/v1/memory` | Learned memory items |
