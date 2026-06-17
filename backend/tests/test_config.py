from app.core.config import get_settings


def test_get_settings_uses_phase_one_defaults() -> None:
    settings = get_settings()

    assert settings.conversation_retention_days == 30
    assert settings.encrypt_sensitive_data_at_rest is True
    assert settings.tenant_scope_column == "organization_id"
