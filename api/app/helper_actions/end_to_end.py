"""Composite end-to-end proposal orchestration (Slice 4).

``propose_end_to_end_architecture`` composes the smaller approved deterministic
proposal helpers into one dependency-ordered change set. It is strictly bounded:
every section is the same closed shape its dedicated helper accepts, and the
orchestrator reuses those builders (and therefore their validation). There is no
natural-language planner and the orchestrator never writes architecture-domain
data.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.helper_actions import integration_proposals, proposals
from app.helper_actions.context import HelperContext
from app.helper_actions.proposals import BuiltOperation, BuiltProposal
from app.helper_actions.schemas import (
    EndToEndRequest,
    InformationModelRequest,
    IntegrationProposalRequest,
    SolutionStructureRequest,
    StrategyChainRequest,
)

COMPOSITE_HELPER = "propose_end_to_end_architecture"

SECTION_HELPER = {
    "enterprise": "propose_strategy_chain",
    "information": "propose_information_model",
    "solution": "propose_solution_structure",
    "integration": "propose_contract",
}


def _domain_request(helper: str, req: EndToEndRequest, section: Any) -> Any:
    if helper in {"propose_strategy_chain"}:
        model = StrategyChainRequest
    elif helper in {"propose_information_model"}:
        model = InformationModelRequest
    elif helper in {"propose_solution_structure"}:
        model = SolutionStructureRequest
    else:  # pragma: no cover - defensive
        model = proposals.REQUEST_MODELS[helper]
    return model(
        state_id=req.state_id,
        summary=req.summary,
        nodes=section.nodes,
        links=section.links,
        realizations=getattr(section, "realizations", []),
        interactions=getattr(section, "interactions", []),
    )


def build_end_to_end_proposal(ctx: HelperContext, req: EndToEndRequest) -> BuiltProposal:
    requested = set(req.requested_disciplines)
    disabled_requested = sorted(
        discipline for discipline in requested if discipline not in ctx.disciplines
    )
    if disabled_requested:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "disabled_discipline", "disciplines": disabled_requested},
        )

    operations: list[BuiltOperation] = []
    reused: list[dict[str, Any]] = []
    proposed: list[dict[str, Any]] = []
    assumptions: list[str] = []
    unresolved: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    disciplines_built: list[str] = []
    seq = 0

    def merge(built: BuiltProposal, discipline: str) -> None:
        nonlocal seq
        id_map: dict[str, str] = {}
        for op in built.operations:
            seq += 1
            id_map[op.operation_id] = f"e2e-op-{seq}"
        for op in built.operations:
            operations.append(
                BuiltOperation(
                    operation_id=id_map[op.operation_id],
                    domain_action=op.domain_action,
                    target_type=op.target_type,
                    target_id=op.target_id,
                    temporary_id=op.temporary_id,
                    before_value=op.before_value,
                    proposed_value=op.proposed_value,
                    depends_on=[id_map[dep] for dep in op.depends_on if dep in id_map],
                    explanation=op.explanation,
                )
            )
        reused.extend(built.reused_objects)
        proposed.extend(built.proposed_objects)
        assumptions.extend(built.assumptions)
        unresolved.extend(built.unresolved_decisions)
        warnings.extend(built.warnings)
        for key, value in (built.metadata or {}).items():
            metadata.setdefault(key, value)
        disciplines_built.append(discipline)

    # Enterprise.
    if "enterprise" in ctx.disciplines and req.enterprise is not None:
        built = proposals.build_domain_proposal(
            ctx,
            SECTION_HELPER["enterprise"],
            _domain_request(SECTION_HELPER["enterprise"], req, req.enterprise),
        )
        merge(built, "enterprise")

    # Information.
    if "information" in ctx.disciplines and req.information is not None:
        built = proposals.build_domain_proposal(
            ctx,
            SECTION_HELPER["information"],
            _domain_request(SECTION_HELPER["information"], req, req.information),
        )
        merge(built, "information")

    # Solution.
    if "solution" in ctx.disciplines and req.solution is not None:
        built = proposals.build_domain_proposal(
            ctx,
            SECTION_HELPER["solution"],
            _domain_request(SECTION_HELPER["solution"], req, req.solution),
        )
        merge(built, "solution")

    # Integration.
    if "integration" in ctx.disciplines and req.integration is not None:
        section = req.integration
        integration_req = IntegrationProposalRequest(
            state_id=req.state_id,
            summary=req.summary,
            **section.model_dump(),
        )
        built = integration_proposals.build_integration_proposal(
            ctx, SECTION_HELPER["integration"], integration_req
        )
        merge(built, "integration")

    assumptions.append(
        "Composite proposal composes enabled deterministic helpers; disabled or unnamed "
        "disciplines are omitted, not fabricated."
    )
    unresolved_deduped = list(dict.fromkeys(unresolved))
    return BuiltProposal(
        helper_name=COMPOSITE_HELPER,
        state_id=req.state_id,
        summary=req.summary,
        operations=operations,
        reused_objects=reused,
        proposed_objects=proposed,
        assumptions=list(dict.fromkeys(assumptions)),
        unresolved_decisions=unresolved_deduped,
        warnings=list(dict.fromkeys(warnings)),
        input_summary={
            "operation_count": len(operations),
            "reused_count": len(reused),
            "proposed_count": len(proposed),
            "unresolved_count": len(unresolved_deduped),
            "requested_disciplines": sorted(requested),
            "disciplines_built": disciplines_built,
            "business_intent": req.business_intent,
            "constraints": list(req.constraints),
            "desired_outcomes": list(req.desired_outcomes),
            "preferred_object_count": len(req.preferred_object_ids),
        },
        metadata={**metadata, "composite": True, "disciplines_built": disciplines_built},
    )
