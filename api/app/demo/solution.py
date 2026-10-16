"""Solution module of the demo generator (components, interfaces, operations)."""

from __future__ import annotations

from app.models import (
    ArchitectureInterface,
    DataRepository,
    DeploymentNode,
    InterfaceOperation,
    SolutionBoundary,
    SolutionComponent,
    SolutionMember,
    TrustBoundary,
)

from .context import DemoContext

COMPONENTS: list[dict] = [
    {
        "key": "solution.component.portal",
        "name": "Customer Portal",
        "type": "application",
        "technology": "React",
        "responsibility": "Capture customer details and consent.",
        "position": {"x": 120, "y": 220},
    },
    {
        "key": "solution.component.onboarding",
        "name": "Onboarding Service",
        "type": "service",
        "technology": "Java",
        "responsibility": "Orchestrate verification, activation and billing setup.",
        "position": {"x": 460, "y": 220},
    },
    {
        "key": "solution.component.connector",
        "name": "Integration Connector",
        "type": "service",
        "technology": "Go",
        "responsibility": "Publish customer events to the Integration Runtime.",
        "position": {"x": 800, "y": 220},
    },
    {
        "key": "solution.component.billing_adapter",
        "name": "Billing Adapter",
        "type": "service",
        "technology": "Java",
        "responsibility": "Translate onboarding requests into billing operations.",
        "position": {"x": 1140, "y": 220},
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
        "key": "iface.portal_onboarding_api",
        "component": "solution.component.portal",
        "name": "Onboarding API",
        "direction": "required",
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
        "key": "iface.billing_provided_api",
        "component": "solution.component.billing_adapter",
        "name": "Billing API",
        "direction": "provided",
        "kind": "sync",
        "protocol": "HTTPS",
        "technology": "REST",
    },
    {
        "key": "iface.customer_event",
        "component": "solution.component.connector",
        "name": "Customer Event Stream",
        "direction": "provided",
        "kind": "async",
        "protocol": "AMQP",
        "technology": "RabbitMQ",
    },
    {
        "key": "iface.onboarding_customer_event",
        "component": "solution.component.onboarding",
        "name": "Customer Event",
        "direction": "provided",
        "kind": "async",
        "protocol": "AMQP",
        "technology": "RabbitMQ",
    },
    {
        "key": "iface.connector_customer_event",
        "component": "solution.component.connector",
        "name": "Customer Event",
        "direction": "required",
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

DEPLOYMENTS: list[dict] = [
    {
        "key": "solution.deployment.web",
        "name": "Public Web Tier",
        "environment": "production",
        "hosting": "container",
        "technology": "NGINX",
        "description": "Internet-facing hosting for the customer portal (synthetic demo).",
    },
    {
        "key": "solution.deployment.services",
        "name": "Core Services",
        "environment": "production",
        "hosting": "container",
        "technology": "Kubernetes",
        "description": "Internal service cluster for onboarding and integration (synthetic demo).",
    },
]

TRUST_BOUNDARIES: list[dict] = [
    {
        "key": "solution.trust.public",
        "name": "Public Network",
        "security_level": "public",
        "description": "Untrusted internet-facing zone (synthetic demo).",
    },
    {
        "key": "solution.trust.internal",
        "name": "Internal Network",
        "security_level": "internal",
        "description": "Restricted internal service zone (synthetic demo).",
    },
]

# component -> deployment key and component -> trust boundary key
COMPONENT_DEPLOYMENT: dict[str, str] = {
    "solution.component.portal": "solution.deployment.web",
    "solution.component.onboarding": "solution.deployment.services",
    "solution.component.connector": "solution.deployment.services",
    "solution.component.billing_adapter": "solution.deployment.services",
}

COMPONENT_TRUST: dict[str, str] = {
    "solution.component.portal": "solution.trust.public",
    "solution.component.onboarding": "solution.trust.internal",
    "solution.component.connector": "solution.trust.internal",
    "solution.component.billing_adapter": "solution.trust.internal",
}

# interface -> trust boundary it crosses
INTERFACE_TRUST: dict[str, str] = {
    "iface.portal_onboarding_api": "solution.trust.public",
    "iface.onboarding_api": "solution.trust.internal",
    "iface.billing_api": "solution.trust.internal",
    "iface.billing_provided_api": "solution.trust.internal",
    "iface.onboarding_customer_event": "solution.trust.internal",
    "iface.connector_customer_event": "solution.trust.internal",
    "iface.customer_event": "solution.trust.internal",
}

# (required interface, provided interface) pairs that compose the solution flow.
CONNECTS_TO: list[tuple[str, str]] = [
    ("iface.portal_onboarding_api", "iface.onboarding_api"),
    ("iface.billing_api", "iface.billing_provided_api"),
    ("iface.connector_customer_event", "iface.onboarding_customer_event"),
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
        {"x": 60, "y": 40},
        discipline="solution",
        width=1000.0,
        height=460.0,
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
            {"x": 120 + 300 * list(SYSTEM_ORDER).index(key), "y": 80},
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

    deployment_rows = [ctx.registry(spec["key"], "deployment_node") for spec in DEPLOYMENTS]
    trust_rows = [ctx.registry(spec["key"], "trust_boundary") for spec in TRUST_BOUNDARIES]
    db.add_all(deployment_rows)
    db.add_all(trust_rows)
    for spec in DEPLOYMENTS:
        db.add(
            DeploymentNode(
                object_id=ctx.id(spec["key"]),
                tenant_id=ctx.tenant_id,
                solution_object_id=solution_id,
                name=spec["name"],
                description=spec["description"],
                technology=spec["technology"],
                environment=spec["environment"],
                hosting=spec["hosting"],
                properties={},
                created_in_state_id=candidate,
                created_at=now,
                updated_at=now,
            )
        )
    for spec in TRUST_BOUNDARIES:
        db.add(
            TrustBoundary(
                object_id=ctx.id(spec["key"]),
                tenant_id=ctx.tenant_id,
                solution_object_id=solution_id,
                name=spec["name"],
                description=spec["description"],
                security_level=spec["security_level"],
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

    platform_links = []
    for component_key, deployment_key in COMPONENT_DEPLOYMENT.items():
        platform_links.append(
            ctx.relationship(
                f"sol.link.deploy.{component_key}",
                ctx.id(component_key),
                ctx.id(deployment_key),
                "deployed_on",
            )
        )
    for component_key, trust_key in COMPONENT_TRUST.items():
        platform_links.append(
            ctx.relationship(
                f"sol.link.contained.{component_key}",
                ctx.id(component_key),
                ctx.id(trust_key),
                "contained_in",
            )
        )
    for interface_key, trust_key in INTERFACE_TRUST.items():
        platform_links.append(
            ctx.relationship(
                f"sol.link.crosses.{interface_key}",
                ctx.id(interface_key),
                ctx.id(trust_key),
                "crosses",
            )
        )
    for required_key, provided_key in CONNECTS_TO:
        platform_links.append(
            ctx.relationship(
                f"sol.link.connects.{required_key}",
                ctx.id(required_key),
                ctx.id(provided_key),
                "connects_to",
            )
        )
    db.add_all(platform_links)


SYSTEM_ORDER = ("crm", "billing", "integration_runtime")
