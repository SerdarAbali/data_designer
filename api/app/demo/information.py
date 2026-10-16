"""Information module of the demo generator (customer data model)."""

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

# Logical attribute key -> (catalog field key, required, nullable, identifier, key)
ATTRIBUTES: list[dict] = [
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
]

CONSENT_ATTRIBUTES: list[dict] = [
    {"name": "consent_type", "data_type": "string", "required": True, "nullable": False},
    {"name": "granted_at", "data_type": "datetime", "required": False, "nullable": True},
]


def _field_ref(db, ctx: DemoContext, attribute_id: UUID, field_key: str) -> None:
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
            created_in_state_id=ctx.id("state.candidate"),
        )
    )


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

    for index, spec in enumerate(ATTRIBUTES):
        attribute_id = ctx.id(f"info.customer.{spec['name']}")
        db.add(ctx.registry(f"info.customer.{spec['name']}", "information_attribute"))
        db.add(
            InformationAttribute(
                object_id=attribute_id,
                tenant_id=ctx.tenant_id,
                entity_object_id=customer_id,
                name=spec["name"],
                data_type=spec["data_type"],
                required=spec["required"],
                nullable=spec["nullable"],
                is_key=spec["key"],
                is_identifier=spec["identifier"],
                ordinal=index,
                definition=f"{spec['name']} (synthetic demo)",
                created_in_state_id=candidate,
                created_at=now,
                updated_at=now,
            )
        )
        _field_ref(db, ctx, attribute_id, spec["field"])

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
        db.add(ctx.registry(f"info.consent.{spec['name']}", "information_attribute"))
        db.add(
            InformationAttribute(
                object_id=ctx.id(f"info.consent.{spec['name']}"),
                tenant_id=ctx.tenant_id,
                entity_object_id=consent_id,
                name=spec["name"],
                data_type=spec["data_type"],
                required=spec["required"],
                nullable=spec["nullable"],
                is_key=False,
                is_identifier=False,
                ordinal=index,
                definition=f"{spec['name']} (synthetic demo)",
                created_in_state_id=candidate,
                created_at=now,
                updated_at=now,
            )
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
        "candidate", "info.customer", customer_id, {"x": 900, "y": 60}, discipline="information"
    )
    ctx.add_node(
        "candidate", "info.consent", consent_id, {"x": 1220, "y": 60}, discipline="information"
    )
