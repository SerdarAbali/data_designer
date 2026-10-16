"""Scenario/test content for the demo integration contracts."""

from __future__ import annotations

from app.models import Scenario

from .context import DemoContext


def _document(
    ctx: DemoContext,
    *,
    contract_id,
    phase,
    sample,
    expected,
    preconditions,
    trigger,
    notes,
    assertion_field,
    assertion_text,
):
    return {
        "version": 1,
        "preconditions": preconditions,
        "trigger": trigger,
        "participants": [
            {"id": "crm", "kind": "system", "systemId": str(ctx.id("system.crm"))},
            {"id": "billing", "kind": "system", "systemId": str(ctx.id("system.billing"))},
        ],
        "contractIds": [str(contract_id)],
        "beforeState": [],
        "afterState": [],
        "items": [
            {
                "id": "step-1",
                "kind": "contract",
                "contractId": str(contract_id),
                "phase": phase,
                "sampleValues": sample,
                "expectedValues": expected,
            }
        ],
        "assertions": [
            {
                "id": "assert-1",
                "text": assertion_text,
                "stepId": "step-1",
                "fieldId": str(assertion_field),
                "expected": list(expected.values())[0],
            }
        ],
        "notes": notes,
    }


def build_scenarios(db, ctx: DemoContext) -> None:
    direct_id = ctx.id("integration.direct")

    first_name = ctx.id("field.crm.customer.first_name")
    last_name = ctx.id("field.crm.customer.last_name")
    full_name = ctx.id("field.billing.billing_account.full_name")
    error_code = ctx.id("field.billing.integration_error.error_code")
    customer_id = ctx.id("field.crm.customer.customer_id")

    scenarios = [
        {
            "key": "scenario.happy",
            "name": "Onboarding happy path",
            "category": "happy_path",
            "description": "Customer details map to a billing account (synthetic demo).",
            "document": _document(
                ctx,
                contract_id=direct_id,
                phase="request",
                sample={str(first_name): "Ada", str(last_name): "Lovelace"},
                expected={str(full_name): "Ada Lovelace"},
                preconditions="Candidate state with the direct onboarding contract.",
                trigger="A customer submits the onboarding form.",
                notes="Synthetic demo content.",
                assertion_field=full_name,
                assertion_text="The full name is composed from the customer's first and last name.",
            ),
        },
        {
            "key": "scenario.error",
            "name": "Onboarding error response",
            "category": "error",
            "description": "Billing errors propagate back to the customer record (synthetic demo).",
            "document": _document(
                ctx,
                contract_id=direct_id,
                phase="error-response",
                sample={str(error_code): "E402"},
                expected={str(customer_id): "E402"},
                preconditions="Candidate state with the direct onboarding contract.",
                trigger="Billing rejects the onboarding request.",
                notes="Synthetic demo content.",
                assertion_field=customer_id,
                assertion_text="The billing error code is recorded against the customer.",
            ),
        },
        {
            "key": "scenario.unresolved",
            "name": "Demo: unresolved name review (demo content)",
            "category": "error",
            "description": (
                "Intentional failing demo scenario that needs a human decision (synthetic demo)."
            ),
            "document": _document(
                ctx,
                contract_id=direct_id,
                phase="request",
                sample={str(first_name): "Ada", str(last_name): "Lovelace"},
                expected={str(full_name): "Ada Lovelace (pending review)"},
                preconditions="Candidate state with the direct onboarding contract.",
                trigger="A customer name needs manual review.",
                notes=(
                    "Demo content: this scenario is expected to fail until the mapping is agreed."
                ),
                assertion_field=full_name,
                assertion_text="The reviewed name has not been agreed yet.",
            ),
        },
    ]

    for spec in scenarios:
        row_id = ctx.id(spec["key"])
        db.add(
            Scenario(
                id=row_id,
                tenant_id=ctx.tenant_id,
                scope_integration_id=direct_id,
                name=spec["name"],
                category=spec["category"],
                description=spec["description"],
                document=spec["document"],
                revision=1,
                created_at=ctx.now,
                updated_at=ctx.now,
            )
        )
        ctx.record("scenario", row_id)
    db.flush()
