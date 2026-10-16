"""Canonical catalog content for the demo workspace.

Catalog systems, objects, and fields are created once per workspace and reused
by every discipline. Names and identifiers are deterministic so repeated
generation cannot duplicate them.
"""

from __future__ import annotations

from app.models import CatalogField, CatalogObject, CatalogSystem

from .context import DEMO_ORIGIN, DemoContext

# Logical key -> definition. Keys are stable and drive deterministic UUIDs.
SYSTEMS: dict[str, dict] = {
    "crm": {"name": "CRM", "kind": "application", "color": "#527ca4"},
    "billing": {"name": "Billing", "kind": "application", "color": "#8a6fb0"},
    "integration_runtime": {
        "name": "Integration Runtime",
        "kind": "middleware",
        "color": "#529c8a",
    },
}

OBJECTS: dict[str, dict] = {
    "crm.customer": {"system": "crm", "name": "customer", "label": "Customer"},
    "billing.billing_account": {
        "system": "billing",
        "name": "billing_account",
        "label": "Billing Account",
    },
    "billing.integration_error": {
        "system": "billing",
        "name": "integration_error",
        "label": "Integration Error",
    },
    "integration_runtime.customer_event": {
        "system": "integration_runtime",
        "name": "customer_event",
        "label": "Customer Event",
    },
}

FIELDS: dict[str, dict] = {
    "crm.customer.customer_id": {
        "object": "crm.customer",
        "name": "customer_id",
        "data_type": "string",
        "required": True,
        "nullable": False,
    },
    "crm.customer.first_name": {
        "object": "crm.customer",
        "name": "first_name",
        "data_type": "string",
    },
    "crm.customer.last_name": {
        "object": "crm.customer",
        "name": "last_name",
        "data_type": "string",
    },
    "crm.customer.email": {"object": "crm.customer", "name": "email", "data_type": "string"},
    "crm.customer.status": {"object": "crm.customer", "name": "status", "data_type": "string"},
    "crm.customer.consent": {"object": "crm.customer", "name": "consent", "data_type": "boolean"},
    "crm.customer.phone": {"object": "crm.customer", "name": "phone", "data_type": "string"},
    "billing.billing_account.account_id": {
        "object": "billing.billing_account",
        "name": "account_id",
        "data_type": "string",
    },
    "billing.billing_account.customer_ref": {
        "object": "billing.billing_account",
        "name": "customer_ref",
        "data_type": "string",
    },
    "billing.billing_account.full_name": {
        "object": "billing.billing_account",
        "name": "full_name",
        "data_type": "string",
    },
    "billing.billing_account.email_address": {
        "object": "billing.billing_account",
        "name": "email_address",
        "data_type": "string",
    },
    "billing.billing_account.status": {
        "object": "billing.billing_account",
        "name": "status",
        "data_type": "string",
    },
    "billing.billing_account.marketing_consent": {
        "object": "billing.billing_account",
        "name": "marketing_consent",
        "data_type": "boolean",
    },
    "billing.integration_error.error_code": {
        "object": "billing.integration_error",
        "name": "error_code",
        "data_type": "string",
    },
    "billing.integration_error.error_message": {
        "object": "billing.integration_error",
        "name": "error_message",
        "data_type": "string",
    },
    "integration_runtime.customer_event.event_id": {
        "object": "integration_runtime.customer_event",
        "name": "event_id",
        "data_type": "string",
    },
    "integration_runtime.customer_event.event_type": {
        "object": "integration_runtime.customer_event",
        "name": "event_type",
        "data_type": "string",
    },
    "integration_runtime.customer_event.payload": {
        "object": "integration_runtime.customer_event",
        "name": "payload",
        "data_type": "string",
    },
    "integration_runtime.customer_event.occurred_at": {
        "object": "integration_runtime.customer_event",
        "name": "occurred_at",
        "data_type": "datetime",
    },
}


def build_catalog(db, ctx: DemoContext) -> None:
    now = ctx.now
    for key, spec in SYSTEMS.items():
        system = CatalogSystem(
            id=ctx.id(f"system.{key}"),
            tenant_id=ctx.tenant_id,
            name=spec["name"],
            description=f"{spec['name']} system (synthetic demo)",
            kind=spec["kind"],
            color=spec.get("color"),
            external_identifier=f"demo:{key}",
            binding_state="unbound",
            extra_metadata={"demo": True, "origin": DEMO_ORIGIN},
            created_at=now,
            updated_at=now,
        )
        db.add(system)
        ctx.record("catalog_system", system.id)
        # The model listener registers an ArchitectureObject with the system id.
        ctx.record("architecture_object", system.id)
    db.flush()

    for key, spec in OBJECTS.items():
        obj = CatalogObject(
            id=ctx.id(f"object.{key}"),
            tenant_id=ctx.tenant_id,
            system_id=ctx.id(f"system.{spec['system']}"),
            name=spec["name"],
            label=spec["label"],
            description=f"{spec['label']} (synthetic demo)",
            external_identifier=f"demo:{key}",
            origin=DEMO_ORIGIN,
            position=list(OBJECTS).index(key) + 1,
            extra_metadata={"demo": True},
            created_at=now,
            updated_at=now,
        )
        db.add(obj)
        ctx.record("catalog_object", obj.id)
    db.flush()

    for index, (key, spec) in enumerate(FIELDS.items()):
        field = CatalogField(
            id=ctx.id(f"field.{key}"),
            tenant_id=ctx.tenant_id,
            object_id=ctx.id(f"object.{spec['object']}"),
            name=spec["name"],
            label=spec["name"].replace("_", " ").title(),
            data_type=spec["data_type"],
            required=bool(spec.get("required", False)),
            nullable=bool(spec.get("nullable", True)),
            external_identifier=f"demo:{key}",
            origin=DEMO_ORIGIN,
            position=index + 1,
            extra_metadata={"demo": True},
            created_at=now,
            updated_at=now,
        )
        db.add(field)
        ctx.record("catalog_field", field.id)
    db.flush()
