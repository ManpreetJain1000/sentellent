# Sentellent

Monorepo for the Sentellent AI chief-of-staff platform.

## Repository layout

| Directory | Description |
| --- | --- |
| [`backend/`](backend/) | FastAPI API, LangGraph agent, Celery workers |
| [`frontend/`](frontend/) | React + Vite web application |
| [`docs/`](docs/) | Setup guides and project documentation |
| [`infra/`](infra/) | Terraform and cloud infrastructure |

## Quick start

1. Copy environment files:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```
2. Start infrastructure and backend services:
   ```bash
   docker compose up -d postgres redis
   docker compose up backend worker beat
   ```
3. Run the frontend dev server:
   ```bash
   cd frontend && npm install && npm run dev
   ```

See [`docs/setup.md`](docs/setup.md) for the full setup guide.
