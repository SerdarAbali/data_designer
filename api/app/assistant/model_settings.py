"""Owner-only assistant provider/model settings and privacy enforcement.

No secret is stored here. Credentials live in server-side secret material (the
OpenCode container's environment); this module records only the observed
credential *status* and never returns a credential value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SENSITIVE_CLASSIFICATIONS, AssistantModelSettings

DEFAULT_PRIVACY = "internal"
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 90
DEFAULT_RETENTION_DAYS = 30

#: Non-secret fields an owner may change.
OWNER_FIELDS = (
    "provider",
    "model_id",
    "model_variant",
    "reasoning_effort",
    "max_input_tokens",
    "max_output_tokens",
    "timeout_seconds",
    "step_limit",
    "retention_days",
    "privacy_classification",
    "trains_on_data",
    "approved_for_sensitive",
    "fallback_provider",
    "fallback_model_id",
    "fallback_enabled",
)

#: Never returned to any client.
SECRET_FIELDS = frozenset({"api_key", "credential", "password", "token", "secret"})


def get_settings(db: Session, tenant_id: UUID) -> AssistantModelSettings:
    settings = db.scalar(
        select(AssistantModelSettings).where(AssistantModelSettings.tenant_id == tenant_id)
    )
    if settings is None:
        settings = AssistantModelSettings(tenant_id=tenant_id, credential_status="missing")
        db.add(settings)
        db.flush()
    return settings


def runtime_model(settings: AssistantModelSettings) -> dict[str, str] | None:
    if not settings.provider or not settings.model_id:
        return None
    return {"providerID": settings.provider, "id": settings.model_id}


def privacy_decision(settings: AssistantModelSettings) -> tuple[bool, str | None]:
    """Whether the configured provider may be used for this tenant's data."""
    if settings.privacy_classification in SENSITIVE_CLASSIFICATIONS:
        if settings.trains_on_data:
            return False, "provider_trains_on_data"
        if not settings.approved_for_sensitive:
            return False, "provider_not_approved_for_sensitive"
        if settings.fallback_enabled:
            return False, "fallback_not_allowed_for_sensitive"
    return True, None


def verify_credential(
    settings: AssistantModelSettings, runtime, *, now: datetime | None = None
) -> str:
    """Verify the provider is available without reading any credential value."""
    moment = now or datetime.now(UTC)
    if not settings.provider or not settings.model_id:
        settings.credential_status = "missing"
        settings.credential_last_verified_at = moment
        return "missing"
    try:
        providers = runtime.providers()
    except Exception:  # noqa: BLE001 - an unreachable runtime is "invalid", not a crash
        settings.credential_status = "invalid"
        settings.credential_last_verified_at = moment
        return "invalid"
    entries = providers if isinstance(providers, list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == settings.provider or entry.get("providerID") == settings.provider:
            settings.credential_status = "configured"
            settings.credential_last_verified_at = moment
            return "configured"
    settings.credential_status = "invalid"
    settings.credential_last_verified_at = moment
    return "invalid"


def public_settings(settings: AssistantModelSettings, *, owner: bool) -> dict:
    """Serialise settings. Never returns a credential value."""
    base = {
        "provider": settings.provider,
        "model_id": settings.model_id,
        "model_variant": settings.model_variant,
        "privacy_classification": settings.privacy_classification,
        "trains_on_data": settings.trains_on_data,
        "approved_for_sensitive": settings.approved_for_sensitive,
        "fallback_enabled": settings.fallback_enabled,
        "fallback_provider": settings.fallback_provider,
        "fallback_model_id": settings.fallback_model_id,
        "credential_status": settings.credential_status,
        "credential_last_verified_at": settings.credential_last_verified_at,
    }
    allowed, reason = privacy_decision(settings)
    base["privacy_allowed"] = allowed
    base["privacy_reason"] = reason
    if not owner:
        # Non-owners see only safe availability information.
        return {
            "privacy_classification": settings.privacy_classification,
            "approved_for_sensitive": settings.approved_for_sensitive,
            "trains_on_data": settings.trains_on_data,
            "credential_status": settings.credential_status,
            "privacy_allowed": allowed,
            "privacy_reason": reason,
        }
    base.update(
        {
            "reasoning_effort": settings.reasoning_effort,
            "max_input_tokens": settings.max_input_tokens,
            "max_output_tokens": settings.max_output_tokens,
            "timeout_seconds": settings.timeout_seconds,
            "step_limit": settings.step_limit,
            "retention_days": settings.retention_days,
        }
    )
    return base


def apply_owner_update(
    settings: AssistantModelSettings, payload: dict, *, updated_by: UUID | None
) -> AssistantModelSettings:
    for field in OWNER_FIELDS:
        if field in payload and payload[field] is not None:
            setattr(settings, field, payload[field])
    settings.updated_by = updated_by
    settings.updated_at = datetime.now(UTC)
    return settings
