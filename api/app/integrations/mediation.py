"""Contract mediation resolution (explicit mediator slice).

A Contract keeps its true business direction (``source`` -> ``target``). The
mediator is an *overlay*: an integration runtime, ESB, gateway or broker that
carries the exchange. This module is the single source of truth for answering
"is this contract mediated, and by what?" so every projection reconciles the
explicit canonical field with the legacy runtime-endpoint heuristic identically.

Resolution order (deterministic):

1. ``mediator_system_id`` is set  -> ``mediated`` true, ``explicit``.
2. Otherwise the legacy runtime-endpoint heuristic matches (a modelled runtime
   system is one of the business endpoints) -> ``mediated`` true,
   ``legacy_endpoint_heuristic``.
3. Otherwise -> ``mediated`` false, ``none``.

The explicit mediator is never substituted for the business source or target.
``NULL`` ``mediator_system_id`` means "no mediator is explicitly modelled"; it
is never coerced into a concrete system.
"""

from dataclasses import dataclass

from app.integrations.schemas import (
    IntegrationEndpointRef,
    IntegrationMediatorRef,
)
from app.models import CatalogSystem, Integration

MEDIATION_EXPLICIT = "explicit"
MEDIATION_LEGACY = "legacy_endpoint_heuristic"
MEDIATION_NONE = "none"

# A system counts as an integration runtime only when the modelled data proves
# it: its catalog kind is an explicit runtime kind, or its name names a runtime.
RUNTIME_SYSTEM_KINDS = {"integration_runtime", "integration_runtime_platform", "esb", "runtime"}


def is_runtime_system(system: CatalogSystem | None) -> bool:
    if system is None:
        return False
    if (system.kind or "").strip().lower() in RUNTIME_SYSTEM_KINDS:
        return True
    return "runtime" in (system.name or "").strip().lower()


def endpoint_ref(
    systems: dict,
    objects: dict,
    system_id,
    object_id,
) -> IntegrationEndpointRef:
    """The canonical business endpoint projection, shared by every workbench."""
    system = systems.get(system_id)
    obj = objects.get(object_id)
    return IntegrationEndpointRef(
        system_id=system_id,
        system_name=system.name if system else "Unknown system",
        object_id=object_id,
        object_name=obj.label if obj else "Unknown object",
        system_kind=system.kind if system else None,
        is_runtime=is_runtime_system(system),
    )


@dataclass(frozen=True)
class MediationResolution:
    mediator: IntegrationMediatorRef | None
    explicit: bool
    mediated: bool
    source: str

    @property
    def explicit_mediator(self) -> bool:
        return self.mediator is not None and self.mediator.explicit


_EMPTY = MediationResolution(mediator=None, explicit=False, mediated=False, source=MEDIATION_NONE)


def resolve_mediation(
    integration: Integration,
    systems: dict,
    source: IntegrationEndpointRef | None,
    target: IntegrationEndpointRef | None,
) -> MediationResolution:
    if integration.mediator_system_id is not None:
        system = systems.get(integration.mediator_system_id)
        return MediationResolution(
            mediator=IntegrationMediatorRef(
                system_id=integration.mediator_system_id,
                system_name=system.name if system is not None else "Unknown system",
                system_kind=system.kind if system is not None else None,
                is_runtime=is_runtime_system(system),
                responsibility=integration.mediator_responsibility,
                explicit=True,
            ),
            explicit=True,
            mediated=True,
            source=MEDIATION_EXPLICIT,
        )

    for endpoint in (source, target):
        if endpoint is not None and endpoint.is_runtime:
            return MediationResolution(
                mediator=IntegrationMediatorRef(
                    system_id=endpoint.system_id,
                    system_name=endpoint.system_name,
                    system_kind=endpoint.system_kind,
                    is_runtime=True,
                    responsibility=None,
                    explicit=False,
                ),
                explicit=False,
                mediated=True,
                source=MEDIATION_LEGACY,
            )

    return _EMPTY
