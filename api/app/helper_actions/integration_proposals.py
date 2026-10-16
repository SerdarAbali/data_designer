"""Deterministic proposal builders for the Slice 3 integration helpers.

These builders translate a strict, closed request into typed operations. They
only *read* canonical records (Contracts, Catalog, Solution interfaces) and never
create or modify architecture-domain data: the sole output is a list of
:class:`~app.helper_actions.proposals.BuiltOperation` values that the change-set
service persists as helper lifecycle rows.

Each helper is a named profile over one request shape. A profile fixes the
enabled discipline, the allowed integration patterns, whether an Integration
Runtime is required/forbidden, and which sections are mandatory.

Contract reuse is exact and read-only: an existing Contract is reused unchanged
only when endpoints, interaction type, interfaces, error schema, resilience, and
mappings already satisfy the proposal. Otherwise a *new draft* Contract is
proposed with explicit lineage (``based_on_contract_id`` + ``proposal_intent``).
Helpers never silently clone or mutate an existing Contract, and never create
Catalog records or execute anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.helper_actions import matching
from app.helper_actions.context import HelperContext
from app.helper_actions.proposals import BuiltOperation, BuiltProposal
from app.helper_actions.schemas import (
    ConformanceTestsRequest,
    ContractProposal,
    ContractProposalRequest,
    DirectIntegrationRequest,
    EventDrivenIntegrationRequest,
    FieldMappingsRequest,
    FileTransferIntegrationRequest,
    IntegrationProposalRequest,
    ResilienceConfigurationRequest,
    RuntimeMediatedIntegrationRequest,
    ScenariosRequest,
    TransformationsRequest,
)
from app.integrations.schemas import IntegrationSpecification
from app.scenarios.schemas import ScenarioDocument

API_PATTERNS = frozenset({"point_to_point", "request_reply", "api_gateway", "orchestration"})
EVENT_PATTERNS = frozenset({"publish_subscribe", "event_streaming", "message_queue"})
FILE_PATTERNS = frozenset({"file_transfer", "batch"})

PHASES_BY_INTERACTION = {
    "ONE_WAY": ("request",),
    "REQUEST_RESPONSE": ("request", "success-response"),
    "ASYNC_CALLBACK": ("request", "async-response"),
}
RESPONSE_PHASES = {"success-response", "async-response"}

SCENARIO_CATEGORY = {
    "happy_path": "happy_path",
    "duplicate_request": "alternative",
    "validation_failure": "error",
    "target_unavailable": "error",
    "error_response": "error",
    "event_delivery_failure": "error",
    "file_transfer_failure": "error",
}

SCENARIO_TEXT = {
    "happy_path": (
        "The source system sends a valid request to the target system.",
        "A valid request is submitted end to end.",
    ),
    "validation_failure": (
        "The request fails validation before reaching the target system.",
        "An invalid request is submitted.",
    ),
    "target_unavailable": (
        "The target system is unavailable and the failure is reported.",
        "The target system is taken offline.",
    ),
    "duplicate_request": (
        "A duplicate request is delivered and idempotency is exercised.",
        "The same request is delivered twice.",
    ),
    "error_response": (
        "The target system returns a modelled error response.",
        "The target system rejects the request.",
    ),
    "event_delivery_failure": (
        "An event is not delivered and the failure is reported.",
        "The event broker drops an event.",
    ),
    "file_transfer_failure": (
        "A file transfer fails and the failure is reported.",
        "The file exchange fails.",
    ),
}


def _reject(code: str, **context: Any) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, **context},
    )


def _spec_equal(contract_spec: Any, requested: IntegrationSpecification) -> bool:
    try:
        stored = IntegrationSpecification.model_validate(contract_spec or {})
    except ValidationError:
        return False
    return stored.model_dump(mode="json") == requested.model_dump(mode="json")


def _types_compatible(source: str | None, target: str | None) -> bool:
    if not source or not target:
        return True
    if source == target:
        return True
    numeric = {"int", "integer", "number", "float", "decimal"}
    text = {"string", "text", "varchar", "char"}
    if {source, target} <= numeric:
        return True
    if {source, target} <= text:
        return True
    return False


@dataclass(frozen=True)
class IntegrationProfile:
    discipline: str
    patterns: frozenset[str] | None
    require_mappings: bool = False
    require_transformations: bool = False
    require_resilience: bool = False
    require_scenarios: bool = False
    require_conformance: bool = False
    forbid_runtime: bool = False
    require_runtime: bool = False


PROFILES: dict[str, IntegrationProfile] = {
    "propose_direct_integration": IntegrationProfile(
        "integration", API_PATTERNS, forbid_runtime=True
    ),
    "propose_event_driven_integration": IntegrationProfile("integration", EVENT_PATTERNS),
    "propose_runtime_mediated_integration": IntegrationProfile(
        "integration", API_PATTERNS | EVENT_PATTERNS, require_runtime=True
    ),
    "propose_file_transfer_integration": IntegrationProfile(
        "integration", FILE_PATTERNS, forbid_runtime=True
    ),
    "propose_contract": IntegrationProfile("integration", None),
    "propose_field_mappings": IntegrationProfile("integration", None, require_mappings=True),
    "propose_transformations": IntegrationProfile(
        "integration", None, require_transformations=True
    ),
    "propose_resilience_configuration": IntegrationProfile(
        "integration", None, require_resilience=True
    ),
    "propose_scenarios": IntegrationProfile("integration", None, require_scenarios=True),
    "propose_conformance_tests": IntegrationProfile(
        "integration", None, require_conformance=True
    ),
}

REQUEST_MODELS: dict[str, type] = {
    "propose_direct_integration": DirectIntegrationRequest,
    "propose_event_driven_integration": EventDrivenIntegrationRequest,
    "propose_runtime_mediated_integration": RuntimeMediatedIntegrationRequest,
    "propose_file_transfer_integration": FileTransferIntegrationRequest,
    "propose_contract": ContractProposalRequest,
    "propose_field_mappings": FieldMappingsRequest,
    "propose_transformations": TransformationsRequest,
    "propose_resilience_configuration": ResilienceConfigurationRequest,
    "propose_scenarios": ScenariosRequest,
    "propose_conformance_tests": ConformanceTestsRequest,
}


class _IntegrationBuilder:
    def __init__(
        self,
        ctx: HelperContext,
        helper_name: str,
        req: IntegrationProposalRequest,
        profile: IntegrationProfile,
    ) -> None:
        self.ctx = ctx
        self.helper_name = helper_name
        self.req = req
        self.profile = profile
        self.design: ContractProposal | None = None
        self.ops: list[BuiltOperation] = []
        self._seq = 0
        self._temps: set[str] = set()
        self.reused: dict[str, dict[str, Any]] = {}
        self.proposed: dict[str, dict[str, Any]] = {}
        self.assumptions: list[str] = []
        self.unresolved: list[str] = []
        self.warnings: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.contract_ref: str | None = None
        self.contract_uuid: UUID | None = None
        self.contract_operation_id: str | None = None
        self.contract_is_new = False
        self._phase_intents: dict[str, Any] = {}
        self._resolved_mappings: list[dict[str, Any]] = []
        self._mapping_ops: dict[str, str] = {}
        self._transformation_ops: dict[str, str] = {}
        self._scenario_temps: dict[str, str] = {}
        self._scenario_ops: dict[str, str] = {}
        self.mapping_report: dict[str, list[Any]] = {
            "exact": [],
            "ambiguous": [],
            "unmapped_required_target_fields": [],
            "unused_source_fields": [],
            "type_incompatibilities": [],
        }

    # -- primitives -----------------------------------------------------------

    def _emit(
        self,
        domain_action: str,
        target_type: str,
        *,
        target_id: UUID | None = None,
        temporary_id: str | None = None,
        proposed_value: dict[str, Any] | None = None,
        before_value: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        explanation: str = "",
    ) -> BuiltOperation:
        self._seq += 1
        op = BuiltOperation(
            operation_id=f"op-{self._seq}",
            domain_action=domain_action,
            target_type=target_type,
            target_id=target_id,
            temporary_id=temporary_id,
            before_value=before_value,
            proposed_value=proposed_value or {},
            depends_on=list(dict.fromkeys(depends_on or [])),
            explanation=explanation,
        )
        self.ops.append(op)
        return op

    def _temp(self, kind: str, name: str) -> str:
        base = f"tmp:{kind}:{matching.slug(name)}"
        candidate = base
        suffix = 2
        while candidate in self._temps:
            candidate = f"{base}-{suffix}"
            suffix += 1
        self._temps.add(candidate)
        return candidate

    def _unresolved(self, decision: str) -> None:
        if decision not in self.unresolved:
            self.unresolved.append(decision)

    # -- phase helpers --------------------------------------------------------

    def _phase_allowed(self, phase: str, has_error: bool) -> bool:
        if phase == "error-response":
            return has_error
        assert self.design is not None
        return phase in PHASES_BY_INTERACTION.get(self.design.interaction_type, ("request",))

    def _phase_objects(self, phase: str) -> tuple[UUID, UUID, str, str]:
        design = self.design
        assert design is not None
        if phase == "request":
            return design.source_object_id, design.target_object_id, "source", "target"
        if phase in RESPONSE_PHASES:
            return (
                design.target_object_id,
                design.source_object_id,
                "response_source",
                "response_target",
            )
        error_object = design.error_response_object_id or design.target_object_id
        return (
            error_object,
            design.source_object_id,
            "error_response_source",
            "error_response_target",
        )

    # -- request / ref checks -------------------------------------------------

    def _check_explicit_refs(self) -> None:
        if self.req.contract_id is not None and matching.find_contract(
            self.ctx, self.req.contract_id
        ) is None:
            _reject("unknown_reference", object_id=str(self.req.contract_id))
        if self.req.based_on_contract_id is not None and matching.find_contract(
            self.ctx, self.req.based_on_contract_id
        ) is None:
            _reject("unknown_reference", object_id=str(self.req.based_on_contract_id))
        if self.req.runtime_system_id is not None and matching.find_catalog_system(
            self.ctx, self.req.runtime_system_id
        ) is None:
            _reject("unknown_reference", object_id=str(self.req.runtime_system_id))

    def _resolve_design(self) -> ContractProposal | None:
        if self.req.contract is not None:
            return self.req.contract
        if self.req.contract_id is not None:
            contract = matching.find_contract(self.ctx, self.req.contract_id)
            if contract is not None:
                return ContractProposal(
                    key="contract",
                    name=contract.name,
                    description=contract.description,
                    purpose=None,
                    source_system_id=contract.source_system_id,
                    source_object_id=contract.source_object_id,
                    target_system_id=contract.target_system_id,
                    target_object_id=contract.target_object_id,
                    error_response_object_id=contract.error_response_object_id,
                    interaction_type=contract.interaction_type,
                    pattern=contract.pattern or "other",
                    implementation_status=contract.implementation_status or "draft",
                    producer_interface_id=contract.producer_interface_id,
                    consumer_interface_id=contract.consumer_interface_id,
                    external_identifier=contract.external_identifier,
                )
        return None

    def _check_profile(self) -> None:
        design = self.design
        if design is None:
            _reject("missing_contract", helper=self.helper_name)
        if self.profile.patterns is not None and design.pattern not in self.profile.patterns:
            _reject(
                "pattern_not_allowed",
                pattern=design.pattern,
                helper=self.helper_name,
            )
        if self.profile.forbid_runtime and (
            self.req.runtime_mediated or self.req.runtime_system_id is not None
        ):
            _reject("runtime_not_allowed", helper=self.helper_name)
        if self.profile.require_runtime and not self.req.runtime_mediated:
            _reject("runtime_required", helper=self.helper_name)

    def _check_runtime(self) -> None:
        if self.req.runtime_mediated:
            if self.req.runtime_system_id is None:
                _reject("missing_runtime_system", helper=self.helper_name)
            system = matching.find_catalog_system(self.ctx, self.req.runtime_system_id)
            if system is None:
                _reject("unknown_reference", object_id=str(self.req.runtime_system_id))
            if not matching.is_runtime_system(system):
                _reject(
                    "not_a_runtime",
                    system_id=str(system.id),
                    message="Runtime-mediated integration needs a canonical runtime system",
                )
        elif self.req.runtime_system_id is not None:
            _reject("runtime_flag_required", helper=self.helper_name)

    def _check_design_refs(self) -> None:
        design = self.design
        assert design is not None
        source_system = matching.find_catalog_system(self.ctx, design.source_system_id)
        if source_system is None:
            _reject("unknown_reference", object_id=str(design.source_system_id))
        target_system = matching.find_catalog_system(self.ctx, design.target_system_id)
        if target_system is None:
            _reject("unknown_reference", object_id=str(design.target_system_id))
        source_object = matching.find_catalog_object(self.ctx, design.source_object_id)
        if source_object is None:
            _reject("unknown_reference", object_id=str(design.source_object_id))
        if source_object.system_id != source_system.id:
            _reject("object_system_mismatch", object_id=str(source_object.id))
        target_object = matching.find_catalog_object(self.ctx, design.target_object_id)
        if target_object is None:
            _reject("unknown_reference", object_id=str(design.target_object_id))
        if target_object.system_id != target_system.id:
            _reject("object_system_mismatch", object_id=str(target_object.id))
        if design.error_response_object_id is not None:
            error_object = matching.find_catalog_object(
                self.ctx, design.error_response_object_id
            )
            if error_object is None:
                _reject("unknown_reference", object_id=str(design.error_response_object_id))
            if error_object.system_id != target_system.id:
                _reject("object_system_mismatch", object_id=str(error_object.id))
        for interface_id, label in (
            (design.producer_interface_id, "producer"),
            (design.consumer_interface_id, "consumer"),
        ):
            if interface_id is not None and matching.find_interface(self.ctx, interface_id) is None:
                _reject("unknown_reference", object_id=str(interface_id), role=label)

    # -- phase intents --------------------------------------------------------

    def _resolve_phase_intents(self) -> dict[str, Any]:
        """Resolve request/success/error phase operation refs to canonical operations."""
        design = self.design
        assert design is not None
        result: dict[str, Any] = {
            "request_phase": None,
            "success_response_phase": None,
            "error_response_phase": None,
        }
        for attr in result:
            intent = getattr(design, attr)
            if intent is None:
                continue
            refs: list[dict[str, Any]] = []
            for ref in intent.operation_refs:
                operation = None
                ambiguous = False
                if ref.operation_id is not None:
                    operation = matching.find_interface_operation(self.ctx, ref.operation_id)
                    if operation is None:
                        _reject("unknown_reference", object_id=str(ref.operation_id))
                elif ref.interface_id is not None and ref.name:
                    operation, ambiguous = matching.match_interface_operation_in_interface(
                        self.ctx, ref.interface_id, ref.name
                    )
                    if operation is None:
                        self._unresolved(
                            f"No interface operation matched '{ref.name}'"
                            + (" (ambiguous)" if ambiguous else "")
                        )
                elif ref.name:
                    operation, ambiguous = matching.match_interface_operation_by_name(
                        self.ctx, ref.name
                    )
                    if operation is None:
                        self._unresolved(
                            f"No unique interface operation matched '{ref.name}'"
                            + (" (ambiguous)" if ambiguous else "")
                        )
                refs.append(
                    {
                        "operation_id": str(operation.object_id) if operation is not None else None,
                        "declared_operation_id": (
                            str(ref.operation_id) if ref.operation_id is not None else None
                        ),
                        "interface_id": (
                            str(ref.interface_id) if ref.interface_id is not None else None
                        ),
                        "name": ref.name,
                        "kind": ref.kind,
                        "resolved_kind": (
                            operation.operation_kind if operation is not None else None
                        ),
                        "resolved": operation is not None,
                    }
                )
            result[attr] = {
                "routing": intent.routing,
                "notes": intent.notes,
                "operation_refs": refs,
            }
        return result

    # -- contract matching ----------------------------------------------------

    def _order_key(self, contract: Any) -> tuple:
        design = self.design
        assert design is not None
        name = matching.normalize_name(design.name)
        name_rank = 0 if name == matching.normalize_name(contract.name or "") else 1
        purpose_rank = 1
        if design.purpose:
            purpose = matching.normalize_purpose(design.purpose)
            candidates = {
                matching.normalize_name(contract.name or ""),
                matching.normalize_name(contract.description or ""),
            }
            purpose_rank = 0 if purpose in candidates else 1
        return (name_rank, purpose_rank, contract.name or "", str(contract.id))

    def _design_matches(self, contract: Any) -> bool:
        design = self.design
        assert design is not None
        return (
            design.source_system_id == contract.source_system_id
            and design.source_object_id == contract.source_object_id
            and design.target_system_id == contract.target_system_id
            and design.target_object_id == contract.target_object_id
            and design.interaction_type == contract.interaction_type
            and (design.error_response_object_id or None)
            == (contract.error_response_object_id or None)
            and (design.pattern is None or design.pattern == contract.pattern)
            and (design.producer_interface_id or None) == (contract.producer_interface_id or None)
            and (design.consumer_interface_id or None) == (contract.consumer_interface_id or None)
            and (
                design.external_identifier is None
                or design.external_identifier == contract.external_identifier
            )
        )

    def _mapping_covered(self, contract: Any, resolved: dict[str, Any]) -> bool:
        refs = matching.list_field_refs(self.ctx, contract.id)
        keys = {(ref.direction, ref.object_id, ref.field_id) for ref in refs}
        return (
            resolved["source_direction"],
            resolved["source_object_id"],
            resolved["source_field_id"],
        ) in keys and (
            resolved["target_direction"],
            resolved["target_object_id"],
            resolved["target_field_id"],
        ) in keys

    def _extras_match(self, contract: Any) -> bool:
        if self.req.transformations:
            return False
        # Phase operation intents are not persisted on existing Contracts, so an
        # explicit phase intent cannot be verified as already satisfied.
        if any(value is not None for value in self._phase_intents.values()):
            return False
        if self.req.resilience is not None and not _spec_equal(
            contract.specification, self.req.resilience
        ):
            return False
        for resolved in self._resolved_mappings:
            if not resolved["resolved"]:
                return False
            if not self._mapping_covered(contract, resolved):
                return False
        return True

    def _satisfies(self, contract: Any) -> bool:
        return self._design_matches(contract) and self._extras_match(contract)

    def _candidate_contracts(self) -> list[Any]:
        design = self.design
        assert design is not None
        candidates = [c for c in matching.list_contracts(self.ctx) if self._design_matches(c)]
        if design.external_identifier:
            external = matching.find_contract_by_external_id(
                self.ctx, design.external_identifier
            )
            if external is not None and self._design_matches(external):
                candidates = [external, *[c for c in candidates if c.id != external.id]]
        return sorted(candidates, key=self._order_key)

    def _matched_by(self, contract: Any) -> str:
        design = self.design
        assert design is not None
        if design.external_identifier and (
            design.external_identifier == contract.external_identifier
        ):
            return "external_identifier"
        return "endpoints_interaction_interfaces"

    def _intent_for_lineage(self) -> str:
        if self.req.proposal_intent == "independent":
            _reject("lineage_intent_required", helper=self.helper_name)
        return self.req.proposal_intent

    def _decide_contract(self) -> None:
        design = self.design
        assert design is not None
        explicit = (
            matching.find_contract(self.ctx, self.req.contract_id)
            if self.req.contract_id is not None
            else None
        )
        if explicit is not None:
            if self._satisfies(explicit):
                self._reuse(explicit, "explicit_id")
            else:
                based_on = self.req.based_on_contract_id or explicit.id
                self._create(based_on, self._intent_for_lineage())
            return
        for contract in self._candidate_contracts():
            if self._satisfies(contract):
                self._reuse(contract, self._matched_by(contract))
                return
        self._create(self.req.based_on_contract_id, self.req.proposal_intent)

    def _reuse(self, contract: Any, matched_by: str) -> None:
        op = self._emit(
            "reuse_contract",
            "contract",
            target_id=contract.id,
            proposed_value={
                "kind": "contract",
                "contract_id": str(contract.id),
                "name": contract.name,
                "reused": True,
                "matched_by": matched_by,
            },
            explanation=f"Reuse existing Contract '{contract.name}' unchanged ({matched_by})",
        )
        self.contract_ref = str(contract.id)
        self.contract_uuid = contract.id
        self.contract_operation_id = op.operation_id
        self.contract_is_new = False
        self.reused[str(contract.id)] = {
            "target_type": "contract",
            "target_id": str(contract.id),
            "name": contract.name,
            "matched_by": matched_by,
        }
        self.assumptions.append(
            f"Existing Contract '{contract.name}' reused unchanged; reused Contracts are read-only."
        )
        self.metadata["contract_reused"] = True
        self.metadata["contract_matched_by"] = matched_by

    def _create(self, based_on: UUID | None, intent: str) -> None:
        design = self.design
        assert design is not None
        if based_on is not None and intent == "independent":
            _reject("lineage_intent_required", helper=self.helper_name)
        spec = (
            self.req.resilience.model_dump(mode="json")
            if self.req.resilience is not None
            else {}
        )
        temp = self._temp("contract", design.name)
        proposed_value: dict[str, Any] = {
            "kind": "contract",
            "status": "draft",
            "name": design.name,
            "description": design.description,
            "purpose": design.purpose,
            "source_system_id": str(design.source_system_id),
            "source_object_id": str(design.source_object_id),
            "target_system_id": str(design.target_system_id),
            "target_object_id": str(design.target_object_id),
            "error_response_object_id": (
                str(design.error_response_object_id)
                if design.error_response_object_id
                else None
            ),
            "interaction_type": design.interaction_type,
            "pattern": design.pattern,
            "implementation_status": design.implementation_status,
            "producer_interface_id": (
                str(design.producer_interface_id) if design.producer_interface_id else None
            ),
            "consumer_interface_id": (
                str(design.consumer_interface_id) if design.consumer_interface_id else None
            ),
            "external_identifier": design.external_identifier,
            "runtime_mediated": self.req.runtime_mediated,
            "runtime_system_id": (
                str(self.req.runtime_system_id) if self.req.runtime_mediated else None
            ),
            "runtime_responsibility": self.req.runtime_responsibility or "Not defined.",
            "specification": spec,
            "request_phase": self._phase_intents.get("request_phase"),
            "success_response_phase": self._phase_intents.get("success_response_phase"),
            "error_response_phase": self._phase_intents.get("error_response_phase"),
            "based_on_contract_id": str(based_on) if based_on else None,
            "proposal_intent": intent,
        }
        op = self._emit(
            "create_contract",
            "contract",
            temporary_id=temp,
            proposed_value=proposed_value,
            explanation=f"Propose new draft Contract '{design.name}'",
        )
        self.contract_ref = temp
        self.contract_uuid = matching.placeholder_uuid(temp)
        self.contract_operation_id = op.operation_id
        self.contract_is_new = True
        self.proposed[temp] = {
            "temporary_id": temp,
            "target_type": "contract",
            "name": design.name,
        }
        self.assumptions.append("New Contract is proposed as a draft; no Contract ID is assigned.")
        self.metadata["contract_proposed"] = True
        if based_on is not None:
            self.metadata["contract_lineage"] = {
                "based_on_contract_id": str(based_on),
                "proposal_intent": intent,
            }
            self.assumptions.append(
                f"New draft Contract is a {intent.replace('_', ' ')} of Contract {based_on}."
            )

    # -- mappings -------------------------------------------------------------

    def _resolve_field(
        self,
        field_id: UUID | None,
        object_id: UUID | None,
        field_name: str | None,
        external_id: str | None,
        expected_object: UUID,
        label: str,
    ) -> tuple[Any, str | None, list[str]]:
        if object_id is not None and object_id != expected_object:
            _reject("mapping_object_mismatch", role=label, object_id=str(object_id))
        if field_id is not None:
            field = matching.find_catalog_field_by_id(self.ctx, field_id)
            if field is None:
                _reject("unknown_reference", object_id=str(field_id))
            if field.object_id != expected_object:
                _reject("mapping_object_mismatch", role=label, object_id=str(field_id))
            return field, None, []
        if external_id:
            field = matching.find_catalog_field_by_external_id(self.ctx, external_id)
            if field is None:
                return (
                    None,
                    f"No active Catalog field has external id '{external_id}' ({label})",
                    [],
                )
            if field.object_id != expected_object:
                return (
                    None,
                    f"Catalog field '{external_id}' does not belong to the {label} object",
                    [],
                )
            return field, None, []
        if field_name:
            field, ambiguous = matching.match_catalog_field_in_object(
                self.ctx, expected_object, field_name
            )
            if ambiguous:
                return None, f"Multiple Catalog fields match '{field_name}' ({label})", []
            if field is None:
                suggestions = matching.suggest_catalog_fields(self.ctx, field_name)
                return (
                    None,
                    f"No active Catalog field matched '{field_name}' ({label})",
                    suggestions,
                )
            return field, None, []
        return None, f"No Catalog {label} field was supplied", []

    def _resolve_mapping(self, mapping: Any) -> dict[str, Any]:
        design = self.design
        assert design is not None
        if not self._phase_allowed(mapping.phase, design.error_response_object_id is not None):
            _reject(
                "phase_not_allowed",
                phase=mapping.phase,
                interaction_type=design.interaction_type,
            )
        source_object, target_object, source_direction, target_direction = self._phase_objects(
            mapping.phase
        )
        source_field, source_reason, source_candidates = self._resolve_field(
            mapping.source_field_id,
            mapping.source_object_id,
            mapping.source_field_name,
            mapping.source_external_identifier,
            source_object,
            "source",
        )
        target_field, target_reason, target_candidates = self._resolve_field(
            mapping.target_field_id,
            mapping.target_object_id,
            mapping.target_field_name,
            mapping.target_external_identifier,
            target_object,
            "target",
        )
        resolved = source_field is not None and target_field is not None
        reason = None
        candidates: list[str] = []
        if not resolved:
            reason = source_reason or target_reason or f"Mapping '{mapping.key}' is unresolved"
            candidates = sorted(set(source_candidates + target_candidates))[:10]
        type_compatible = None
        if resolved:
            type_compatible = _types_compatible(
                source_field.data_type, target_field.data_type
            )
        return {
            "key": mapping.key,
            "phase": mapping.phase,
            "required": mapping.required,
            "source_field": source_field,
            "target_field": target_field,
            "source_field_id": source_field.id if source_field else None,
            "target_field_id": target_field.id if target_field else None,
            "source_object_id": source_object,
            "target_object_id": target_object,
            "source_direction": source_direction,
            "target_direction": target_direction,
            "resolved": resolved,
            "reason": reason,
            "candidates": candidates,
            "type_compatible": type_compatible,
            "transformation_key": mapping.transformation_key,
        }

    def _emit_mappings(self) -> None:
        if not self.req.mappings:
            return
        for mapping, resolved in zip(self.req.mappings, self._resolved_mappings, strict=True):
            if resolved["resolved"]:
                self.mapping_report["exact"].append(
                    {
                        "key": resolved["key"],
                        "phase": resolved["phase"],
                        "source_field_id": str(resolved["source_field_id"]),
                        "target_field_id": str(resolved["target_field_id"]),
                    }
                )
            else:
                self.mapping_report["ambiguous"].append(
                    {
                        "key": resolved["key"],
                        "phase": resolved["phase"],
                        "required": resolved["required"],
                        "reason": resolved["reason"],
                        "candidates": resolved["candidates"],
                    }
                )
                self._unresolved(resolved["reason"])
                self.metadata["ambiguous_mappings"] = (
                    self.metadata.get("ambiguous_mappings", 0) + 1
                )
            if resolved["type_compatible"] is False:
                self.mapping_report["type_incompatibilities"].append(
                    {
                        "key": resolved["key"],
                        "source_field_id": str(resolved["source_field_id"]),
                        "target_field_id": str(resolved["target_field_id"]),
                        "source_type": resolved["source_field"].data_type,
                        "target_type": resolved["target_field"].data_type,
                    }
                )
            if not self.contract_is_new:
                continue
            proposed_value: dict[str, Any] = {
                "contract_ref": self.contract_ref,
                "phase": resolved["phase"],
                "source_object_id": str(resolved["source_object_id"]),
                "target_object_id": str(resolved["target_object_id"]),
                "source_field_id": (
                    str(resolved["source_field_id"]) if resolved["source_field_id"] else None
                ),
                "target_field_id": (
                    str(resolved["target_field_id"]) if resolved["target_field_id"] else None
                ),
                "source_field_name": mapping.source_field_name,
                "target_field_name": mapping.target_field_name,
                "required": resolved["required"],
                "resolved": resolved["resolved"],
                "type_compatible": resolved["type_compatible"],
                "transformation_key": resolved["transformation_key"],
            }
            if resolved["resolved"]:
                proposed_value["required_for_approval"] = True
            else:
                proposed_value.update(
                    {
                        "unresolved": True,
                        "reason": resolved["reason"],
                        "candidates": resolved["candidates"],
                        "required_for_approval": bool(resolved["required"]),
                    }
                )
            op = self._emit(
                "create_mapping",
                "mapping",
                temporary_id=self._temp("mapping", resolved["key"]),
                proposed_value=proposed_value,
                depends_on=[self.contract_operation_id] if self.contract_operation_id else [],
                explanation=(
                    f"Propose {resolved['phase']} mapping '{resolved['key']}'"
                    + (" (unresolved)" if not resolved["resolved"] else "")
                ),
            )
            self._mapping_ops[resolved["key"]] = op.operation_id
        self.metadata["mappings"] = len(self.req.mappings)
        self._report_mapping_coverage()

    def _report_mapping_coverage(self) -> None:
        design = self.design
        assert design is not None
        mapped_source: set[UUID] = set()
        mapped_target: set[UUID] = set()
        for resolved in self._resolved_mappings:
            if resolved["source_field_id"]:
                mapped_source.add(resolved["source_field_id"])
            if resolved["target_field_id"]:
                mapped_target.add(resolved["target_field_id"])
        unmapped_required: list[str] = []
        unused: list[str] = []
        seen_phase: set[str] = set()
        for resolved in self._resolved_mappings:
            phase = resolved["phase"]
            if phase in seen_phase:
                continue
            seen_phase.add(phase)
            source_object, target_object, _, _ = self._phase_objects(phase)
            for field in matching.list_active_fields(self.ctx, target_object):
                if field.required and field.id not in mapped_target:
                    unmapped_required.append(f"phase={phase}:{field.name}")
            for field in matching.list_active_fields(self.ctx, source_object):
                if field.id not in mapped_source:
                    unused.append(f"phase={phase}:{field.name}")
        self.mapping_report["unmapped_required_target_fields"] = sorted(set(unmapped_required))
        self.mapping_report["unused_source_fields"] = sorted(set(unused))

    # -- transformations ------------------------------------------------------

    def _emit_transformations(self) -> None:
        if not self.contract_is_new:
            return
        mapping_field_ops: dict[str, str] = {}
        for resolved in self._resolved_mappings:
            op_id = self._mapping_ops.get(resolved["key"])
            if op_id is None:
                continue
            if resolved["source_field_id"]:
                mapping_field_ops[str(resolved["source_field_id"])] = op_id
            if resolved["target_field_id"]:
                mapping_field_ops[str(resolved["target_field_id"])] = op_id
        for transformation in self.req.transformations:
            deps = [self.contract_operation_id] if self.contract_operation_id else []
            for field_id in transformation.source_field_ids:
                op_id = mapping_field_ops.get(str(field_id))
                if op_id:
                    deps.append(op_id)
            op_id = mapping_field_ops.get(str(transformation.target_field_id))
            if op_id:
                deps.append(op_id)
            proposed_value = {
                "contract_ref": self.contract_ref,
                "phase": transformation.phase,
                "node_type": transformation.node_type,
                "source_field_ids": [str(item) for item in transformation.source_field_ids],
                "target_field_id": str(transformation.target_field_id),
                "config": transformation.config,
                "reason": transformation.reason,
                "evidence": transformation.evidence,
            }
            op = self._emit(
                "create_transformation",
                "transformation",
                temporary_id=self._temp("transformation", transformation.key),
                proposed_value=proposed_value,
                depends_on=deps,
                explanation=(
                    f"Propose {transformation.node_type} transformation "
                    f"'{transformation.key}'"
                ),
            )
            self._transformation_ops[transformation.key] = op.operation_id
        self.metadata["transformations"] = len(self.req.transformations)

    # -- resilience -----------------------------------------------------------

    def _emit_resilience(self) -> None:
        if self.req.resilience is None:
            return
        if not self.contract_is_new:
            self.metadata["resilience_satisfied"] = True
            return
        spec = self.req.resilience.model_dump(mode="json")
        proposed_value = {
            "contract_ref": self.contract_ref,
            "specification": spec,
            "idempotency_key_field_id": spec.get("idempotency_key_field_id"),
            "responsibility": self.req.runtime_responsibility or "Not defined.",
        }
        self._emit(
            "configure_resilience",
            "resilience",
            temporary_id=self._temp("resilience", "contract"),
            proposed_value=proposed_value,
            depends_on=[self.contract_operation_id] if self.contract_operation_id else [],
            explanation="Configure retry, timeout, idempotency, routing, auth, and error handling",
        )
        self.metadata["resilience"] = True

    # -- scenarios ------------------------------------------------------------

    def _scenario_document(self, scenario: Any) -> dict[str, Any]:
        design = self.design
        assert design is not None
        if not self._phase_allowed(scenario.phase, design.error_response_object_id is not None):
            _reject(
                "phase_not_allowed",
                phase=scenario.phase,
                interaction_type=design.interaction_type,
            )
        source_object, target_object, _, _ = self._phase_objects(scenario.phase)
        allowed = {
            field.id
            for field in matching.list_active_fields(self.ctx, source_object)
        } | {
            field.id
            for field in matching.list_active_fields(self.ctx, target_object)
        }

        def normalize_values(values: dict[str, Any]) -> dict[str, Any]:
            normalized: dict[str, Any] = {}
            for key, value in values.items():
                try:
                    field_id = UUID(str(key))
                except (ValueError, AttributeError):
                    _reject("invalid_scenario_field_key", key=str(key))
                if field_id not in allowed:
                    _reject("unknown_reference", object_id=str(key), helper=self.helper_name)
                normalized[str(field_id)] = value
            return normalized

        sample_values = normalize_values(scenario.synthetic_values)
        expected_values = normalize_values(scenario.expected_values)

        source_system = matching.find_catalog_system(self.ctx, design.source_system_id)
        target_system = matching.find_catalog_system(self.ctx, design.target_system_id)
        participants = [
            {
                "id": "source",
                "kind": "system",
                "systemId": str(design.source_system_id),
                "label": source_system.name if source_system else None,
            },
            {
                "id": "target",
                "kind": "system",
                "systemId": str(design.target_system_id),
                "label": target_system.name if target_system else None,
            },
        ]
        if self.req.runtime_mediated and self.req.runtime_system_id is not None:
            runtime = matching.find_catalog_system(self.ctx, self.req.runtime_system_id)
            participants.append(
                {
                    "id": "runtime",
                    "kind": "system",
                    "systemId": str(self.req.runtime_system_id),
                    "label": runtime.name if runtime else None,
                }
            )
        preconditions, trigger = SCENARIO_TEXT[scenario.scenario_type]
        document: dict[str, Any] = {
            "version": 1,
            "preconditions": preconditions,
            "trigger": trigger,
            "participants": participants,
            "contractIds": [str(self.contract_uuid)],
            "beforeState": [],
            "afterState": [],
            "items": [
                {
                    "id": "step-1",
                    "kind": "contract",
                    "contractId": str(self.contract_uuid),
                    "phase": scenario.phase,
                    "sampleValues": sample_values,
                    "expectedValues": expected_values,
                }
            ],
            "assertions": [],
            "notes": f"{scenario.notes or ''} Synthetic values generated by the helper.".strip(),
        }
        if expected_values:
            assertion_field = sorted(expected_values)[0]
            document["assertions"] = [
                {
                    "id": "assert-1",
                    "text": scenario.assertion_text or "The expected value is produced.",
                    "stepId": "step-1",
                    "fieldId": assertion_field,
                    "expected": expected_values[assertion_field],
                }
            ]
        try:
            model = ScenarioDocument.model_validate(document)
        except ValidationError as exc:
            _reject("invalid_scenario", errors=exc.errors()[:5])
        return model.model_dump(mode="json", by_alias=True)

    def _emit_scenarios(self) -> None:
        for scenario in self.req.scenarios:
            document = self._scenario_document(scenario)
            temp = self._temp("scenario", scenario.key)
            deps = [self.contract_operation_id] if self.contract_operation_id else []
            deps.extend(self._transformation_ops.values())
            deps = [dep for dep in deps if dep]
            proposed_value = {
                "contract_ref": self.contract_ref,
                "contract_uuid": str(self.contract_uuid),
                "name": scenario.name,
                "category": SCENARIO_CATEGORY[scenario.scenario_type],
                "scenario_type": scenario.scenario_type,
                "phase": scenario.phase,
                "synthetic": True,
                "document": document,
            }
            op = self._emit(
                "create_scenario",
                "scenario",
                temporary_id=temp,
                proposed_value=proposed_value,
                depends_on=deps,
                explanation=f"Propose {scenario.scenario_type} scenario '{scenario.name}'",
            )
            self._scenario_temps[scenario.key] = temp
            self._scenario_ops[scenario.key] = op.operation_id
        if self.req.scenarios:
            self.metadata["scenarios"] = len(self.req.scenarios)

    # -- conformance ----------------------------------------------------------

    def _emit_conformance(self) -> None:
        for expectation in self.req.conformance:
            scenario_ref = None
            if expectation.scenario_key is not None:
                if expectation.scenario_key not in self._scenario_temps:
                    _reject("unknown_scenario_key", key=expectation.scenario_key)
                scenario_ref = self._scenario_temps[expectation.scenario_key]
            for field_id in expectation.field_ids:
                if matching.find_catalog_field_by_id(self.ctx, field_id) is None:
                    _reject("unknown_reference", object_id=str(field_id))
            deps = [self.contract_operation_id] if self.contract_operation_id else []
            if expectation.scenario_key is not None:
                deps.append(self._scenario_ops[expectation.scenario_key])
            proposed_value = {
                "contract_ref": self.contract_ref,
                "expectation_type": expectation.expectation_type,
                "phase": expectation.phase,
                "coverage_min": expectation.coverage_min,
                "field_ids": [str(item) for item in expectation.field_ids],
                "expected_success": expectation.expected_success,
                "expected_phase": expectation.expected_phase,
                "scenario_ref": scenario_ref,
                "expected_revision": expectation.expected_revision,
                "notes": expectation.notes,
            }
            self._emit(
                "define_conformance_expectation",
                "conformance",
                temporary_id=self._temp("expectation", expectation.key),
                proposed_value=proposed_value,
                depends_on=[dep for dep in deps if dep],
                explanation=(
                    f"Define {expectation.expectation_type} conformance "
                    f"expectation '{expectation.key}'"
                ),
            )
        if self.req.conformance:
            self.metadata["conformance"] = len(self.req.conformance)

    # -- required sections ----------------------------------------------------

    def _check_required_sections(self) -> None:
        checks = (
            (self.profile.require_mappings, self.req.mappings, "mappings"),
            (self.profile.require_transformations, self.req.transformations, "transformations"),
            (self.profile.require_resilience, self.req.resilience, "resilience"),
            (self.profile.require_scenarios, self.req.scenarios, "scenarios"),
            (self.profile.require_conformance, self.req.conformance, "conformance"),
        )
        for required, value, label in checks:
            if required and not value:
                _reject("missing_section", section=label, helper=self.helper_name)

    # -- entry point ----------------------------------------------------------

    def build(self) -> BuiltProposal:
        self._check_explicit_refs()
        self.design = self._resolve_design()
        self._check_profile()
        self._check_runtime()
        self._check_design_refs()
        self._phase_intents = self._resolve_phase_intents()
        keys = [mapping.key for mapping in self.req.mappings]
        if len(keys) != len(set(keys)):
            _reject("duplicate_mapping_key")
        self._resolved_mappings = [self._resolve_mapping(mapping) for mapping in self.req.mappings]
        self._decide_contract()
        self._emit_mappings()
        self._emit_transformations()
        self._emit_resilience()
        self._emit_scenarios()
        self._emit_conformance()
        self._check_required_sections()
        return BuiltProposal(
            helper_name=self.helper_name,
            state_id=self.req.state_id,
            summary=self.req.summary,
            operations=self.ops,
            reused_objects=[self.reused[key] for key in sorted(self.reused)],
            proposed_objects=sorted(
                self.proposed.values(), key=lambda item: item["temporary_id"]
            ),
            assumptions=self.assumptions,
            unresolved_decisions=self.unresolved,
            warnings=self.warnings,
            input_summary={
                "operation_count": len(self.ops),
                "contract_reused": bool(self.metadata.get("contract_reused")),
                "contract_proposed": bool(self.metadata.get("contract_proposed")),
                "runtime_mediated": self.req.runtime_mediated,
                "mapping_count": len(self.req.mappings),
                "transformation_count": len(self.req.transformations),
                "scenario_count": len(self.req.scenarios),
                "conformance_count": len(self.req.conformance),
                "unresolved_count": len(self.unresolved),
                "mapping_report": self.mapping_report,
                "requested_disciplines": [self.profile.discipline],
            },
            metadata=self.metadata,
        )


def build_integration_proposal(
    ctx: HelperContext, helper_name: str, req: IntegrationProposalRequest
) -> BuiltProposal:
    profile = PROFILES[helper_name]
    return _IntegrationBuilder(ctx, helper_name, req, profile).build()
