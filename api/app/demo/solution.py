"""Solution module of the demo generator (components, interfaces, operations)."""

from __future__ import annotations

from app.models import (
    ArchitectureInterface,
    DataRepository,
    InterfaceOperation,
    SolutionBoundary,
    SolutionComponent,
    SolutionMember,
)

from .context import DemoContext

COMPONENTS: list[dict] = [
    {
        "key": "solution.component.portal",
        "name": "Customer Portal",
        "type": "application",
        "technology": "React",
        "responsibility": "Capture customer details and consent.",
        "position": {"x": 120, "y": 520},
    },
    {
        "key": "solution.component.onboarding",
        "name": "Onboarding Service",
        "type": "service",
        "technology": "Java",
        "responsibility": "Orchestrate verification, activation and billing setup.",
        "position": {"x": 460, "y": 520},
    },
    {
        "key": "solution.component.connector",
        "name": "Integration Connector",
        "type": "service",
        "technology": "Go",
        "responsibility": "Publish customer events to the Integration Runtime.",
        "position": {"x": 800, "y": 520},
    },
]

INTERFACES: list[dict] = [
    {
        "key": "iface.onboarding_api",
        "component": "solution.component.onboarding",
        "name": "Onboarding API",
        "direction": "provided",
        "kind": "sync",
        "protocol": "HTTPS",
        "technology": "REST",
    },
    {
        "key": "iface.billing_api",
        "component": "solution.component.onboarding",
        "name": "Billing API",
        "direction": "required",
        "kind": "sync",
        "protocol": "HTTPS",
        "technology": "REST",
    },
    {
        "key": "iface.customer_event",
        "component": "solution.component.connector",
        "name": "Customer Event",
        "direction": "provided",
        "kind": "async",
        "protocol": "AMQP",
        "technology": "RabbitMQ",
    },
]

OPERATIONS: list[dict] = [
    {
        "key": "op.create_customer",
        "interface": "iface.onboarding_api",
        "name": "createCustomer",
        "kind": "operation",
    },
    {
        "key": "op.customer_created",
        "interface": "iface.customer_event",
        "name": "customerCreated",
        "kind": "event",
    },
]


def ensure_interfaces(db, ctx: DemoContext, *, with_components: bool) -> None:
    """Create interfaces/operations once. Standalone when Solution is disabled."""
    now = ctx.now
    candidate = ctx.id("state.candidate")
    new_interfaces = [spec for spec in INTERFACES if spec["key"] not in ctx.ids]
    new_operations = [spec for spec in OPERATIONS if spec["key"] not in ctx.ids]
    for spec in new_interfaces:
        db.add(ctx.registry(spec["key"], "interface"))
    for spec in new_operations:
        db.add(ctx.registry(spec["key"], "interface_operation"))
    db.flush()
    for spec in new_interfaces:
        component_id = ctx.id(spec["component"]) if with_components else None
        db.add(
            ArchitectureInterface(
                object_id=ctx.id(spec["key"]),
                tenant_id=ctx.tenant_id,
                name=spec["name"],
                description=f"{spec['name']} (synthetic demo)",
                component_object_id=component_id,
                direction=spec["direction"],
                interface_kind=spec["kind"],
                protocol=spec["protocol"],
                technology=spec["technology"],
                created_in_state_id=candidate,
            )
        )
    db.flush()
    for spec in new_operations:
        db.add(
            InterfaceOperation(
                object_id=ctx.id(spec["key"]),
                tenant_id=ctx.tenant_id,
                interface_object_id=ctx.id(spec["interface"]),
                name=spec["name"],
                description=f"{spec['name']} (synthetic demo)",
                operation_kind=spec["kind"],
                ordinal=0,
                created_in_state_id=candidate,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def build_solution(db, ctx: DemoContext) -> None:
    now = ctx.now
    candidate = ctx.id("state.candidate")
    solution_id = ctx.id("solution.onboarding")

    db.add(ctx.registry("solution.onboarding", "solution_boundary"))
    db.add(
        SolutionBoundary(
            object_id=solution_id,
            tenant_id=ctx.tenant_id,
            name="Customer Onboarding",
            description="Improved onboarding solution (synthetic demo).",
            owner="Customer Operations",
            external_identifier="demo:solution.onboarding",
        )
    )
    ctx.add_node(
        "candidate",
        "solution.onboarding",
        solution_id,
        {"x": 120, "y": 300},
        discipline="solution",
        width=1180.0,
        height=520.0,
    )

    for key in ("crm", "billing", "integration_runtime"):
        db.add(
            SolutionMember(
                id=ctx.id(f"solution.member.{key}"),
                tenant_id=ctx.tenant_id,
                solution_object_id=solution_id,
                system_id=ctx.id(f"system.{key}"),
                created_in_state_id=candidate,
                created_at=now,
            )
        )
        # The member system appears on the solution canvas too.
        ctx.add_node(
            "candidate",
            f"solution.system.{key}",
            ctx.id(f"system.{key}"),
            {"x": 120 + 300 * list(SYSTEM_ORDER).index(key), "y": 60},
            discipline="solution",
        )

    for spec in COMPONENTS:
        db.add(ctx.registry(spec["key"], "component"))
        db.add(
            SolutionComponent(
                object_id=ctx.id(spec["key"]),
                tenant_id=ctx.tenant_id,
                solution_object_id=solution_id,
                parent_component_object_id=None,
                name=spec["name"],
                description=f"{spec['name']} (synthetic demo)",
                responsibility=spec["responsibility"],
                component_type=spec["type"],
                technology=spec["technology"],
                created_in_state_id=candidate,
            )
        )
        ctx.add_node(
            "candidate", spec["key"], ctx.id(spec["key"]), spec["position"], discipline="solution"
        )

    db.flush()
    ensure_interfaces(db, ctx, with_components=True)

    db.add(ctx.registry("solution.repository.customer_store", "data_repository"))
    db.add(
        DataRepository(
            object_id=ctx.id("solution.repository.customer_store"),
            tenant_id=ctx.tenant_id,
            solution_object_id=solution_id,
            name="Customer Store",
            description="Canonical customer records (synthetic demo).",
            owner="Customer Operations",
            repository_type="relational",
            technology="PostgreSQL",
            properties={},
            created_in_state_id=candidate,
            created_at=now,
            updated_at=now,
        )
    )

    db.add_all(
        [
            ctx.relationship(
                "sol.link.solution.portal",
                solution_id,
                ctx.id("solution.component.portal"),
                "contains_component",
            ),
            ctx.relationship(
                "sol.link.solution.onboarding",
                solution_id,
                ctx.id("solution.component.onboarding"),
                "contains_component",
            ),
            ctx.relationship(
                "sol.link.solution.connector",
                solution_id,
                ctx.id("solution.component.connector"),
                "contains_component",
            ),
            ctx.relationship(
                "sol.link.onboarding.api",
                ctx.id("solution.component.onboarding"),
                ctx.id("iface.onboarding_api"),
                "provides",
            ),
            ctx.relationship(
                "sol.link.onboarding.billing",
                ctx.id("solution.component.onboarding"),
                ctx.id("iface.billing_api"),
                "requires",
            ),
            ctx.relationship(
                "sol.link.connector.event",
                ctx.id("solution.component.connector"),
                ctx.id("iface.customer_event"),
                "provides",
            ),
            ctx.relationship(
                "sol.link.api.create",
                ctx.id("iface.onboarding_api"),
                ctx.id("op.create_customer"),
                "has_operation",
            ),
            ctx.relationship(
                "sol.link.event.created",
                ctx.id("iface.customer_event"),
                ctx.id("op.customer_created"),
                "has_operation",
            ),
            ctx.relationship(
                "sol.link.api.store",
                ctx.id("iface.onboarding_api"),
                ctx.id("solution.repository.customer_store"),
                "uses_repository",
            ),
        ]
    )


SYSTEM_ORDER = ("crm", "billing", "integration_runtime")
