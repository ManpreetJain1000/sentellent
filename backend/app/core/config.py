from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="sentellent")
    app_environment: str = Field(default="development")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    database_url: str = Field(default="postgresql+psycopg://sentellent_user:sentellent_password@localhost:5432/sentellent")
    redis_url: str = Field(default="redis://localhost:6379/0")
    jwt_secret_key: str = Field(default="change-me")
    jwt_access_token_expires_minutes: int = Field(default=60)
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")
    google_oauth_redirect_uri: AnyHttpUrl | str = Field(
        default="http://localhost:8000/api/v1/auth/google/callback"
    )
    groq_api_key: str = Field(default="")
    groq_model_name: str = Field(default="llama-3.3-70b-versatile")
    groq_fallback_model_name: str = Field(default="qwen/qwen3-32b")
    groq_fallback_models: str = Field(
        default="qwen/qwen3-32b,openai/gpt-oss-120b,qwen/qwen3.6-27b"
    )
    agent_max_history_messages: int = Field(default=8)
    agent_max_tool_rounds: int = Field(default=6)
    pgvector_embedding_dimensions: int = Field(default=384)
    embedding_model_name: str = Field(default="hash-v1")
    s3_upload_bucket_name: str = Field(default="")
    conversation_retention_days: int = Field(default=30)
    encrypt_sensitive_data_at_rest: bool = Field(default=True)
    tenant_scope_column: str = Field(default="organization_id")
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000")
    frontend_url: str = Field(default="http://localhost:5173")
    google_oauth_scopes: str = Field(
        default=(
            "openid email profile "
            "https://www.googleapis.com/auth/gmail.readonly "
            "https://www.googleapis.com/auth/calendar"
        )
    )
    token_encryption_key: str = Field(default="")
    default_timezone: str = Field(default="Asia/Kolkata")
    celery_broker_url: str = Field(default="")
    celery_result_backend: str = Field(default="")
    celery_task_always_eager: bool = Field(default=False)
    sentry_dsn: str = Field(default="")
    rate_limit_auth_per_minute: int = Field(default=10)
    rate_limit_chat_per_minute: int = Field(default=20)
    rate_limit_ingest_per_hour: int = Field(default=5)
    email_ingest_async_enabled: bool = Field(default=True)

    @property
    def celery_broker_url_resolved(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_result_backend_resolved(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def groq_model_chain(self) -> list[str]:
        chain: list[str] = []
        for candidate in (
            self.groq_model_name,
            self.groq_fallback_model_name,
            *[item.strip() for item in self.groq_fallback_models.split(",") if item.strip()],
        ):
            if candidate and candidate not in chain:
                chain.append(candidate)
        return chain

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def google_scope_list(self) -> list[str]:
        return [scope.strip() for scope in self.google_oauth_scopes.split(" ") if scope.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def database_connect_args(self) -> dict[str, str]:
        if "supabase.co" in self.database_url:
            return {"sslmode": "require"}
        return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
