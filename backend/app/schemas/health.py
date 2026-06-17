from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    environment: str
    tenant_model: str
    conversation_retention_days: int
    encrypt_sensitive_data_at_rest: bool
    checks: dict[str, str] = Field(default_factory=dict)
