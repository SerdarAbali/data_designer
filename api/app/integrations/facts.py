"""Effective generic contract facts (lifecycle, operational status, environment).

The canonical ``integrations`` row is the Current baseline. Candidate/Target
deltas live in ``integration_state_overrides``. Keeping the rule
"state override when present, otherwise the canonical value" in one place means
the landscape, contract-detail, message-flow and facts endpoints cannot drift.

A ``NULL`` override column means *not overridden*: the canonical value (which
may itself be ``NULL`` = unspecified) applies. A value is only flagged as
``overridden`` when it actually differs from the canonical baseline, so the UI
never claims a delta that is not there.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Integration, IntegrationStateOverride
from app.models.integration import FACT_FIELDS

__all__ = [
    "FACT_FIELDS",
    "effective_fact",
    "effective_facts",
    "override_for_contract",
    "overrides_for_state",
]


def overrides_for_state(
    db: Session, tenant_id: UUID, state_id: UUID
) -> dict[UUID, IntegrationStateOverride]:
    """Every override row for a state, keyed by integration id."""
    rows = db.scalars(
        select(IntegrationStateOverride).where(
            IntegrationStateOverride.tenant_id == tenant_id,
            IntegrationStateOverride.state_id == state_id,
        )
    )
    return {row.integration_id: row for row in rows}


def override_for_contract(
    db: Session, tenant_id: UUID, state_id: UUID, integration_id: UUID
) -> IntegrationStateOverride | None:
    return db.scalar(
        select(IntegrationStateOverride).where(
            IntegrationStateOverride.tenant_id == tenant_id,
            IntegrationStateOverride.state_id == state_id,
            IntegrationStateOverride.integration_id == integration_id,
        )
    )


def effective_fact(canonical: str | None, override: str | None) -> dict:
    """Resolve one fact: state override when present, otherwise canonical."""
    return {
        "value": override if override is not None else canonical,
        "canonical": canonical,
        "override": override,
        "overridden": override is not None and override != canonical,
    }


def effective_facts(
    integration: Integration, override: IntegrationStateOverride | None
) -> dict[str, dict]:
    return {
        field: effective_fact(
            getattr(integration, field, None),
            getattr(override, field, None) if override is not None else None,
        )
        for field in FACT_FIELDS
    }
