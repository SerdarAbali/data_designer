"""Enterprise module of the demo generator (strategy to execution)."""

from __future__ import annotations

from app.models import (
    ArchitecturePrinciple,
    BusinessCapability,
    BusinessGoal,
    BusinessProcess,
    BusinessRequirement,
    OrganizationRole,
)

from .context import DemoContext


def _add(db, ctx: DemoContext, key: str, registry_kind: str, typed, position) -> None:
    row_id = ctx.id(key)
    db.add(ctx.registry(key, registry_kind))
    db.add(typed)
    ctx.add_node("current", key + ".cur", row_id, position, discipline="enterprise")
    ctx.add_node("candidate", key + ".cand", row_id, position, discipline="enterprise")


def build_enterprise(db, ctx: DemoContext) -> None:
    now = ctx.now
    candidate = ctx.id("state.candidate")
    goal_id = ctx.id("ent.goal")
    requirement_id = ctx.id("ent.requirement")
    capability_id = ctx.id("ent.capability")
    process_id = ctx.id("ent.process")
    principle_id = ctx.id("ent.principle")
    risk_id = ctx.id("ent.risk")
    role_id = ctx.id("ent.role")

    _add(
        db,
        ctx,
        "ent.goal",
        "business_goal",
        BusinessGoal(
            object_id=goal_id,
            tenant_id=ctx.tenant_id,
            name="Reduce customer onboarding time",
            description="Onboard customers in hours, not weeks, without manual rework.",
            owner="Head of Customer Operations",
            outcome_metric="Time from signup to active account under 1 business day",
            horizon="12 months",
            properties={},
            created_in_state_id=None,
            created_at=now,
            updated_at=now,
        ),
        {"x": 80, "y": 60},
    )
    _add(
        db,
        ctx,
        "ent.requirement",
        "business_requirement",
        BusinessRequirement(
            object_id=requirement_id,
            tenant_id=ctx.tenant_id,
            name="Capture verified customer details",
            description="Verified identity, contact details and consent are captured once.",
        ),
        {"x": 80, "y": 260},
    )
    _add(
        db,
        ctx,
        "ent.capability",
        "business_capability",
        BusinessCapability(
            object_id=capability_id,
            tenant_id=ctx.tenant_id,
            name="Customer onboarding",
            description="Register, verify and activate a customer account.",
        ),
        {"x": 420, "y": 60},
    )
    _add(
        db,
        ctx,
        "ent.process",
        "business_process",
        BusinessProcess(
            object_id=process_id,
            tenant_id=ctx.tenant_id,
            name="Customer onboarding",
            description="Current-state manual onboarding step pending automation.",
            owner="Head of Customer Operations",
            process_type="value_stream",
            properties={},
            created_in_state_id=None,
            created_at=now,
            updated_at=now,
        ),
        {"x": 420, "y": 260},
    )
    _add(
        db,
        ctx,
        "ent.principle",
        "architecture_principle",
        ArchitecturePrinciple(
            object_id=principle_id,
            tenant_id=ctx.tenant_id,
            name="Consent before marketing",
            description="Customer consent is recorded before any marketing use.",
            principle_type="constraint",
            rationale="Regulatory requirement.",
            properties={},
            created_in_state_id=None,
            created_at=now,
            updated_at=now,
        ),
        {"x": 760, "y": 60},
    )
    # The single intentional synthetic risk that keeps the Enterprise gap and
    # impact analysis demonstrable; it is deliberately left unlinked.
    _add(
        db,
        ctx,
        "ent.risk",
        "architecture_principle",
        ArchitecturePrinciple(
            object_id=risk_id,
            tenant_id=ctx.tenant_id,
            name="Legacy billing dependency",
            description="Billing still depends on the legacy batch interface (synthetic demo).",
            principle_type="risk",
            rationale="Single point of failure during onboarding activation.",
            properties={},
            created_in_state_id=None,
            created_at=now,
            updated_at=now,
        ),
        {"x": 760, "y": 420},
    )
    _add(
        db,
        ctx,
        "ent.role",
        "organization_role",
        OrganizationRole(
            object_id=role_id,
            tenant_id=ctx.tenant_id,
            name="Head of Customer Operations",
            description="Owns onboarding outcomes.",
            role_type="role",
            properties={},
            created_in_state_id=None,
            created_at=now,
            updated_at=now,
        ),
        {"x": 760, "y": 260},
    )

    # Canonical strategy chain plus ownership, governance and application
    # support. Relationship rows are scoped to the candidate state so the
    # enterprise projections surface them, and every edge follows LINK_RULES.
    db.add_all(
        [
            ctx.relationship(
                "ent.rel.goal.requirement",
                goal_id,
                requirement_id,
                "drives",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.requirement.capability",
                requirement_id,
                capability_id,
                "needs",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.capability.process",
                capability_id,
                process_id,
                "has_process",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.capability.principle",
                capability_id,
                principle_id,
                "governed_by",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.process.principle",
                process_id,
                principle_id,
                "governed_by",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.process.role",
                process_id,
                role_id,
                "owned_by",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.capability.role",
                capability_id,
                role_id,
                "owned_by",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.system.crm.capability",
                ctx.id("system.crm"),
                capability_id,
                "supports",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.system.runtime.process",
                ctx.id("system.integration_runtime"),
                process_id,
                "supports",
                created_in_state_id=candidate,
            ),
            ctx.relationship(
                "ent.rel.system.billing.process",
                ctx.id("system.billing"),
                process_id,
                "supports",
                created_in_state_id=candidate,
            ),
        ]
    )
