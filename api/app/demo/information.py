"""Information module of the demo generator (customer data model).

The Customer entity and its identity attributes exist in Current and are reused
by the candidate; the candidate adds contact/status/consent attributes plus a
secondary Customer Consent entity. One optional attribute is deliberately left
without a physical realization: it is the single, explicitly labelled synthetic
information gap used to exercise unmapped/lineage reporting.
"""

from __future__ import annotations

from uuid import UUID

from app.models import (
    ArchitectureRelationship,
    CatalogField,
    InformationAttribute,
    InformationObject,
)

from .context import DemoContext

ER_EDGE_TYPE = "references"
REALIZES_EDGE_TYPE = "realizes"

# The single intentional Information gap: an optional attribute with no catalog
# realization. It is marked in its definition so the synthetic nature is clear.
INTENTIONAL_GAP_ATTRIBUTE = "preferred_contact_method"
INTENTIONAL_GAP_NOTE = "synthetic demo gap: intentionally unmapped optional attribute"

# Baseline attributes: created in Current (created_in_state_id=None) and reused
# by the candidate.
BASELINE_ATTRIBUTES: list[dict] = [
    {
        "name": "customer_id",
        "data_type": "string",
        "required": True,
        "nullable": False,
        "identifier": True,
        "key": True,
        "field": "crm.customer.customer_id",
    },
    {
        "name": "first_name",
        "data_type": "string",
        "required": True,
        "nullable": False,
        "identifier": False,
        "key": False,
        "field": "crm.customer.first_name",
    },
    {
        "name": "last_name",
        "data_type": "string",
        "required": True,
        "nullable": False,
        "identifier": False,
        "key": False,
        "field": "crm.customer.last_name",
    },
]

# Candidate-only attributes layered on top of the baseline.
CANDIDATE_ATTRIBUTES: list[dict] = [
    {
        "name": "email",
        "data_type": "string",
        "required": True,
        "nullable": False,
        "identifier": False,
        "key": True,
        "field": "crm.customer.email",
    },
    {
        "name": "status",
        "data_type": "string",
        "required": True,
        "nullable": False,
        "identifier": False,
        "key": False,
        "field": "crm.customer.status",
    },
    {
        "name": "consent",
        "data_type": "boolean",
        "required": False,
        "nullable": True,
        "identifier": False,
        "key": False,
        "field": "crm.customer.consent",
    },
    {
        "name": INTENTIONAL_GAP_ATTRIBUTE,
        "data_type": "string",
        "required": False,
        "nullable": True,
        "identifier": False,
        "key": False,
        "field": None,
        "definition": INTENTIONAL_GAP_NOTE,
    },
]

CONSENT_ATTRIBUTES: list[dict] = [
    {"name": "consent_type", "data_type": "string", "required": True, "nullable": False},
    {"name": "granted_at", "data_type": "datetime", "required": False, "nullable": True},
]


def _field_ref(
    db, ctx: DemoContext, attribute_id: UUID, field_key: str, created_in_state_id: UUID | None
) -> None:
    field = db.get(CatalogField, ctx.id(f"field.{field_key}"))
    if field is None:
        return
    ref_key = f"fieldref.{field_key}"
    db.add(
        ctx.registry(
            ref_key,
            "catalog_field_ref",
            catalog_field_id=field.id,
        )
    )
    db.add(
        ctx.relationship(
            f"realizes.{attribute_id}",
            attribute_id,
            ctx.id(ref_key),
            REALIZES_EDGE_TYPE,
            created_in_state_id=created_in_state_id,
        )
    )


def _add_attribute(
    db,
    ctx: DemoContext,
    *,
    key: str,
    entity_id: UUID,
    spec: dict,
    ordinal: int,
    created_in_state_id: UUID | None,
) -> UUID:
    attribute_id = ctx.id(key)
    db.add(ctx.registry(key, "information_attribute"))
    db.add(
        InformationAttribute(
            object_id=attribute_id,
            tenant_id=ctx.tenant_id,
            entity_object_id=entity_id,
            name=spec["name"],
            data_type=spec["data_type"],
            required=spec["required"],
            nullable=spec["nullable"],
            is_key=spec.get("key", False),
            is_identifier=spec.get("identifier", False),
            ordinal=ordinal,
            definition=spec.get("definition", f"{spec['name']} (synthetic demo)"),
            created_in_state_id=created_in_state_id,
            created_at=ctx.now,
            updated_at=ctx.now,
        )
    )
    field_key = spec.get("field")
    if field_key:
        _field_ref(db, ctx, attribute_id, field_key, created_in_state_id)
    return attribute_id


def build_information(db, ctx: DemoContext) -> None:
    now = ctx.now
    candidate = ctx.id("state.candidate")
    crm = ctx.id("system.crm")

    customer_id = ctx.id("info.customer")
    db.add(ctx.registry("info.customer", "information_object"))
    db.add(
        InformationObject(
            object_id=customer_id,
            tenant_id=ctx.tenant_id,
            name="Customer",
            description="Customer master data (synthetic demo).",
            owner="Customer Operations",
            steward="Data Steward",
            authoritative_system_id=crm,
            external_identifier="demo:info.customer",
            classification="internal",
            sensitivity="medium",
        )
    )
    # Customer is a reused baseline entity: it appears in Current and candidate.
    ctx.add_node(
        "current", "info.customer", customer_id, {"x": 900, "y": 60}, discipline="information"
    )
    ctx.add_node(
        "candidate", "info.customer", customer_id, {"x": 900, "y": 60}, discipline="information"
    )

    ordinal = 0
    for spec in BASELINE_ATTRIBUTES:
        _add_attribute(
            db,
            ctx,
            key=f"info.customer.{spec['name']}",
            entity_id=customer_id,
            spec=spec,
            ordinal=ordinal,
            created_in_state_id=None,
        )
        ordinal += 1
    for spec in CANDIDATE_ATTRIBUTES:
        _add_attribute(
            db,
            ctx,
            key=f"info.customer.{spec['name']}",
            entity_id=customer_id,
            spec=spec,
            ordinal=ordinal,
            created_in_state_id=candidate,
        )
        ordinal += 1

    consent_id = ctx.id("info.consent")
    db.add(ctx.registry("info.consent", "information_object"))
    db.add(
        InformationObject(
            object_id=consent_id,
            tenant_id=ctx.tenant_id,
            name="Customer Consent",
            description="Consent records (synthetic demo).",
            owner="Customer Operations",
            steward="Data Steward",
            authoritative_system_id=crm,
            external_identifier="demo:info.consent",
            classification="internal",
            sensitivity="medium",
        )
    )
    for index, spec in enumerate(CONSENT_ATTRIBUTES):
        _add_attribute(
            db,
            ctx,
            key=f"info.consent.{spec['name']}",
            entity_id=consent_id,
            spec=spec,
            ordinal=index,
            created_in_state_id=candidate,
        )

    db.add(
        ArchitectureRelationship(
            id=ctx.id("info.rel.customer.consent"),
            tenant_id=ctx.tenant_id,
            source_object_id=customer_id,
            target_object_id=consent_id,
            relationship_type=ER_EDGE_TYPE,
            properties={
                "name": "has consent",
                "cardinality": "one_to_many",
                "source_optional": False,
                "target_optional": True,
            },
            created_in_state_id=candidate,
            created_at=now,
            updated_at=now,
        )
    )
    ctx.record("relationship", ctx.id("info.rel.customer.consent"))

    ctx.add_node(
        "candidate", "info.consent", consent_id, {"x": 1220, "y": 60}, discipline="information"
    )
