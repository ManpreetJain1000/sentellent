# Environment Variable Reference

This document explains the meaning of the core environment variable names used by the Phase 1 scaffold.

## Shared Variables

| Variable | Meaning |
| --- | --- |
| `PROJECT_NAME` | Human-readable name for logs, UI, and service metadata. |
| `ENVIRONMENT_NAME` | Deployment stage label such as development, staging, or production. |
| `AWS_REGION` | AWS region for deployed infrastructure. |
| `FRONTEND_BASE_URL` | Public URL where the frontend is served. |
| `BACKEND_BASE_URL` | Public URL where the backend is served. |

## Frontend Variables

| Variable | Meaning |
| --- | --- |
| `VITE_APP_NAME` | Browser-visible application name. |
| `VITE_API_BASE_URL` | Base URL used by the frontend to call the backend API. |
| `VITE_GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID used in browser auth flows. |
| `VITE_GOOGLE_REDIRECT_URI` | OAuth redirect URI registered in Google Cloud. |

## Backend Variables

| Variable | Meaning |
| --- | --- |
| `APP_NAME` | FastAPI application name used in logs and metadata. |
| `APP_ENVIRONMENT` | Runtime environment for the backend service. |
| `APP_DEBUG` | Enables development-only debug behavior. |
| `APP_HOST` | Network host the backend binds to. |
| `APP_PORT` | HTTP port the backend exposes. |
| `DATABASE_URL` | PostgreSQL connection string used by the backend. |
| `REDIS_URL` | Redis connection string for session caching. |
| `JWT_SECRET_KEY` | Secret used to sign backend-issued tokens. |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | Lifetime of access tokens in minutes. |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID used server-side. |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret used server-side. |
| `GOOGLE_OAUTH_REDIRECT_URI` | Backend callback URL for OAuth authorization. |
| `GROQ_API_KEY` | API key for the Groq language model provider. |
| `GROQ_MODEL_NAME` | Default Groq model selected for the agent. |
| `PGVECTOR_EMBEDDING_DIMENSIONS` | Expected dimensionality of vector embeddings. |
| `EMBEDDING_MODEL_NAME` | Local embedding provider identifier for memory retrieval. |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API. |
| `FRONTEND_URL` | Public frontend URL used for OAuth redirects. |
| `GOOGLE_OAUTH_SCOPES` | Space-separated Google OAuth scopes for workspace access. |
| `TOKEN_ENCRYPTION_KEY` | Optional key for encrypting stored OAuth tokens at rest. |
| `S3_UPLOAD_BUCKET_NAME` | AWS S3 bucket used for uploads or generated artifacts. |
