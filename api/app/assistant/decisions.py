"""Closed structured unresolved-decision descriptors.

The assistant never invents free-form decisions. Every descriptor uses one of a
small closed set of decision types, is derived deterministically from an existing
unresolved operation, and carries only bounded, typed options. There is no
generic "arbitrary value" decision type.
"""

from __future__ import annotations

from typing import Any

from app.models import HelperChangeOperation, HelperChangeSet

CLOSED_DECISION_KINDS = (
    "choose_catalog_field",
    "choose_canonical_object",
    "create_new_architecture_object",
    "choose_integration_pattern",
    "choose_runtime",
    "choose_contract_intent",
    "choose_cardinality",
    "choose_owner_or_steward",
    "choose_interface_direction",
    "choose_evidence",
    "confirm_or_remove_operation",
)

MAX_DESCRIPTORS = 20
MAX_OPTIONS = 12

_QUESTION_BY_KIND = {
    "choose_catalog_field": "Which Catalog field should realize this?",
    "choose_canonical_object": "Which existing canonical object should be reused?",
    "create_new_architecture_object": "Create a new architecture object for this?",
    "choose_integration_pattern": "Which integration pattern should be used?",
    "choose_runtime": "Which runtime system should mediate this integration?",
    "choose_contract_intent": "How should this Contract relate to the existing one?",
    "choose_cardinality": "What cardinality should this relationship have?",
    "choose_owner_or_steward": "Who owns or stewards this?",
    "choose_interface_direction": "Is this interface required or provided?",
    "choose_evidence": "Which modeled interface/operation supports this interaction?",
    "confirm_or_remove_operation": "Confirm or remove this proposed operation?",
}


def _kind_for(operation: HelperChangeOperation) -> str:
    action = operation.domain_action
    proposed = operation.proposed_value or {}
    if action == "set_realization":
        return "choose_catalog_field"
    if action == "include_object":
        return "choose_canonical_object"
    if action == "create_object":
        return "create_new_architecture_object"
    if action == "create_mapping":
        return "choose_catalog_field"
    if action == "create_contract":
        if proposed.get("based_on_contract_id") or proposed.get("proposal_intent"):
            return "choose_contract_intent"
        return "confirm_or_remove_operation"
    if action == "configure_resilience":
        return "choose_contract_intent"
    if action in {"create_link", "record_interaction"}:
        if proposed.get("relationship_type") and proposed.get("cardinality") is None:
            return "choose_cardinality"
        return "choose_evidence"
    return "confirm_or_remove_operation"


def _options(operation: HelperChangeOperation, kind: str) -> list[dict[str, Any]]:
    proposed = operation.proposed_value or {}
    candidates = proposed.get("candidates")
    options: list[dict[str, Any]] = []
    if isinstance(candidates, list):
        for item in candidates[:MAX_OPTIONS]:
            if isinstance(item, dict):
                options.append(
                    {
                        "key": str(item.get("key") or item.get("id") or "")[:120],
                        "label": str(item.get("label") or item.get("name") or "")[:160],
                        "object_id": item.get("object_id"),
                    }
                )
    if not options and kind == "confirm_or_remove_operation":
        options = [{"key": "confirm", "label": "Keep this operation"}]
    return options


def derive_unresolved_details(
    change_set: HelperChangeSet, operations: list[HelperChangeOperation]
) -> list[dict[str, Any]]:
    """Deterministic closed descriptors for every unresolved active operation."""
    details: list[dict[str, Any]] = []
    for operation in operations:
        if getattr(operation, "resolution_state", "active") != "active":
            continue
        proposed = operation.proposed_value or {}
        if not proposed.get("unresolved"):
            continue
        kind = _kind_for(operation)
        if kind not in CLOSED_DECISION_KINDS:
            kind = "confirm_or_remove_operation"
        reason = str(proposed.get("reason") or _QUESTION_BY_KIND[kind])[:300]
        details.append(
            {
                "decision_id": f"decision:{operation.operation_id}:{kind}",
                "operation_id": operation.operation_id,
                "kind": kind,
                "question": _QUESTION_BY_KIND[kind],
                "explanation": reason,
                "options": _options(operation, kind),
                "required": bool(proposed.get("required_for_approval", True)),
                "affected_operation_ids": [operation.operation_id],
                "resolution_state": "open",
            }
        )
        if len(details) >= MAX_DESCRIPTORS:
            break
    return details
