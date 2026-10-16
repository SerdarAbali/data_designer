import type { ScenarioDocument, ScenarioItem, ScenarioParticipant, ScenarioStep } from "../scenarioModel";
import type { SolutionDesign } from "./solutionModel";

export const EXTERNAL_PARTICIPANT_ID = "participant-external";

export type SolutionStepRef = {
  stepId: string;
  operationId: string | null;
  operationName: string;
  componentId: string;
  componentName: string;
  interfaceId: string;
  interfaceName: string;
  direction: "provided" | "required";
};

export type SolutionSequence = {
  document: ScenarioDocument;
  stepRefs: Map<string, SolutionStepRef>;
};

export function componentParticipantId(objectId: string): string {
  return `component-${objectId}`;
}

/**
 * Adapts the canonical solution design into the shared scenario document shape
 * so the existing sequence layout/rendering engine draws the interaction view.
 */
export function buildSolutionSequence(design: SolutionDesign): SolutionSequence {
  const participants: ScenarioParticipant[] = design.components
    .filter((component) => component.interfaces.length > 0)
    .map((component) => ({
      id: componentParticipantId(component.object_id),
      kind: "system" as const,
      label: component.name,
    }));

  const hasInterfaces = participants.length > 0;
  const participantIds = new Set(participants.map((participant) => participant.id));
  if (hasInterfaces) {
    participants.unshift({
      id: EXTERNAL_PARTICIPANT_ID,
      kind: "actor" as const,
      label: "External",
    });
    participantIds.add(EXTERNAL_PARTICIPANT_ID);
  }

  const componentByInterface = new Map<string, string>();
  for (const component of design.components) {
    for (const ui of component.interfaces) componentByInterface.set(ui.object_id, component.object_id);
  }

  const requiredTarget = new Map<string, string>();
  for (const link of design.links.filter((item) => item.relationship_type === "connects_to")) {
    requiredTarget.set(link.source_object_id, link.target_object_id);
  }
  const providerFor = new Map<string, string>();
  const requirerFor = new Map<string, string>();
  for (const [requiredId, providedId] of requiredTarget) {
    const provider = componentByInterface.get(providedId);
    const requirer = componentByInterface.get(requiredId);
    if (provider) providerFor.set(requiredId, provider);
    if (requirer) requirerFor.set(providedId, requirer);
  }

  const items: ScenarioItem[] = [];
  const stepRefs = new Map<string, SolutionStepRef>();

  const resolveEndpoints = (
    ownerComponentId: string,
    interfaceId: string,
    direction: "provided" | "required",
  ): { from: string; to: string } => {
    const owner = componentParticipantId(ownerComponentId);
    if (direction === "provided") {
      const requirer = requirerFor.get(interfaceId);
      return {
        from: requirer ? componentParticipantId(requirer) : EXTERNAL_PARTICIPANT_ID,
        to: owner,
      };
    }
    const provider = providerFor.get(interfaceId);
    return {
      from: owner,
      to: provider ? componentParticipantId(provider) : EXTERNAL_PARTICIPANT_ID,
    };
  };

  const register = (
    stepId: string,
    ref: Omit<SolutionStepRef, "stepId">,
    step: ScenarioStep,
  ) => {
        const from = participantIds.has(step.fromParticipantId ?? "") ? step.fromParticipantId! : EXTERNAL_PARTICIPANT_ID;
        items.push({ ...step, fromParticipantId: from });
        stepRefs.set(stepId, { stepId, ...ref });
  };

  for (const component of design.components) {
    for (const ui of component.interfaces) {
      const operations = [...ui.operations].sort((a, b) => a.ordinal - b.ordinal);
      const endpoints = resolveEndpoints(component.object_id, ui.object_id, ui.direction);
      if (operations.length === 0) {
        const stepId = `iface-${ui.object_id}`;
        register(
          stepId,
          {
            operationId: null,
            operationName: ui.name,
            componentId: component.object_id,
            componentName: component.name,
            interfaceId: ui.object_id,
            interfaceName: ui.name,
            direction: ui.direction,
          },
          {
            kind: "actor",
            id: stepId,
            phase: "request",
            fromParticipantId: endpoints.from,
            toParticipantId: endpoints.to,
            label: ui.name,
          },
        );
        continue;
      }
      for (const operation of operations) {
        const requestId = `step-${operation.object_id}-request`;
        register(
          requestId,
          {
            operationId: operation.object_id,
            operationName: operation.name,
            componentId: component.object_id,
            componentName: component.name,
            interfaceId: ui.object_id,
            interfaceName: ui.name,
            direction: ui.direction,
          },
          {
            kind: "actor",
            id: requestId,
            phase: "request",
            fromParticipantId: endpoints.from,
            toParticipantId: endpoints.to,
            label: `${operation.name} · ${ui.name}`,
          },
        );
        if (operation.operation_kind !== "event") {
          const responseId = `step-${operation.object_id}-response`;
          register(
            responseId,
            {
              operationId: operation.object_id,
              operationName: operation.name,
              componentId: component.object_id,
              componentName: component.name,
              interfaceId: ui.object_id,
              interfaceName: ui.name,
              direction: ui.direction,
            },
            {
              kind: "actor",
              id: responseId,
              phase: "success-response",
              fromParticipantId: endpoints.to,
              toParticipantId: endpoints.from,
              label: `${operation.name} response`,
            },
          );
        }
      }
    }
  }

  const document: ScenarioDocument = {
    version: 1,
    preconditions: "",
    trigger: "",
    participants,
    contractIds: [],
    beforeState: [],
    afterState: [],
    items,
    assertions: [],
    notes: "",
  };

  return { document, stepRefs };
}
