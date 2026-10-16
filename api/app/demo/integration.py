"""Integration module of the demo generator (contracts, mappings, resilience)."""

from __future__ import annotations

from uuid import UUID

from app.models import Integration, IntegrationDependency, IntegrationFieldRef

from .context import DemoContext
from .solution import ensure_interfaces

REQUEST = "request"
RESPONSE = "response"
ERROR = "error"

DIRECTIONS = {
    REQUEST: ("source", "target"),
    RESPONSE: ("response_source", "response_target"),
    ERROR: ("error_response_source", "error_response_target"),
}


def _node(
    ctx: DemoContext, key: str, node_type: str, x: float, y: float, config: dict | None = None
) -> dict:
    return {
        "id": str(ctx.id(f"node.{key}")),
        "type": node_type,
        "position": {"x": x, "y": y},
        "config": config or {},
    }


def _edge(
    ctx: DemoContext, key: str, source: dict, port: str, target: dict, target_port: str
) -> dict:
    return {
        "id": str(ctx.id(f"edge.{key}")),
        "sourceNodeId": source["id"],
        "sourcePortId": port,
        "targetNodeId": target["id"],
        "targetPortId": target_port,
    }


def _field_port_id(ctx: DemoContext, field_key: str) -> str:
    return f"field:{ctx.id(f'field.{field_key}')}"


def _refs(
    graph: dict, source_object_id: UUID, target_object_id: UUID, phase: str
) -> set[tuple[UUID, str, UUID]]:
    source_dir, target_dir = DIRECTIONS[phase]
    source_node = next((n for n in graph["nodes"] if n["type"] == "source"), None)
    target_node = next((n for n in graph["nodes"] if n["type"] == "target"), None)
    refs: set[tuple[UUID, str, UUID]] = set()
    for edge in graph["edges"]:
        if source_node is not None and edge["sourceNodeId"] == source_node["id"]:
            port = edge["sourcePortId"]
            if port.startswith("field:"):
                refs.add((UUID(port.removeprefix("field:")), source_dir, source_object_id))
        if target_node is not None and edge["targetNodeId"] == target_node["id"]:
            port = edge["targetPortId"]
            if port.startswith("field:"):
                refs.add((UUID(port.removeprefix("field:")), target_dir, target_object_id))
    return refs


def _sample_rows(ctx: DemoContext) -> list[dict]:
    def row(
        row_id: str, customer_id: str, first: str, last: str, email: str, status: str, consent: bool
    ) -> dict:
        return {
            "rowId": row_id,
            "values": {
                str(ctx.id("field.crm.customer.customer_id")): customer_id,
                str(ctx.id("field.crm.customer.first_name")): first,
                str(ctx.id("field.crm.customer.last_name")): last,
                str(ctx.id("field.crm.customer.email")): email,
                str(ctx.id("field.crm.customer.status")): status,
                str(ctx.id("field.crm.customer.consent")): consent,
            },
        }

    return [
        row("row-1", "C-1001", "Ada", "Lovelace", "ada@example.test", "active", True),
        row("row-2", "C-1002", "Grace", "Hopper", "grace@example.test", "pending", False),
    ]


def _direct_contract(db, ctx: DemoContext) -> UUID:
    crm_object = ctx.id("object.crm.customer")
    billing_object = ctx.id("object.billing.billing_account")
    error_object = ctx.id("object.billing.integration_error")

    source = _node(ctx, "direct.req.source", "source", 0, 120)
    target = _node(ctx, "direct.req.target", "target", 480, 120)
    concat = _node(ctx, "direct.req.concat", "concat", 240, 120, {"separator": " "})
    request_graph = {
        "version": 1,
        "nodes": [source, target, concat],
        "edges": [
            _edge(
                ctx,
                "direct.req.e1",
                source,
                _field_port_id(ctx, "crm.customer.customer_id"),
                target,
                _field_port_id(ctx, "billing.billing_account.account_id"),
            ),
            _edge(
                ctx,
                "direct.req.e2",
                source,
                _field_port_id(ctx, "crm.customer.email"),
                target,
                _field_port_id(ctx, "billing.billing_account.email_address"),
            ),
            _edge(
                ctx,
                "direct.req.e3",
                source,
                _field_port_id(ctx, "crm.customer.status"),
                target,
                _field_port_id(ctx, "billing.billing_account.status"),
            ),
            _edge(
                ctx,
                "direct.req.e4",
                source,
                _field_port_id(ctx, "crm.customer.consent"),
                target,
                _field_port_id(ctx, "billing.billing_account.marketing_consent"),
            ),
            _edge(
                ctx,
                "direct.req.e5",
                source,
                _field_port_id(ctx, "crm.customer.customer_id"),
                target,
                _field_port_id(ctx, "billing.billing_account.customer_ref"),
            ),
            _edge(
                ctx,
                "direct.req.e6",
                source,
                _field_port_id(ctx, "crm.customer.first_name"),
                concat,
                "input",
            ),
            _edge(
                ctx,
                "direct.req.e7",
                source,
                _field_port_id(ctx, "crm.customer.last_name"),
                concat,
                "input",
            ),
            _edge(
                ctx,
                "direct.req.e8",
                concat,
                "output",
                target,
                _field_port_id(ctx, "billing.billing_account.full_name"),
            ),
        ],
    }

    r_source = _node(ctx, "direct.res.source", "source", 0, 120)
    r_target = _node(ctx, "direct.res.target", "target", 480, 120)
    response_graph = {
        "version": 1,
        "nodes": [r_source, r_target],
        "edges": [
            _edge(
                ctx,
                "direct.res.e1",
                r_source,
                _field_port_id(ctx, "billing.billing_account.account_id"),
                r_target,
                _field_port_id(ctx, "crm.customer.customer_id"),
            ),
            _edge(
                ctx,
                "direct.res.e2",
                r_source,
                _field_port_id(ctx, "billing.billing_account.status"),
                r_target,
                _field_port_id(ctx, "crm.customer.status"),
            ),
            _edge(
                ctx,
                "direct.res.e3",
                r_source,
                _field_port_id(ctx, "billing.billing_account.email_address"),
                r_target,
                _field_port_id(ctx, "crm.customer.email"),
            ),
            _edge(
                ctx,
                "direct.res.e4",
                r_source,
                _field_port_id(ctx, "billing.billing_account.marketing_consent"),
                r_target,
                _field_port_id(ctx, "crm.customer.consent"),
            ),
        ],
    }

    e_source = _node(ctx, "direct.err.source", "source", 0, 120)
    e_target = _node(ctx, "direct.err.target", "target", 480, 120)
    error_graph = {
        "version": 1,
        "nodes": [e_source, e_target],
        "edges": [
            _edge(
                ctx,
                "direct.err.e1",
                e_source,
                _field_port_id(ctx, "billing.integration_error.error_code"),
                e_target,
                _field_port_id(ctx, "crm.customer.customer_id"),
            ),
            _edge(
                ctx,
                "direct.err.e2",
                e_source,
                _field_port_id(ctx, "billing.integration_error.error_message"),
                e_target,
                _field_port_id(ctx, "crm.customer.status"),
            ),
        ],
    }

    contract_id = ctx.id("integration.direct")
    db.add(
        Integration(
            id=contract_id,
            tenant_id=ctx.tenant_id,
            source_system_id=ctx.id("system.crm"),
            source_object_id=crm_object,
            target_system_id=ctx.id("system.billing"),
            target_object_id=billing_object,
            name="Customer onboarding (direct)",
            description="Direct CRM to Billing onboarding contract (synthetic demo).",
            graph=request_graph,
            response_graph=response_graph,
            error_response_graph=error_graph,
            error_response_object_id=error_object,
            interaction_type="REQUEST_RESPONSE",
            pattern="request_reply",
            implementation_status="built",
            producer_interface_id=ctx.id("iface.onboarding_api"),
            consumer_interface_id=ctx.id("iface.billing_api"),
            specification={
                "retry": {"max_attempts": 3, "backoff": "exponential"},
                "timeout_ms": 5000,
                "idempotent": True,
                "idempotency_key_field_id": str(ctx.id("field.crm.customer.customer_id")),
                "security": {"auth_type": "oauth2", "notes": "mTLS between services"},
                "routing": "Route by region",
                "orchestration_role": "orchestration",
                "error_handling": "Retry then dead-letter",
            },
            sample_rows=_sample_rows(ctx),
            external_identifier="demo:integration.direct",
            extra_metadata={"demo": True},
            revision=1,
            created_at=ctx.now,
            updated_at=ctx.now,
        )
    )
    ctx.record("integration", contract_id)
    refs: set[tuple[UUID, str, UUID]] = set()
    refs |= _refs(request_graph, crm_object, billing_object, REQUEST)
    refs |= _refs(response_graph, billing_object, crm_object, RESPONSE)
    refs |= _refs(error_graph, error_object, crm_object, ERROR)
    refs |= {
        (UUID(str(ctx.id("field.crm.customer." + name))), "source", crm_object)
        for name in ("customer_id", "first_name", "last_name", "email", "status", "consent")
    }
    for field_id, direction, object_id in refs:
        db.add(
            IntegrationFieldRef(
                id=ctx.id(f"ref.{contract_id}.{field_id}.{direction}"),
                tenant_id=ctx.tenant_id,
                integration_id=contract_id,
                object_id=object_id,
                field_id=field_id,
                direction=direction,
            )
        )
    return contract_id


def _event_contract(db, ctx: DemoContext) -> UUID:
    crm_object = ctx.id("object.crm.customer")
    runtime_object = ctx.id("object.integration_runtime.customer_event")

    source = _node(ctx, "event.req.source", "source", 0, 120)
    target = _node(ctx, "event.req.target", "target", 480, 120)
    upper = _node(ctx, "event.req.upper", "fx", 240, 120, {"function": "upper"})
    request_graph = {
        "version": 1,
        "nodes": [source, target, upper],
        "edges": [
            _edge(
                ctx,
                "event.req.e1",
                source,
                _field_port_id(ctx, "crm.customer.customer_id"),
                target,
                _field_port_id(ctx, "integration_runtime.customer_event.event_id"),
            ),
            _edge(
                ctx,
                "event.req.e2",
                source,
                _field_port_id(ctx, "crm.customer.email"),
                target,
                _field_port_id(ctx, "integration_runtime.customer_event.payload"),
            ),
            _edge(
                ctx,
                "event.req.e3",
                source,
                _field_port_id(ctx, "crm.customer.status"),
                upper,
                "input",
            ),
            _edge(
                ctx,
                "event.req.e4",
                upper,
                "output",
                target,
                _field_port_id(ctx, "integration_runtime.customer_event.event_type"),
            ),
        ],
    }

    r_source = _node(ctx, "event.res.source", "source", 0, 120)
    r_target = _node(ctx, "event.res.target", "target", 480, 120)
    response_graph = {
        "version": 1,
        "nodes": [r_source, r_target],
        "edges": [
            _edge(
                ctx,
                "event.res.e1",
                r_source,
                _field_port_id(ctx, "integration_runtime.customer_event.event_id"),
                r_target,
                _field_port_id(ctx, "crm.customer.customer_id"),
            ),
            _edge(
                ctx,
                "event.res.e2",
                r_source,
                _field_port_id(ctx, "integration_runtime.customer_event.event_type"),
                r_target,
                _field_port_id(ctx, "crm.customer.status"),
            ),
        ],
    }

    contract_id = ctx.id("integration.event")
    db.add(
        Integration(
            id=contract_id,
            tenant_id=ctx.tenant_id,
            source_system_id=ctx.id("system.crm"),
            source_object_id=crm_object,
            target_system_id=ctx.id("system.integration_runtime"),
            target_object_id=runtime_object,
            name="Customer onboarding (event)",
            description=(
                "Event-driven onboarding mediated by the Integration Runtime (synthetic demo)."
            ),
            graph=request_graph,
            response_graph=response_graph,
            error_response_graph={"version": 1, "nodes": [], "edges": []},
            error_response_object_id=None,
            interaction_type="ASYNC_CALLBACK",
            pattern="publish_subscribe",
            implementation_status="built",
            producer_interface_id=ctx.id("iface.customer_event"),
            consumer_interface_id=None,
            specification={
                "retry": {"max_attempts": 5, "backoff": "linear"},
                "timeout_ms": 10000,
                "idempotent": True,
                "idempotency_key_field_id": str(ctx.id("field.crm.customer.customer_id")),
                "security": {"auth_type": "mtls", "notes": "Runtime broker credentials"},
                "routing": "Runtime topic per region",
                "orchestration_role": "choreography",
                "error_handling": "Dead-letter after retries",
            },
            sample_rows=_sample_rows(ctx),
            external_identifier="demo:integration.event",
            extra_metadata={"demo": True},
            revision=1,
            created_at=ctx.now,
            updated_at=ctx.now,
        )
    )
    ctx.record("integration", contract_id)
    refs: set[tuple[UUID, str, UUID]] = set()
    refs |= _refs(request_graph, crm_object, runtime_object, REQUEST)
    refs |= _refs(response_graph, runtime_object, crm_object, RESPONSE)
    refs |= {
        (UUID(str(ctx.id("field.crm.customer." + name))), "source", crm_object)
        for name in ("customer_id", "first_name", "last_name", "email", "status", "consent")
    }
    for field_id, direction, object_id in refs:
        db.add(
            IntegrationFieldRef(
                id=ctx.id(f"ref.{contract_id}.{field_id}.{direction}"),
                tenant_id=ctx.tenant_id,
                integration_id=contract_id,
                object_id=object_id,
                field_id=field_id,
                direction=direction,
            )
        )
    return contract_id


def _legacy_contract(db, ctx: DemoContext) -> UUID:
    contract_id = ctx.id("integration.legacy")
    db.add(
        Integration(
            id=contract_id,
            tenant_id=ctx.tenant_id,
            source_system_id=ctx.id("system.crm"),
            source_object_id=ctx.id("object.crm.customer"),
            target_system_id=ctx.id("system.billing"),
            target_object_id=ctx.id("object.billing.billing_account"),
            name="Legacy customer export",
            description=(
                "Existing manual/basic integration from the current state (synthetic demo)."
            ),
            graph={"version": 1, "nodes": [], "edges": []},
            response_graph={"version": 1, "nodes": [], "edges": []},
            error_response_graph={"version": 1, "nodes": [], "edges": []},
            error_response_object_id=None,
            interaction_type="ONE_WAY",
            pattern="file_transfer",
            implementation_status="draft",
            specification={"error_handling": "Manual re-key on failure"},
            sample_rows=[],
            external_identifier="demo:integration.legacy",
            extra_metadata={"demo": True},
            revision=1,
            created_at=ctx.now,
            updated_at=ctx.now,
        )
    )
    ctx.record("integration", contract_id)
    return contract_id


def build_integration(db, ctx: DemoContext) -> None:
    ensure_interfaces(db, ctx, with_components=ctx.has("solution"))
    db.flush()
    direct_id = _direct_contract(db, ctx)
    event_id = _event_contract(db, ctx)
    legacy_id = _legacy_contract(db, ctx)
    db.add(
        IntegrationDependency(
            id=ctx.id("dependency.legacy.direct"),
            tenant_id=ctx.tenant_id,
            upstream_integration_id=legacy_id,
            downstream_integration_id=direct_id,
            created_at=ctx.now,
        )
    )
    db.flush()
    # Current state tells the "existing/manual" story; candidate adds the event flow.
    # The relationship type is shown on the canvas as "<type> · <contract>", so it
    # reflects how the contract moves data rather than a blanket "Consumes".
    ctx.add_state_relationship(
        "current",
        "current.legacy",
        ctx.id("system.crm"),
        ctx.id("system.billing"),
        "Uses",
        name="Legacy customer export",
        integration_id=legacy_id,
    )
    ctx.add_state_relationship(
        "candidate",
        "candidate.direct",
        ctx.id("system.crm"),
        ctx.id("system.billing"),
        "Uses",
        name="Customer onboarding (direct)",
        integration_id=direct_id,
    )
    ctx.add_state_relationship(
        "candidate",
        "candidate.event",
        ctx.id("system.crm"),
        ctx.id("system.integration_runtime"),
        "Publishes",
        name="Customer onboarding (event)",
        integration_id=event_id,
    )
