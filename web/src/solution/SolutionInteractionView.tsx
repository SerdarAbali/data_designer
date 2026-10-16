import { useMemo } from "react";

import SequenceDiagram from "../components/scenarios/SequenceDiagram";
import type { SolutionDesign } from "./solutionModel";
import { buildSolutionSequence } from "./solutionSequence";

type Props = {
  design: SolutionDesign;
  editable: boolean;
  selectedOperationId: string | null;
  selectedInterfaceId: string | null;
  onSelectOperation: (componentId: string, interfaceId: string, operationId: string) => void;
  onSelectInterface: (componentId: string, interfaceId: string) => void;
  onAddComponent: () => void;
};

export default function SolutionInteractionView({
  design,
  editable,
  selectedOperationId,
  selectedInterfaceId,
  onSelectOperation,
  onSelectInterface,
  onAddComponent,
}: Props) {
  const { document, stepRefs } = useMemo(() => buildSolutionSequence(design), [design]);
  const hasMessages = document.items.length > 0;

  if (!hasMessages) {
    return (
      <div className="solution-container-empty" role="status">
        <span className="empty-icon">⇄</span>
        <h3>No interactions modeled yet</h3>
        <p>Add interfaces and operations to components to generate the dynamic sequence.</p>
        {editable && design.components.length === 0 && (
          <button type="button" onClick={onAddComponent}>+ Add component</button>
        )}
      </div>
    );
  }

  const selectedStepId = selectedOperationId
    ? `step-${selectedOperationId}-request`
    : selectedInterfaceId
      ? `iface-${selectedInterfaceId}`
      : null;

  return (
    <div className="solution-interaction" aria-label={`Interaction view for ${design.solution.name}`}>
      <SequenceDiagram
        document={document}
        index={null}
        ariaLabel={`Interaction sequence for ${design.solution.name}`}
        selectedStepId={selectedStepId}
        onSelectStep={(stepId) => {
          const ref = stepRefs.get(stepId);
          if (!ref) return;
          if (ref.operationId) onSelectOperation(ref.componentId, ref.interfaceId, ref.operationId);
          else onSelectInterface(ref.componentId, ref.interfaceId);
        }}
      />
    </div>
  );
}
