# Sentellent — Local & Deployment Setup Guide

This guide explains how to run Sentellent in three ways:

1. **Docker Compose** — fastest way to spin up infrastructure and app containers together
2. **AWS** — staging/production deployment with Terraform and GitHub Actions
3. **Local (native)** — run frontend and backend directly on your machine with minimal containers

Each section explains **every service** used by the application and what role it plays.

---

## Application services overview

Before following any setup path, understand what each component does and how they connect.

| Service | Technology | Role in Sentellent |
| --- | --- | --- |
| **Frontend** | React, TypeScript, Vite, Tailwind CSS | Browser UI: landing page, Google sign-in, agentic chat, memory sidebar, workspace connection status. Talks to the backend over HTTP. Default dev URL: `http://localhost:5173`. |
| **Backend API** | FastAPI, Uvicorn | Core HTTP API under `/api/v1`: authentication (Google OAuth + JWT), conversations, chat with the agent, memory CRUD, org membership, background job status, health checks. Default port: `8000`. |
| **PostgreSQL** | PostgreSQL 16 + **pgvector** extension | Primary datastore: users, organizations, conversations, messages, memory items (with vector embeddings), workspace OAuth tokens, background jobs, and LangGraph conversation checkpoints. Requires the `vector` extension (created by Alembic migration `0002_workspace_pgvector`). |
| **Redis** | Redis 7 | Session cache, API rate limiting (auth/chat/ingest), Celery message broker and result backend, and worker heartbeat key (`worker:heartbeat`). Falls back to in-memory storage when Redis is unavailable (dev only). |
| **Celery Worker** | Celery 5 | Runs background tasks off the request path. Main task: `ingest_user_inbox` — fetches Gmail and persists facts into memory without blocking chat. |
| **Celery Beat** | Celery Beat scheduler | Runs periodic tasks. Sends `worker_heartbeat` every 60 seconds so `/api/v1/health` can report whether a worker is alive. |
| **LangGraph Agent** | LangGraph + Groq LLM | Chief-of-staff agent inside the backend process. Uses Groq models for reasoning and tools for Gmail, Google Calendar, and memory retrieval. Checkpoints are stored in PostgreSQL. |
| **Groq API** | External LLM provider | Powers the agent (`GROQ_API_KEY`, `GROQ_MODEL_NAME`). Not hosted by you — configure an API key in `.env`. |
| **Google OAuth / Workspace APIs** | External (Google Cloud) | Sign-in, Gmail read, Calendar read/write. Requires OAuth client credentials and enabled Gmail + Calendar APIs. See [google-oauth-setup.md](./google-oauth-setup.md). |
| **Sentry** (optional) | External error tracking | Initialized when `SENTRY_DSN` is set. Captures backend exceptions in production. |
| **S3** (optional) | AWS S3 | Referenced by `S3_UPLOAD_BUCKET_NAME` for future uploads/artifacts. Not required for core chat flows. |

```mermaid
flowchart TB
  Browser[Frontend - React/Vite]
  API[Backend - FastAPI]
  PG[(PostgreSQL + pgvector)]
  Redis[(Redis)]
  Worker[Celery Worker]
  Beat[Celery Beat]
  Groq[Groq API]
  Google[Google OAuth / Gmail / Calendar]

  Browser --> API
  API --> PG
  API --> Redis
  API --> Groq
  API --> Google
  Worker --> Redis
  Worker --> PG
  Worker --> Google
  Beat --> Redis
  Beat --> Worker
```

---

## Prerequisites (all setups)

| Tool | Version | Purpose |
| --- | --- | --- |
| **Docker** + **Docker Compose** | Latest stable | Run PostgreSQL, Redis, and optionally backend/worker containers |
| **Python** | 3.11+ (3.12 recommended) | Backend and Celery |
| **Node.js** | 22+ | Frontend dev server and build |
| **Git** | Any recent version | Clone the repository |

You will also need:

- A **Groq API key** — [console.groq.com](https://console.groq.com)
- **Google OAuth credentials** — see [google-oauth-setup.md](./google-oauth-setup.md)
- A strong **JWT secret** for local dev (any long random string in `JWT_SECRET_KEY`)

For environment variable details, see [environment-variables.md](./environment-variables.md).

---

# 1. Docker Compose setup

Docker Compose is the recommended way to run **PostgreSQL**, **Redis**, and optionally the **backend**, **worker**, and **beat** services with one command. The **frontend** is usually run with `npm run dev` on the host for hot reload.

## 1.1 Create `docker-compose.yml`

Create this file at the repository root (or adjust paths to match your layout):

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: sentellent-postgres
    environment:
      POSTGRES_DB: sentellent
      POSTGRES_USER: sentellent_user
      POSTGRES_PASSWORD: sentellent_password
    ports:
      - "5432:5432"
    volumes:
      - sentellent_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sentellent_user -d sentellent"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: sentellent-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: sentellent-backend
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: postgresql+psycopg://sentellent_user:sentellent_password@postgres:5432/sentellent
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: sentellent-worker
    command: ["celery", "-A", "app.workers.celery_app", "worker", "-l", "info"]
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: postgresql+psycopg://sentellent_user:sentellent_password@postgres:5432/sentellent
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: sentellent-beat
    command: ["celery", "-A", "app.workers.celery_app", "beat", "-l", "info"]
    env_file:
      - ./backend/.env
    environment:
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy

volumes:
  sentellent_pgdata:
```

### What each Compose service does

| Compose service | Maps to | Explanation |
| --- | --- | --- |
| `postgres` | **PostgreSQL + pgvector** | Stores all persistent application data and vector embeddings. The `pgvector/pgvector:pg16` image includes the extension required for semantic memory search. Data survives restarts via the `sentellent_pgdata` volume. |
| `redis` | **Redis** | Shared cache and Celery transport. Backend uses it for sessions and rate limits; worker and beat use it as broker/backend. |
| `backend` | **FastAPI backend** | Builds from `backend/Dockerfile`. Runs Alembic migrations on startup, then Uvicorn on port `8000`. Serves the REST API and hosts the LangGraph agent. |
| `worker` | **Celery worker** | Same image as backend, different command. Processes `ingest_user_inbox` and other async tasks so chat requests are not blocked by Gmail API calls. |
| `beat` | **Celery Beat** | Scheduler that triggers `worker_heartbeat` every 60 seconds. Required for the health endpoint to report `worker: ok`. |

## 1.2 Configure environment files

### Backend (`backend/.env`)

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and set at minimum:

```env
JWT_SECRET_KEY=<your-random-secret>
GROQ_API_KEY=<your-groq-key>
GOOGLE_OAUTH_CLIENT_ID=<your-google-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<your-google-client-secret>
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
EMAIL_INGEST_ASYNC_ENABLED=true
CELERY_TASK_ALWAYS_EAGER=false
```

When using Compose, `DATABASE_URL` and `REDIS_URL` in the compose file override hostnames (`postgres`, `redis`) — you do not need to change those in `.env` if the compose `environment` block is set as above.

### Frontend (`frontend/.env`)

```bash
cd frontend
cp .env.example .env
```

```env
VITE_API_BASE_URL=http://localhost:8000
```

## 1.3 Start the stack

### Option A — Infrastructure only (run backend on host)

Useful when you want `--reload` on the API during development:

```bash
# Start PostgreSQL and Redis
docker compose up postgres redis -d

# Backend (host)
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Celery worker (host, if async ingest enabled)
celery -A app.workers.celery_app worker -l info

# Celery beat (host, separate terminal)
celery -A app.workers.celery_app beat -l info

# Frontend (host)
cd frontend && npm install && npm run dev
```

### Option B — Full Compose stack

```bash
docker compose up --build -d
cd frontend && npm install && npm run dev
```

## 1.4 Verify Docker Compose setup

| Check | Command / URL | Expected |
| --- | --- | --- |
| PostgreSQL | `docker compose ps postgres` | `healthy` |
| Redis | `docker compose exec redis redis-cli ping` | `PONG` |
| Backend health | `curl http://localhost:8000/api/v1/health` | `"status": "ok"` with `database`, `redis`, and `worker` checks |
| Frontend | Open `http://localhost:5173` | Landing page loads |
| Google OAuth | Open `http://localhost:8000/api/v1/auth/google/start` | Redirects to Google sign-in |

### Email ingest note

When `EMAIL_INGEST_ASYNC_ENABLED=true`, the agent returns a processing message instead of live Gmail data until the worker finishes. For immediate inbox answers in chat, set:

```env
EMAIL_INGEST_ASYNC_ENABLED=false
```

Or keep async mode and wait for the background job to complete (`GET /api/v1/jobs/{id}`).

---

# 2. AWS setup

AWS deployment provisions managed infrastructure for staging/production. Application code is built into a Docker image, pushed to ECR, and run on ECS Fargate. The frontend is hosted on Amplify.

Terraform definitions live in `infra/terraform/`. CI/CD is in `.github/workflows/deploy.yml`.

## 2.1 AWS services used

| AWS service | Role in Sentellent |
| --- | --- |
| **VPC + subnets + security groups** | Network isolation. ECS tasks, RDS, and ElastiCache run in private subnets. Security groups allow backend → PostgreSQL (5432) and backend/worker → Redis (6379). |
| **Amazon RDS (PostgreSQL 16)** | Managed PostgreSQL database — same schema as local (users, orgs, memory with pgvector, checkpoints, jobs). Not publicly accessible. |
| **Amazon ElastiCache (Redis 7)** | Managed Redis for sessions, rate limits, Celery broker/backend, and worker heartbeat. |
| **Amazon ECS Fargate** | Serverless containers. Two services: **backend** (Uvicorn API) and **worker** (Celery). No servers to manage. |
| **Amazon ECR** | Private Docker registry. GitHub Actions builds `backend/Dockerfile` and pushes images tagged with the git SHA. |
| **API Gateway (HTTP API)** | Public HTTPS entry point for the backend. Proxies `ANY /{proxy+}` to the ECS backend service on port 8000. |
| **AWS Amplify** | Builds and hosts the React frontend from the `frontend/` directory. Injects `VITE_API_BASE_URL` at build time. |
| **CloudWatch Logs** | Log groups `/ecs/{project}-{env}-backend` and `/ecs/{project}-{env}-worker` for container stdout. |
| **IAM** | ECS task execution role pulls images from ECR and reads secrets from Secrets Manager. |
| **Secrets Manager** | Stores `JWT_SECRET_KEY`, `GROQ_API_KEY`, and Google OAuth credentials (referenced by ARN in Terraform). |
| **S3** (Terraform backend) | Remote state bucket `sentellent-terraform-state` for Terraform state locking and persistence. |

External services (not provisioned by Terraform but required):

- **Groq API** — LLM provider
- **Google Cloud OAuth** — authentication and workspace APIs
- **Sentry** (optional) — error tracking via `SENTRY_DSN`

## 2.2 Prerequisites

1. AWS account with permissions for ECS, RDS, ElastiCache, Amplify, API Gateway, IAM, Secrets Manager, and S3.
2. An existing **VPC** with at least two **private subnets** (see `vpc_id` and `private_subnet_ids` in Terraform variables).
3. **Terraform** >= 1.6.0 installed locally.
4. **AWS CLI** configured (`aws configure` or SSO).
5. GitHub repository with OIDC deploy role (`AWS_DEPLOY_ROLE_ARN` secret).

## 2.3 One-time AWS preparation

### Step 1 — Create Secrets Manager secrets

Create secrets for:

| Secret | Used by |
| --- | --- |
| `JWT_SECRET_KEY` | Backend + worker (JWT signing) |
| `GROQ_API_KEY` | Backend + worker (LLM) |
| `GOOGLE_OAUTH_CLIENT_ID` | Backend + worker (OAuth) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Backend + worker (OAuth) |

Note each secret's **ARN** — Terraform references them via `jwt_secret_arn`, `groq_api_key_arn`, etc.

### Step 2 — Create ECR repository

```bash
aws ecr create-repository --repository-name sentellent-backend --region us-east-1
```

Build and push an initial image (replace account ID and region):

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker build -t sentellent-backend ./backend
docker tag sentellent-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/sentellent-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/sentellent-backend:latest
```

### Step 3 — Create Terraform state bucket

```bash
aws s3 mb s3://sentellent-terraform-state --region us-east-1
```

Update `infra/terraform/main.tf` if you use a different bucket name or region.

### Step 4 — Configure Terraform variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region         = "us-east-1"
environment        = "staging"
vpc_id             = "vpc-xxxxxxxx"
private_subnet_ids = ["subnet-aaaaaaa", "subnet-bbbbbbb"]
db_password        = "<strong-db-password>"
backend_image      = "<account-id>.dkr.ecr.us-east-1.amazonaws.com/sentellent-backend:latest"
jwt_secret_arn     = "arn:aws:secretsmanager:..."
groq_api_key_arn   = "arn:aws:secretsmanager:..."
google_oauth_client_id_arn     = "arn:aws:secretsmanager:..."
google_oauth_client_secret_arn = "arn:aws:secretsmanager:..."
github_repository_url = "https://github.com/your-org/sentellent"
backend_api_url    = "https://xxxxxxxx.execute-api.us-east-1.amazonaws.com"
```

`backend_api_url` is the API Gateway endpoint (available after first `terraform apply`, or set after you know the URL and re-apply for Amplify OAuth variables).

### Step 5 — Apply Terraform

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

Terraform creates, in order of dependency:

1. **Security groups** — network rules for backend, database, and Redis
2. **RDS PostgreSQL** — `aws_db_instance.postgres` with subnet group and 7-day backups
3. **ElastiCache Redis** — single-node `cache.t4g.micro` cluster
4. **ECS cluster** — `sentellent-staging-cluster`
5. **CloudWatch log groups** — backend and worker logs
6. **ECS task definitions** — backend (port 8000) and worker (Celery command)
7. **ECS services** — backend and worker Fargate services in private subnets
8. **API Gateway** — HTTP API with proxy integration to backend
9. **Amplify app + branch** — frontend build from `frontend/` with `VITE_API_BASE_URL`

Capture outputs:

```bash
terraform output api_gateway_endpoint
terraform output amplify_frontend_url
terraform output postgres_endpoint
terraform output redis_endpoint
```

### Step 6 — Run database migrations

Migrations run automatically in the backend Docker entrypoint (`alembic upgrade head`). The deploy workflow also runs them before ECS rollout:

```bash
cd backend
pip install .
DATABASE_URL="postgresql+psycopg://..." alembic upgrade head
```

Use the RDS endpoint from Terraform output and credentials from `terraform.tfvars`.

### Step 7 — Configure Google OAuth for production

In Google Cloud Console, add production URLs:

| Setting | Value |
| --- | --- |
| Authorized redirect URI | `https://<api-gateway-endpoint>/api/v1/auth/google/callback` |
| Authorized JavaScript origin | `https://<amplify-frontend-url>` |

Set backend environment (via Terraform task definition or ECS console):

- `GOOGLE_OAUTH_REDIRECT_URI` — production callback URL
- `FRONTEND_URL` — Amplify frontend URL
- `CORS_ORIGINS` — Amplify frontend URL

See [google-oauth-setup.md](./google-oauth-setup.md) for full OAuth steps.

### Step 8 — Configure GitHub Actions deploy secrets

In your GitHub repository settings, add:

| Secret | Purpose |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | IAM role for OIDC deploy |
| `DATABASE_URL` | RDS connection string for migration step |
| `AMPLIFY_APP_ID` | From `terraform output amplify_app_id` |
| `AMPLIFY_BRANCH_NAME` | Usually `main` |

On push to `main`, the deploy workflow:

1. Builds and pushes the backend image to **ECR**
2. Runs **Alembic migrations** against RDS
3. Forces new deployment of **ECS backend** and **ECS worker** services
4. Triggers an **Amplify** frontend release

## 2.4 Verify AWS deployment

| Check | How |
| --- | --- |
| API health | `curl https://<api-gateway-endpoint>/api/v1/health` |
| Frontend | Open Amplify URL from `terraform output amplify_frontend_url` |
| Backend logs | CloudWatch → `/ecs/sentellent-staging-backend` |
| Worker logs | CloudWatch → `/ecs/sentellent-staging-worker` |
| RDS connectivity | ECS tasks use `DATABASE_URL` built from RDS endpoint in task definition |
| Redis connectivity | Health check `redis: ok`; worker heartbeat `worker: ok` when worker service is running |

## 2.5 AWS architecture diagram

```mermaid
flowchart LR
  User[User Browser]
  Amp[Amplify - Frontend]
  APIGW[API Gateway]
  ECS_API[ECS Fargate - Backend]
  ECS_Worker[ECS Fargate - Worker]
  RDS[(RDS PostgreSQL)]
  Redis[(ElastiCache Redis)]
  ECR[ECR]
  SM[Secrets Manager]
  CW[CloudWatch Logs]

  User --> Amp
  User --> APIGW
  Amp --> APIGW
  APIGW --> ECS_API
  ECS_API --> RDS
  ECS_API --> Redis
  ECS_Worker --> RDS
  ECS_Worker --> Redis
  ECR --> ECS_API
  ECR --> ECS_Worker
  SM --> ECS_API
  SM --> ECS_Worker
  ECS_API --> CW
  ECS_Worker --> CW
```

---

# 3. Local setup (native, without full Docker Compose)

This path installs Python and Node dependencies directly on your machine. You still need **PostgreSQL** and **Redis** — either installed natively or started via Docker for just those two services.

## 3.1 Install infrastructure services

### PostgreSQL with pgvector

**Option A — Docker (recommended)**

```bash
docker run -d \
  --name sentellent-postgres \
  -e POSTGRES_DB=sentellent \
  -e POSTGRES_USER=sentellent_user \
  -e POSTGRES_PASSWORD=sentellent_password \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

**Option B — Native PostgreSQL**

Install PostgreSQL 16 and the pgvector extension for your OS, then create the database:

```sql
CREATE USER sentellent_user WITH PASSWORD 'sentellent_password';
CREATE DATABASE sentellent OWNER sentellent_user;
\c sentellent
CREATE EXTENSION IF NOT EXISTS vector;
```

### Redis

**Option A — Docker**

```bash
docker run -d --name sentellent-redis -p 6379:6379 redis:7-alpine
```

**Option B — Native**

Install Redis 7 and start the server on port `6379`.

| Service | Why you need it locally |
| --- | --- |
| **PostgreSQL + pgvector** | All app data, vector memory search, LangGraph checkpoints |
| **Redis** | Sessions, rate limits, Celery (if using async worker), health checks |

## 3.2 Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://sentellent_user:sentellent_password@localhost:5432/sentellent
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=<random-secret>
GROQ_API_KEY=<your-groq-key>
GOOGLE_OAUTH_CLIENT_ID=<your-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<your-client-secret>
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Run migrations and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| Component | What happens |
| --- | --- |
| **Alembic** | Applies migrations `0001`–`0004`: schema, pgvector, memory, multitenancy |
| **Uvicorn** | Serves FastAPI with hot reload on code changes |
| **FastAPI app** | Loads settings from `.env`, configures CORS, structlog, optional Sentry, LangGraph checkpoint schema |

## 3.3 Celery worker and beat (optional but recommended)

Required when `EMAIL_INGEST_ASYNC_ENABLED=true` (default in `.env.example`).

**Terminal 2 — Worker**

```bash
cd backend && source venv/bin/activate
celery -A app.workers.celery_app worker -l info
```

**Terminal 3 — Beat**

```bash
cd backend && source venv/bin/activate
celery -A app.workers.celery_app beat -l info
```

| Process | Role |
| --- | --- |
| **Celery worker** | Executes `ingest_user_inbox` and writes email-derived memories to PostgreSQL |
| **Celery beat** | Schedules `worker_heartbeat` every 60s; health endpoint uses this to report worker status |

**Simpler alternative:** set `CELERY_TASK_ALWAYS_EAGER=true` to run tasks inline in the API process (no separate worker). Good for quick testing; not ideal for production-like behavior.

## 3.4 Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

| Setting | Purpose |
| --- | --- |
| `VITE_API_BASE_URL=http://localhost:8000` | All API calls from the browser go to the local backend |
| `VITE_APP_NAME` | Display name in the UI |

Open **http://localhost:5173**.

## 3.5 Google OAuth (required for sign-in)

Follow [google-oauth-setup.md](./google-oauth-setup.md):

1. Create a Google Cloud OAuth **Web application** client
2. Add redirect URI `http://localhost:8000/api/v1/auth/google/callback`
3. Add JavaScript origin `http://localhost:5173`
4. Enable **Gmail API** and **Google Calendar API**
5. Add your email as a test user if the consent screen is in Testing mode

## 3.6 Verify local setup

```bash
# Health (from backend directory)
curl http://localhost:8000/api/v1/health

# Backend tests
cd backend && pytest -q

# Frontend tests
cd frontend && npm test
```

Expected health response (all services running):

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "worker": "ok"
  }
}
```

If `worker` is `stale`, start the Celery worker and beat, or set `CELERY_TASK_ALWAYS_EAGER=true`.

## 3.7 Local development terminal layout

| Terminal | Command | Service |
| --- | --- | --- |
| 1 | `docker compose up postgres redis -d` (or native DB/Redis) | PostgreSQL, Redis |
| 2 | `uvicorn app.main:app --reload` | Backend API + LangGraph agent |
| 3 | `celery -A app.workers.celery_app worker -l info` | Celery worker |
| 4 | `celery -A app.workers.celery_app beat -l info` | Celery beat |
| 5 | `npm run dev` | Frontend (Vite) |

---

## Quick comparison

| Aspect | Docker Compose | AWS | Local native |
| --- | --- | --- | --- |
| **Best for** | Consistent infra, team onboarding | Staging/production | Day-to-day feature development |
| **PostgreSQL** | Compose `postgres` service | RDS | Docker or native install |
| **Redis** | Compose `redis` service | ElastiCache | Docker or native install |
| **Backend** | Container or host | ECS Fargate | Host with `uvicorn --reload` |
| **Worker / Beat** | Compose or host | ECS worker service | Host Celery processes |
| **Frontend** | Always `npm run dev` locally | Amplify hosted | `npm run dev` |
| **LLM / OAuth** | External API keys | External API keys | External API keys |

---

## Troubleshooting

| Problem | Likely cause | Fix |
| --- | --- | --- |
| `redirect_uri_mismatch` | Google OAuth URI mismatch | See [google-oauth-setup.md](./google-oauth-setup.md) |
| Database connection refused | PostgreSQL not running | Start postgres container or service |
| `CREATE EXTENSION vector` fails | Wrong Postgres image | Use `pgvector/pgvector:pg16` |
| Redis errors / rate limit fallback | Redis not running | Start redis on port 6379 |
| Health `worker: stale` | No Celery worker or beat | Start worker + beat, or use eager mode |
| Chat invents email content | Async ingest enabled, job not done | Set `EMAIL_INGEST_ASYNC_ENABLED=false` or wait for job |
| CORS errors | Frontend origin not allowed | Add origin to `CORS_ORIGINS` in backend `.env` |

---

## Related documentation

- [environment-variables.md](./environment-variables.md) — full variable reference
- [google-oauth-setup.md](./google-oauth-setup.md) — Google Cloud OAuth configuration
- [backend/README.md](../backend/README.md) — API routes and backend scope
- [frontend/README.md](../frontend/README.md) — frontend scope
- [infra/terraform/README.md](../infra/terraform/README.md) — Terraform resource list
